import os
import json
import functools
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, session, current_app
from app.models import db, Election, Candidate, VoteRecord, User
from app.auth import login_required
from app import redis_client
from sqlalchemy import func
import hashlib

# 引入机器学习相关库
from sklearn.ensemble import IsolationForest
import numpy as np

vote_bp = Blueprint('vote', __name__, url_prefix='/api/vote')


# ================= 0. 安全辅助功能：Redis 限流装饰器 =================

def rate_limit(limit=1, period=60, key_prefix='rate_limit'):
    """高并发防刷限流装饰器"""

    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            if not redis_client:
                return f(*args, **kwargs)

            user_id = session.get('user_id')
            identifier = f"user:{user_id}" if user_id else f"ip:{request.remote_addr}"
            key = f"{key_prefix}:{f.__name__}:{identifier}"

            current_count = redis_client.get(key)
            if current_count and int(current_count) >= limit:
                return jsonify({'code': 429, 'msg': f'操作太频繁，请在 {period} 秒后再试'}), 429

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
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
        os.makedirs(upload_folder, exist_ok=True)

        ext = os.path.splitext(file.filename)[1] or '.png'
        unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
        file_path = os.path.join(upload_folder, unique_filename)

        file.save(file_path)
        return f"/static/uploads/{unique_filename}"
    return None


# ================= 1. 提议功能：支持详情查询、保存草稿与修改 =================

@vote_bp.route('/proposal/<int:prop_id>', methods=['GET'])
@login_required
def get_proposal_detail(prop_id):
    """获取单个提议详情：解决点击编辑 404 问题"""
    prop = Election.query.get_or_404(prop_id)
    # 安全检查：只能查看自己发起的提议
    if prop.proposer_id != session.get('user_id'):
        return jsonify({'code': 403, 'msg': '无权访问此提议内容'}), 403

    candidates = Candidate.query.filter_by(election_id=prop.id).all()

    return jsonify({
        'code': 200,
        'data': {
            'id': prop.id,
            'title': prop.title,
            'description': prop.description,
            'image_url': prop.image_url,
            'is_multi_choice': prop.is_multi_choice,
            'start_time': prop.start_time.strftime('%Y-%m-%dT%H:%M') if prop.start_time else "",
            'end_time': prop.end_time.strftime('%Y-%m-%dT%H:%M') if prop.end_time else "",
            'options': [{'name': c.name, 'image': c.image_url} for c in candidates]
        }
    })


@vote_bp.route('/propose', methods=['POST'])
@login_required
@rate_limit(limit=5, period=60, key_prefix='propose')
def submit_proposal():
    """学生提交/更新投票项目提议：支持【保存草稿】与【更新旧草稿】"""
    prop_id = request.form.get('id')  # 获取ID用于判断是新建还是更新
    title = request.form.get('title')
    description = request.form.get('description')
    start_time_str = request.form.get('start_time')
    end_time_str = request.form.get('end_time')
    is_multi = request.form.get('is_multi_choice') == 'true'
    action = request.form.get('action', 'submit')  # 'draft' 或 'submit'

    # 1. 查找现有提议或创建新对象
    if prop_id:
        proposal = Election.query.get(prop_id)
        if not proposal or proposal.proposer_id != session['user_id']:
            return jsonify({'code': 403, 'msg': '无权修改该提议'}), 403
        # 只有在草稿、审核中或被驳回时允许修改
        if proposal.review_status not in ['draft', 'pending', 'rejected']:
            return jsonify({'code': 400, 'msg': '该投票项目已发布或已结束，无法修改'}), 400
    else:
        proposal = Election(proposer_id=session['user_id'], status='draft')

    # 2. 基础校验 (草稿模式下放宽校验)
    if action == 'submit':
        if not title or not description:
            return jsonify({'code': 400, 'msg': '正式提交审核前，请填写标题和描述'}), 400
    else:
        title = title or f"未命名草稿_{datetime.now().strftime('%m%d_%H%M')}"

    # 3. 更新字段内容
    proposal.title = title
    proposal.description = description
    proposal.is_multi_choice = is_multi
    proposal.review_status = 'draft' if action == 'draft' else 'pending'

    # 时间处理
    try:
        if start_time_str:
            proposal.start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
        if end_time_str:
            proposal.end_time = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        if action == 'submit':
            return jsonify({'code': 400, 'msg': '时间格式不正确'}), 400

    # 海报处理
    if 'image' in request.files:
        proposal.image_url = save_upload_file(request.files['image'])

    try:
        db.session.add(proposal)
        db.session.flush()

        # 4. 更新选项：编辑模式下先删除旧选项再重新插入
        options_str = request.form.get('options', '[]')
        options = json.loads(options_str)

        Candidate.query.filter_by(election_id=proposal.id).delete()
        for i, opt_name in enumerate(options):
            if opt_name.strip():
                opt_img_key = f'option_image_{i}'
                opt_image_url = save_upload_file(request.files.get(opt_img_key))

                new_candidate = Candidate(
                    election_id=proposal.id,
                    name=opt_name.strip(),
                    manifesto="发起人预设",
                    image_url=opt_image_url,
                    is_qualified=True if action == 'submit' else False
                )
                db.session.add(new_candidate)

        db.session.commit()
        msg = '草稿已成功保存！' if action == 'draft' else '提议已提交，请等待管理员审核！'
        return jsonify({'code': 200, 'msg': msg})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'msg': f'服务器错误: {str(e)}'}), 500


