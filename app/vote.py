import os
import json
import functools
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, session, current_app
from app.models import db, Election, Candidate, VoteRecord, User
from app.auth import login_required, approval_required
from app import redis_client  # 确保你的 __init__.py 中已经初始化了 redis_client
from sqlalchemy import func
import hashlib

vote_bp = Blueprint('vote', __name__, url_prefix='/api/vote')


# ================= 0. 安全辅助功能：Redis 限流装饰器 =================

def rate_limit(limit=1, period=60, key_prefix='rate_limit'):
    """
    高并发防刷限流装饰器
    :param limit: 允许访问的次数
    :param period: 时间周期（秒）
    :param key_prefix: Redis 键前缀
    """

    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            if not redis_client:
                return f(*args, **kwargs)  # 如果没有配置 Redis，则降级不限流

            # 优先使用用户ID标识，未登录则使用IP地址
            user_id = session.get('user_id')
            identifier = f"user:{user_id}" if user_id else f"ip:{request.remote_addr}"
            key = f"{key_prefix}:{f.__name__}:{identifier}"

            # 检查 Redis 里的请求计数
            current_count = redis_client.get(key)
            if current_count and int(current_count) >= limit:
                return jsonify({'code': 429, 'msg': f'操作太频繁，请在 {period} 秒后再试'}), 429

            # 首次请求设置过期时间，非首次请求递增
            if not current_count:
                redis_client.setex(key, period, 1)
            else:
                redis_client.incr(key)

            return f(*args, **kwargs)

        return wrapped

    return decorator


def save_upload_file(file):
    """辅助函数：保存上传的图片文件并返回相对路径URL"""
    if file and file.filename:
        # 确保服务器的静态文件目录下存在 uploads 文件夹
        upload_folder = os.path.join(request.root_path, 'static', 'uploads')
        os.makedirs(upload_folder, exist_ok=True)

        # 使用时间戳防止用户上传的文件名冲突
        filename = secure_filename(file.filename)
        unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
        file_path = os.path.join(upload_folder, unique_filename)

        # 保存文件到物理硬盘
        file.save(file_path)
        return f"/static/uploads/{unique_filename}"
    return None


# ================= 1. 学生提议功能 (UGC) =================

@vote_bp.route('/propose', methods=['POST'])
@login_required
@approval_required
@rate_limit(limit=1, period=60, key_prefix='propose')  # 限制1分钟只能提议1次
def submit_proposal():
    """学生提交投票项目提议（支持主海报、起止时间及各个选项的独立图片上传）"""
    title = request.form.get('title')
    description = request.form.get('description')
    start_time_str = request.form.get('start_time')
    end_time_str = request.form.get('end_time')

    options_str = request.form.get('options', '[]')
    try:
        options = json.loads(options_str)
    except:
        options = []

    if not title or not description:
        return jsonify({'code': 400, 'msg': '标题和描述不能为空'}), 400

    if len(options) < 2:
        return jsonify({'code': 400, 'msg': '一个投票至少需要提供2个选项'}), 400

    # 1. 处理时间格式转换
    start_time = None
    end_time = None
    try:
        if start_time_str:
            start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
        if end_time_str:
            end_time = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        return jsonify({'code': 400, 'msg': '时间格式错误'}), 400

    # 2. 处理投票项目的大海报图片
    election_image_url = None
    if 'image' in request.files:
        election_image_url = save_upload_file(request.files['image'])

    # 3. 创建一个待审核的选举项目
    new_proposal = Election(
        title=title,
        description=description,
        image_url=election_image_url,
        start_time=start_time,
        end_time=end_time,
        proposer_id=session['user_id'],
        review_status='pending',
        status='draft',
        is_official=False
    )

    try:
        db.session.add(new_proposal)
        db.session.flush()

        # 4. 绑定选项并处理各个选项自己的附件/图片
        for i, opt_name in enumerate(options):
            if opt_name.strip():
                opt_img_key = f'option_image_{i}'
                opt_image_url = None
                if opt_img_key in request.files:
                    opt_image_url = save_upload_file(request.files[opt_img_key])

                new_candidate = Candidate(
                    election_id=new_proposal.id,
                    name=opt_name.strip(),
                    manifesto="发起人预设选项",
                    department=session.get('department'),
                    image_url=opt_image_url,
                    is_qualified=True
                )
                db.session.add(new_candidate)

        db.session.commit()
        return jsonify({'code': 200, 'msg': '提议及选项已成功提交，请等待管理员审核！'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'msg': str(e)}), 500


