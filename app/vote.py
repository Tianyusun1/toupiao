from flask import Blueprint, request, jsonify, session
from app.models import db, Election, Candidate, VoteRecord, User
from app.auth import login_required, approval_required
from app import redis_client
from sqlalchemy import func
import hashlib

vote_bp = Blueprint('vote', __name__, url_prefix='/api/vote')


# ================= 1. 学生提议功能 (UGC) =================

@vote_bp.route('/propose', methods=['POST'])
@login_required
@approval_required  # 只有审核通过的学生才能发起提议
def submit_proposal():
    """学生提交投票项目提议"""
    data = request.get_json()
    title = data.get('title')
    description = data.get('description')

    if not title or not description:
        return jsonify({'code': 400, 'msg': '标题和描述不能为空'}), 400

    # 创建一个待审核的选举项目
    new_proposal = Election(
        title=title,
        description=description,
        proposer_id=session['user_id'],
        review_status='pending',  # 初始状态：待审核
        status='draft',  # 初始状态：草稿
        is_official=False  # 标记为民间提议
    )

    try:
        db.session.add(new_proposal)
        db.session.commit()
        return jsonify({'code': 200, 'msg': '提议已提交，请等待管理员审核！'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'msg': str(e)}), 500


@vote_bp.route('/apply_candidate', methods=['POST'])
@login_required
@approval_required
def apply_candidate():
    """学生自荐或推荐他人成为候选人"""
    data = request.get_json()
    election_id = data.get('election_id')
    name = data.get('name')
    manifesto = data.get('manifesto')

    election = Election.query.get(election_id)
    if not election or election.review_status != 'approved':
        return jsonify({'code': 400, 'msg': '该投票项目尚未通过审核或不存在'}), 400

    new_candidate = Candidate(
        election_id=election_id,
        name=name,
        manifesto=manifesto,
        department=session.get('department'),
        is_qualified=False  # 初始状态：资质待审核
    )

    db.session.add(new_candidate)
    db.session.commit()
    return jsonify({'code': 200, 'msg': '候选人申请已提交，等待资质审核！'})


# ================= 2. 安全投票机制 =================

@vote_bp.route('/do_vote', methods=['POST'])
@login_required
@approval_required
def do_vote():
    """执行投票：包含 Redis 防刷与哈希凭证生成"""
    data = request.get_json()
    election_id = data.get('election_id')
    candidate_id = data.get('candidate_id')
    user_id = session.get('user_id')

    # 1. 基础校验
    election = Election.query.get(election_id)
    if not election or election.status != 'active':
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
    # 调用 model 中定义的哈希生成方法
    new_vote.generate_hash()

    try:
        db.session.add(new_vote)
        db.session.commit()
        return jsonify({
            'code': 200,
            'msg': '投票成功！',
            'token': new_vote.vote_hash  # 返回凭证，让用户觉得很高级
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

    # 我投过的票
    votes = db.session.query(VoteRecord, Election, Candidate).join(
        Election, VoteRecord.election_id == Election.id
    ).join(
        Candidate, VoteRecord.candidate_id == Candidate.id
    ).filter(VoteRecord.user_id == user_id).all()

    # 我发起的提议
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