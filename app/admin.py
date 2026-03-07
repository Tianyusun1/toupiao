from flask import Blueprint, request, jsonify, session
from app.models import db, User, Election, Candidate
from app.auth import login_required
import functools

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# --- 管理员权限拦截器 ---
def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get('role') != 'admin':
            return jsonify({'code': 403, 'msg': '权限不足：仅限管理员操作'}), 403
        return view(*args, **kwargs)

    return wrapped_view


# ================= 1. 用户资质审核 =================

@admin_bp.route('/users/pending', methods=['GET'])
@login_required
@admin_required
def get_pending_users():
    """获取所有待审核的用户列表"""
    users = User.query.filter_by(is_approved=False, role='student').all()
    data = [{
        'id': u.id,
        'student_id': u.student_id,
        'name': u.name,
        'department': u.department,
        'major': u.major,
        'class': u.class_name
    } for u in users]
    return jsonify({'code': 200, 'data': data})


@admin_bp.route('/users/approve', methods=['POST'])
@login_required
@admin_required
def approve_user():
    """核准学生身份"""
    data = request.get_json()
    user_id = data.get('user_id')
    action = data.get('action')  # 'pass' 或 'reject'

    user = User.query.get(user_id)
    if not user:
        return jsonify({'code': 404, 'msg': '用户不存在'}), 404

    if action == 'pass':
        user.is_approved = True
        db.session.commit()
        return jsonify({'code': 200, 'msg': f'已批准 {user.name} 的注册申请'})
    else:
        db.session.delete(user)  # 驳回则直接删除记录，让其重新注册
        db.session.commit()
        return jsonify({'code': 200, 'msg': '已驳回该申请'})


# ================= 2. 投票提议审批 (UGC流) =================

@admin_bp.route('/elections/pending', methods=['GET'])
@login_required
@admin_required
def get_pending_elections():
    """获取学生提交的投票申请列表"""
    # 查找审核状态为 pending 的选举提议
    elections = Election.query.filter_by(review_status='pending').all()
    data = [{
        'id': e.id,
        'title': e.title,
        'description': e.description,
        'proposer_name': User.query.get(e.proposer_id).name if e.proposer_id else "系统"
    } for e in elections]
    return jsonify({'code': 200, 'data': data})


@admin_bp.route('/elections/review', methods=['POST'])
@login_required
@admin_required
def review_election():
    """审核投票提议"""
    data = request.get_json()
    eid = data.get('election_id')
    action = data.get('action')  # 'approve' 或 'reject'
    feedback = data.get('feedback', '')

    election = Election.query.get(eid)
    if not election:
        return jsonify({'code': 404, 'msg': '提议不存在'}), 404

    if action == 'approve':
        election.review_status = 'approved'
        election.status = 'active'  # 审核通过直接进入进行中，或设为草稿待手动开启
        # 设置投票起止时间（可由管理员在此时指定）
        election.start_time = db.func.now()
        # 这里默认给7天有效期，实际可从data获取
    else:
        election.review_status = 'rejected'
        election.admin_feedback = feedback

    db.session.commit()
    return jsonify({'code': 200, 'msg': '审核操作成功'})


# ================= 3. 候选人资质审核 =================

@admin_bp.route('/candidates/review', methods=['POST'])
@login_required
@admin_required
def qualify_candidate():
    """核准候选人资格"""
    data = request.get_json()
    cid = data.get('candidate_id')
    qualified = data.get('is_qualified')  # True 或 False

    candidate = Candidate.query.get(cid)
    if candidate:
        candidate.is_qualified = qualified
        db.session.commit()
        return jsonify({'code': 200, 'msg': '候选人资质状态已更新'})
    return jsonify({'code': 404, 'msg': '未找到候选人'}), 404