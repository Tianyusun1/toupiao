from flask import Blueprint, request, jsonify, session, Response, current_app
from app.models import db, User, Election, Candidate, VoteRecord
from app.auth import login_required
import functools
import csv
import io
from datetime import datetime

# 统一使用 /api/admin 前缀，确保与前端 index.html 和 admin_panel.html 调用的路径一致
admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


# --- 管理员权限拦截器 ---
def admin_required(view):
    """验证用户是否具有管理员角色"""
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
    """获取所有待审核（is_approved=False）的学生列表"""
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
    """核准或驳回学生身份申请"""
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
        # 驳回处理：删除该记录，允许学生更正信息后重新注册
        db.session.delete(user)
        db.session.commit()
        return jsonify({'code': 200, 'msg': '已驳回该申请，相关记录已清除'})


# ================= 2. 投票项目管理（提议流与全列表） =================

@admin_bp.route('/elections/pending', methods=['GET'])
@login_required
@admin_required
def get_pending_elections():
    """获取待审批（review_status='pending'）的投票提议"""
    elections = Election.query.filter_by(review_status='pending').all()
    data = [{
        'id': e.id,
        'title': e.title,
        'description': e.description,
        'proposer_name': User.query.get(e.proposer_id).name if e.proposer_id else "系统"
    } for e in elections]
    return jsonify({'code': 200, 'data': data})


@admin_bp.route('/elections/all', methods=['GET'])
@login_required
@admin_required
def get_all_elections():
    """获取所有已通过审核的项目，用于前端‘数据审计’列表展示"""
    # 只要是审核通过（approved）的项目，管理员就可以导出报表 [cite: 2026-03-04]
    elections = Election.query.filter_by(review_status='approved').all()
    data = [{
        'id': e.id,
        'title': e.title,
        'status': e.status, # active, draft, ended 等
        'end_time': e.end_time.strftime('%Y-%m-%d %H:%M') if e.end_time else '长期有效'
    } for e in elections]
    return jsonify({'code': 200, 'data': data})


@admin_bp.route('/elections/review', methods=['POST'])
@login_required
@admin_required
def review_election():
    """审核学生提交的投票提议"""
    data = request.get_json()
    eid = data.get('election_id')
    action = data.get('action')  # 'approve' 或 'reject'
    feedback = data.get('feedback', '')

    election = Election.query.get(eid)
    if not election:
        return jsonify({'code': 404, 'msg': '提议不存在'}), 404

    if action == 'approve':
        election.review_status = 'approved'
        election.status = 'active'
        # 若提议时未填时间，默认审批通过即刻开启
        if not election.start_time:
            election.start_time = datetime.utcnow()
    else:
        election.review_status = 'rejected'
        election.admin_feedback = feedback

    db.session.commit()
    return jsonify({'code': 200, 'msg': '审核操作成功'})


# ================= 3. 数据导出与安全审计 =================

@admin_bp.route('/export/<int:election_id>', methods=['GET'])
@login_required
@admin_required
def export_election_data(election_id):
    """一键导出带哈希凭证的 CSV 报表，解决 Excel 中文乱码问题 [cite: 2026-03-05]"""
    election = Election.query.get_or_404(election_id)

    # 联表查询：投票记录 + 用户 + 候选人
    records = db.session.query(VoteRecord, User, Candidate).join(
        User, VoteRecord.user_id == User.id
    ).join(
        Candidate, VoteRecord.candidate_id == Candidate.id
    ).filter(VoteRecord.election_id == election_id).all()

    # 构建内存 CSV 流
    output = io.StringIO()
    # 写入 UTF-8 BOM 头部，确保 Excel 打开不乱码 [cite: 2026-03-05]
    output.write(u'\ufeff')
    writer = csv.writer(output)

    # 写入带审计维度的表头
    writer.writerow(['投票序号', '学号', '姓名', '院系', '所投选项', '投票时间', '安全哈希凭证(防篡改)'])

    for r, u, c in records:
        writer.writerow([
            r.id,
            u.student_id,
            u.name,
            u.department,
            c.name,
            r.vote_time.strftime('%Y-%m-%d %H:%M:%S'),
            r.vote_hash  # 关键导出项：用于答辩展示数据的不可篡改性 [cite: 2026-03-04]
        ])

    file_name = f"Audit_Report_{election_id}_{datetime.now().strftime('%Y%m%d')}.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={file_name}"}
    )


# ================= 4. 候选人/选项管理 =================

@admin_bp.route('/candidates/review', methods=['POST'])
@login_required
@admin_required
def qualify_candidate():
    """核准具体候选人或选项的资格"""
    data = request.get_json()
    cid = data.get('candidate_id')
    qualified = data.get('is_qualified')  # True 或 False

    candidate = Candidate.query.get(cid)
    if candidate:
        candidate.is_qualified = qualified
        db.session.commit()
        return jsonify({'code': 200, 'msg': '候选人资质状态已更新'})
    return jsonify({'code': 404, 'msg': '未找到候选人'}), 404