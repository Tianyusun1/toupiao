from flask import Blueprint, render_template, session, redirect, url_for
from app.models import Election, Candidate  # 引入数据库模型，用来查投票数据

# 创建一个前端展示模块的蓝图
main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """网站的主入口：投票大厅"""
    # 如果用户没有登录，直接返回炫酷的 login.html 登录页
    if 'user_id' not in session:
        return render_template('login.html')

    # 【核心逻辑】：如果用户已经登录了，去数据库查出所有正在进行中（active）的选举活动
    active_elections = Election.query.filter_by(status='active').all()

    # 获取当前登录用户的名字和权限
    name = session.get('name')
    role = session.get('role')

    # 把用户信息和查出来的选举活动数据，全部扔给高级模板 index.html 去渲染
    return render_template('index.html',
                           name=name,
                           role=role,
                           elections=active_elections)


@main_bp.route('/election/<int:election_id>')
def election_detail(election_id):
    """选举详情页：点击卡片后进入的投票页面"""
    # 没登录的话，一脚踢回首页去登录
    if 'user_id' not in session:
        return redirect(url_for('main.index'))

    # 根据地址栏传过来的 ID，查出这场选举的具体信息 (如果乱输ID找不到就会报404)
    election = Election.query.get_or_404(election_id)

    # 查出这场选举下面绑定的所有候选人
    candidates = Candidate.query.filter_by(election_id=election_id).all()

    # 把选举信息和候选人名单扔给详情页去渲染卡片
    return render_template('election_detail.html', election=election, candidates=candidates)

@main_bp.route('/register')
def register_page():
    """跳转到注册页面"""
    return render_template('register.html')

@main_bp.route('/profile')
def profile_page():
    """个人主页：查看投票凭证和提议进度"""
    if 'user_id' not in session:
        return redirect(url_for('main.index'))
    return render_template('profile.html', name=session.get('name'))

# 先从 app.admin 引入权限拦截器
from app.admin import admin_required
from app.auth import login_required

@main_bp.route('/admin/dashboard')
@login_required
@admin_required
def admin_panel():
    """管理员超级面板"""
    return render_template('admin_panel.html', name=session.get('name'))