@vote_bp.route('/apply_candidate', methods=['POST'])
@login_required
@rate_limit(limit=1, period=60, key_prefix='apply')
def apply_candidate():
    """学生自荐或推荐他人成为候选人"""
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


# ==========================================
# [修改] 核心投票机制：所有人均可参与
# ==========================================
@vote_bp.route('/do_vote', methods=['POST'])
@login_required
@rate_limit(limit=1, period=3, key_prefix='vote')
def do_vote():
    """执行投票：支持单选与多选，支持选票修改"""
    data = request.get_json()
    election_id = data.get('election_id')
    candidate_ids = data.get('candidate_ids', [])
    user_id = session.get('user_id')

    if not candidate_ids or not isinstance(candidate_ids, list):
        return jsonify({'code': 400, 'msg': '未选择候选人'}), 400

    election = Election.query.get(election_id)
    if not election:
        return jsonify({'code': 404, 'msg': '投票不存在'}), 404

    now = datetime.now()
    if election.start_time and now < election.start_time:
        return jsonify({'code': 400, 'msg': '投票尚未开始'}), 400
    if election.end_time and now > election.end_time:
        return jsonify({'code': 400, 'msg': '投票已经结束'}), 400

    if election.status not in ['active', 'published']:
        return jsonify({'code': 400, 'msg': '投票未开启'}), 400

    if not election.is_multi_choice and len(candidate_ids) > 1:
        return jsonify({'code': 400, 'msg': '该投票项目仅支持单选'}), 400

    existing_records = VoteRecord.query.filter_by(user_id=user_id, election_id=election_id).all()

    action_msg = '投票成功！'
    if existing_records:
        if getattr(election, 'allow_update_vote', False):
            for r in existing_records:
                db.session.delete(r)
            db.session.flush()
            action_msg = '选票修改成功！旧记录已作废。'
        else:
            return jsonify({'code': 403, 'msg': '您已参与过本次投票，且该项目不允许修改选票'}), 403

    try:
        tokens = []
        for cid in candidate_ids:
            candidate = Candidate.query.get(cid)
            if not candidate or not candidate.is_qualified:
                continue

            new_vote = VoteRecord(
                user_id=user_id,
                election_id=election_id,
                candidate_id=cid,
                ip_address=request.remote_addr
            )
            new_vote.generate_hash()
            db.session.add(new_vote)
            tokens.append(new_vote.vote_hash)

        db.session.commit()
        return jsonify({'code': 200, 'msg': action_msg, 'tokens': tokens})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'msg': f'系统繁忙: {str(e)}'}), 500


# ================= 3. 个人中心相关接口 =================