@vote_bp.route('/apply_candidate', methods=['POST'])
@login_required
@approval_required
@rate_limit(limit=1, period=60, key_prefix='apply')  # 限制1分钟只能申请1次
def apply_candidate():
    """学生自荐或推荐他人成为候选人 (已升级支持海报上传)"""
    election_id = request.form.get('election_id')
    name = request.form.get('name')
    manifesto = request.form.get('manifesto')

    if not election_id or not name:
        return jsonify({'code': 400, 'msg': '参数不完整'}), 400

    election = Election.query.get(election_id)
    if not election or election.review_status != 'approved':
        return jsonify({'code': 400, 'msg': '该投票项目尚未通过审核或不存在'}), 400

    candidate_image_url = None
    if 'image' in request.files:
        candidate_image_url = save_upload_file(request.files['image'])

    new_candidate = Candidate(
        election_id=election_id,
        name=name,
        manifesto=manifesto,
        image_url=candidate_image_url,
        department=session.get('department'),
        is_qualified=False
    )

    try:
        db.session.add(new_candidate)
        db.session.commit()
        return jsonify({'code': 200, 'msg': '候选人申请已提交，等待资质审核！'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'msg': '系统繁忙'}), 500


# ================= 2. 安全投票机制 =================

@vote_bp.route('/do_vote', methods=['POST'])
@login_required
@approval_required
@rate_limit(limit=1, period=60, key_prefix='vote')  # 核心：限制同一用户每分钟只能提交一次投票
def do_vote():
    """执行投票：包含 Redis 防刷与哈希凭证生成"""
    data = request.get_json()
    election_id = data.get('election_id')
    candidate_id = data.get('candidate_id')
    user_id = session.get('user_id')

    # 1. 基础校验
    election = Election.query.get(election_id)
    if not election:
        return jsonify({'code': 404, 'msg': '投票不存在'}), 404

    # --- 新增时间自动化核验 ---
    now = datetime.now()
    if election.start_time and now < election.start_time:
        return jsonify({'code': 400, 'msg': '投票尚未开始'}), 400
    if election.end_time and now > election.end_time:
        return jsonify({'code': 400, 'msg': '投票已经结束'}), 400

    if election.status != 'active':
        return jsonify({'code': 400, 'msg': '投票未开启'}), 400

    candidate = Candidate.query.get(candidate_id)
    if not candidate or not candidate.is_qualified:
        return jsonify({'code': 400, 'msg': '候选人资质未通过审核'}), 400

    # 2. 一人一票校验
    if VoteRecord.query.filter_by(user_id=user_id, election_id=election_id).first():
        return jsonify({'code': 403, 'msg': '您已投过票，请勿重复操作'}), 403

    # 3. 生成投票记录与【安全哈希凭证】
    new_vote = VoteRecord(
        user_id=user_id,
        election_id=election_id,
        candidate_id=candidate_id,
        ip_address=request.remote_addr
    )
    new_vote.generate_hash()

    try:
        db.session.add(new_vote)
        db.session.commit()
        return jsonify({
            'code': 200,
            'msg': '投票成功！',
            'token': new_vote.vote_hash
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'msg': '系统繁忙'}), 500


# ================= 3. 个人数据接口 =================

@vote_bp.route('/my_records', methods=['GET'])
@login_required
def get_personal_records():
    """获取个人投票历史及提议进度"""
    user_id = session['user_id']

    votes = db.session.query(VoteRecord, Election, Candidate).join(
        Election, VoteRecord.election_id == Election.id
    ).join(
        Candidate, VoteRecord.candidate_id == Candidate.id
    ).filter(VoteRecord.user_id == user_id).all()

    proposals = Election.query.filter_by(proposer_id=user_id).all()

    return jsonify({
        'code': 200,
        'votes': [{
            'election': v.Election.title,
            'candidate': v.Candidate.name,
            'time': v.VoteRecord.vote_time.strftime('%Y-%m-%d %H:%M'),
            'hash': v.VoteRecord.vote_hash
        } for v in votes],
        'proposals': [{
            'title': p.title,
            'status': p.review_status,
            'feedback': p.admin_feedback
        } for p in proposals]
    })


# ================= 4. 数据统计与可视化接口 =================

@vote_bp.route('/statistics/<int:election_id>', methods=['GET'])
@login_required
def get_statistics(election_id):
    """提供给 ECharts 大屏的统计数据接口"""
    election = Election.query.get(election_id)
    if not election:
        return jsonify({'code': 404, 'msg': '选举项目不存在'}), 404

    total_votes = VoteRecord.query.filter_by(election_id=election_id).count()

    candidates = Candidate.query.filter_by(election_id=election_id).all()
    candidate_names = []
    candidate_votes = []

    for c in candidates:
        candidate_names.append(c.name)
        votes_count = VoteRecord.query.filter_by(candidate_id=c.id).count()
        candidate_votes.append(votes_count)

    dept_counts = db.session.query(
        User.department,
        func.count(VoteRecord.id)
    ).join(
        VoteRecord, User.id == VoteRecord.user_id
    ).filter(
        VoteRecord.election_id == election_id
    ).group_by(
        User.department
    ).all()

    departments_data = [
        {"name": dept if dept else "其他", "value": count}
        for dept, count in dept_counts
    ]

    return jsonify({
        'code': 200,
        'msg': '获取统计数据成功',
        'data': {
            'title': election.title,
            'total_votes': total_votes,
            'candidates': candidate_names,
            'votes': candidate_votes,
            'departments': departments_data
        }
    })