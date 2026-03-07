from flask import Blueprint, request, jsonify, session
from app.models import db, User
import functools

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


# --- 高级权限拦截器：不仅要登录，还要审核通过 ---
def approval_required(view):
    """
    这是一个高级装饰器。
    挂载它后，即便用户登录了，如果管理员还没审核通过，也无法进行投票或提议。
    """

    @functools.wraps(view)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'code': 401, 'msg': '请先登录'}), 401

        user = User.query.get(session['user_id'])
        if not user or not user.is_approved:
            return jsonify({'code': 403, 'msg': '您的账号处于待审核状态，请联系管理员！'}), 403
        return view(*args, **kwargs)

    return wrapped_view


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'code': 401, 'msg': '请先登录'}), 401
        return view(*args, **kwargs)

    return wrapped_view


@auth_bp.route('/register', methods=['POST'])
def register():
    """升级版注册：采集学术背景字段"""
    data = request.get_json()
    student_id = data.get('student_id')
    name = data.get('name')
    password = data.get('password')

    # 新增字段
    dept = data.get('department')
    major = data.get('major')
    class_name = data.get('class_name')
    year = data.get('entry_year')

    if not all([student_id, name, password, dept]):
        return jsonify({'code': 400, 'msg': '必填项（学号、姓名、密码、院系）不能为空！'}), 400

    if User.query.filter_by(student_id=student_id).first():
        return jsonify({'code': 400, 'msg': '该学号已被注册！'}), 400

    # 创建新用户，注意：is_approved 默认为 False (待审核)
    new_user = User(
        student_id=student_id,
        name=name,
        department=dept,
        major=major,
        class_name=class_name,
        entry_year=year,
        role='student',
        is_approved=False  # 初始状态为待审核
    )
    new_user.set_password(password)

    try:
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'code': 200, 'msg': '申请已提交！请等待管理员审核。'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'msg': f'服务器错误: {str(e)}'}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """增强版登录：返回审核状态"""
    data = request.get_json()
    user = User.query.filter_by(student_id=data.get('student_id')).first()

    if user and user.check_password(data.get('password')):
        # 存入 Session
        session['user_id'] = user.id
        session['student_id'] = user.student_id
        session['role'] = user.role
        session['name'] = user.name
        session['is_approved'] = user.is_approved

        return jsonify({
            'code': 200,
            'msg': '登录成功！',
            'data': {
                'name': user.name,
                'role': user.role,
                'is_approved': user.is_approved,
                'department': user.department
            }
        })
    return jsonify({'code': 401, 'msg': '账号或密码错误'}), 401


@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'code': 200, 'msg': '已退出'})