@vote_bp.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    """修改个人信息"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if not user:
        return jsonify({'code': 404, 'msg': '用户不存在'}), 404
    data = request.get_json()
    bio = data.get('bio')
    if bio is not None:
        user.bio = bio
    try:
        db.session.commit()
        session['bio'] = bio
        return jsonify({'code': 200, 'msg': '个人信息已成功更新！'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'msg': f'保存失败: {str(e)}'}), 500


@vote_bp.route('/my_records', methods=['GET'])
@login_required
def get_personal_records():
    """获取个人投票历史及【提议/草稿】数据"""
    user_id = session['user_id']
    user = User.query.get(user_id)

    votes = db.session.query(VoteRecord, Election, Candidate).join(
        Election, VoteRecord.election_id == Election.id
    ).join(
        Candidate, VoteRecord.candidate_id == Candidate.id
    ).filter(VoteRecord.user_id == user_id).all()

    proposals = Election.query.filter_by(proposer_id=user_id).all()

    return jsonify({
        'code': 200,
        'bio': user.bio if user else "",
        'votes': [{
            'election': v.Election.title,
            'candidate': v.Candidate.name,
            'time': v.VoteRecord.vote_time.strftime('%Y-%m-%d %H:%M'),
            'hash': v.VoteRecord.vote_hash
        } for v in votes],
        'proposals': [{
            'id': p.id,
            'title': p.title,
            'status': p.review_status,
            'feedback': p.admin_feedback
        } for p in proposals]
    })


# ================= 4. 统计与审计接口 =================

@vote_bp.route('/statistics/<int:election_id>', methods=['GET'])
@login_required
def get_statistics(election_id):
    """提供统计数据接口：集成 ECharts 可视化与 AI 安全审计"""

    cache_key = f"stats:election:{election_id}"
    if redis_client:
        cached_data = redis_client.get(cache_key)
        if cached_data:
            return jsonify({
                'code': 200,
                'msg': '获取统计数据成功(Cache)',
                'data': json.loads(cached_data)
            })

    election = Election.query.get(election_id)
    if not election:
        return jsonify({'code': 404, 'msg': '选举项目不存在'}), 404

    all_records = VoteRecord.query.filter_by(election_id=election_id).order_by(VoteRecord.vote_time).all()
    total_votes = len(all_records)

    candidates = Candidate.query.filter_by(election_id=election_id).all()
    c_names = [c.name for c in candidates]
    c_votes = [VoteRecord.query.filter_by(candidate_id=c.id).count() for c in candidates]

    time_series = {}
    for r in all_records:
        hour_key = r.vote_time.strftime('%m-%d %H:00')
        time_series[hour_key] = time_series.get(hour_key, 0) + 1

    trend_labels = sorted(time_series.keys())
    trend_values = [time_series[k] for k in trend_labels]

    risk_report = {"level": "低", "suspicious_count": 0, "score": 100}

    if total_votes > 10:
        try:
            features = []
            ip_counts = {}
            for i, r in enumerate(all_records):
                ip_counts[r.ip_address] = ip_counts.get(r.ip_address, 0) + 1
                delta = (r.vote_time - all_records[i - 1].vote_time).total_seconds() if i > 0 else 0
                features.append([r.vote_time.hour, r.vote_time.minute, delta, ip_counts[r.ip_address]])

            X = np.array(features)
            clf = IsolationForest(contamination=0.05, random_state=42)
            preds = clf.fit_predict(X)

            susp_count = int(np.sum(preds == -1))
            risk_score = max(0, 100 - (susp_count / total_votes * 500))

            risk_report = {
                "level": "高" if risk_score < 60 else ("中" if risk_score < 85 else "低"),
                "suspicious_count": susp_count,
                "score": round(risk_score, 1)
            }
        except Exception as e:
            current_app.logger.error(f"AI Audit Error: {e}")

    dept_counts = db.session.query(
        User.department,
        func.count(VoteRecord.id)
    ).join(User, User.id == VoteRecord.user_id).filter(
        VoteRecord.election_id == election_id
    ).group_by(User.department).all()

    response_data = {
        'title': election.title,
        'total_votes': total_votes,
        'candidates': c_names,
        'votes': c_votes,
        'trend': {'labels': trend_labels, 'values': trend_values},
        'departments': [{"name": d if d else "未知", "value": c} for d, c in dept_counts],
        'security': risk_report
    }

    if redis_client:
        redis_client.setex(cache_key, 60, json.dumps(response_data))

    return jsonify({
        'code': 200,
        'msg': '获取统计数据成功',
        'data': response_data
    })