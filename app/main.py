from flask import Blueprint, render_template, session, redirect, url_for
from app.models import Election, Candidate, VoteRecord
from datetime import datetime  # 引入时间模块

# 创建一个前端展示模块的蓝图
main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """网站的主入口：带时间自动分类的投票大厅"""
    # 如果用户没有登录，直接返回登录页
    if 'user_id' not in session:
        return render_template('login.html')

    now = datetime.now()

    # --- 自动化状态计算逻辑 ---
    # 1. 查出所有审核通过(approved)的投票项目
    all_approved = Election.query.filter_by(review_status='approved').all()

    # 2. 为每个项目动态打上时间标签，用于前端显示
    for e in all_approved:
        if e.end_time and now > e.end_time:
            e.time_label = '已结束'
            e.time_status = 'ended'
            e.badge_class = 'bg-secondary'
        elif e.start_time and now < e.start_time:
            e.time_label = '预热中'
            e.time_status = 'upcoming'
            e.badge_class = 'bg-warning text-dark'
        else:
            e.time_label = '进行中'
            e.time_status = 'active'
            e.badge_class = 'bg-success'

    # 获取当前登录用户信息
    name = session.get('name')
    role = session.get('role')

    # 将处理好“时间标签”的项目传给 index.html
    return render_template('index.html',
                           name=name,
                           role=role,
                           elections=all_approved,
                           now=now)


@main_bp.route('/election/<int:election_id>')
def election_detail(election_id):
    """选举详情页：集成排名计算、时间锁定与【审核状态校验】"""
    if 'user_id' not in session:
        return redirect(url_for('main.index'))

    user_id = session.get('user_id')
    now = datetime.now()

    # 查出投票信息
    election = Election.query.get_or_404(election_id)
    candidates = Candidate.query.filter_by(election_id=election_id).all()

    # --- 1. 计算实时票数与排名 ---
    for candidate in candidates:
        candidate.vote_count = VoteRecord.query.filter_by(candidate_id=candidate.id).count()

    # 按票数降序排序
    candidates.sort(key=lambda x: getattr(x, 'vote_count', 0), reverse=True)

    # --- 2. 判定当前用户的投票权利 ---
    # a. 检查是否投过票
    has_voted = VoteRecord.query.filter_by(user_id=user_id, election_id=election_id).first() is not None

    # b. 检查时间状态
    is_expired = election.end_time and now > election.end_time
    not_started = election.start_time and now < election.start_time

    # c. 核心改进：检查用户审核状态 (管理员默认通过)
    is_approved = session.get('is_approved') == True or session.get('role') == 'admin'

    # 最终决定按钮状态的布尔值：
    # 必须满足：没投过票 + 不在非投票时间段 + 项目激活 + 【用户已审核通过】
    can_vote = (not has_voted) and (not is_expired) and (not not_started) and \
               (election.status == 'active') and is_approved

    return render_template('election_detail.html',
                           election=election,
                           candidates=candidates,
                           has_voted=has_voted,
                           is_expired=is_expired,
                           not_started=not_started,
                           is_approved=is_approved,
                           can_vote=can_vote)


@main_bp.route('/election/<int:election_id>/results')
def election_results(election_id):
    """数据可视化统计大屏"""
    if 'user_id' not in session:
        return redirect(url_for('main.index'))
    Election.query.get_or_404(election_id)
    return render_template('results.html', election_id=election_id)


@main_bp.route('/register')
def register_page():
    """注册页面：未审核用户也可访问"""
    return render_template('register.html')


@main_bp.route('/profile')
def profile_page():
    """个人中心：允许所有已登录用户（含未审核）访问"""
    if 'user_id' not in session:
        return redirect(url_for('main.index'))
    return render_template('profile.html', name=session.get('name'))


# 权限拦截器相关导入
from app.admin import admin_required
from app.auth import login_required


@main_bp.route('/admin/dashboard')
@login_required
@admin_required
def admin_panel():
    """管理员超级面板"""
    return render_template('admin_panel.html', name=session.get('name'))