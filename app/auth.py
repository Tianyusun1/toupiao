from flask import Blueprint, request, jsonify, session, current_app, render_template, redirect, url_for
from app.models import db, User
import functools
import base64
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


# --- 高级权限拦截器：用于拦截敏感操作(如需开放投票，请确保投票路由不再使用此装饰器) ---
def approval_required(view):
    @functools.wraps(view)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'code': 401, 'msg': '请先登录'}), 401
        user = User.query.get(session['user_id'])
        if not user or (user.role != 'admin' and not user.is_approved):
            return jsonify({'code': 403, 'msg': '您的账号处于待审核状态，暂无权限执行此操作。'}), 403
        return view(*args, **kwargs)

    return wrapped_view


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'code': 401, 'msg': '请先登录'}), 401
        return view(*args, **kwargs)

    return wrapped_view


# --- 注册路由 ---
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')

    data = request.get_json()
    student_id = data.get('student_id')
    name = data.get('name')
    password = data.get('password')
    dept = data.get('department')

    if not all([student_id, name, password, dept]):
        return jsonify({'code': 400, 'msg': '必填项不能为空！'}), 400

    if User.query.filter_by(student_id=student_id).first():
        return jsonify({'code': 400, 'msg': '该学号已被注册！'}), 400

    new_user = User(
        student_id=student_id,
        name=name,
        department=dept,
        major=data.get('major'),
        class_name=data.get('class_name'),
        entry_year=data.get('entry_year'),
        role='student',
        is_approved=False
    )
    new_user.set_password(password)

    try:
        db.session.add(new_user)
        db.session.commit()
        # [修改处] 更新了文案，因为现在不需要审核也能投票了
        return jsonify({'code': 200, 'msg': '注册成功！您可以直接登录并参与投票。'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'msg': f'服务器错误: {str(e)}'}), 500


# --- 登录路由：彻底修复 Session 写入问题，并增加黑名单拦截 ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        # 如果已经登录了还访问登录页，直接跳到首页
        if 'user_id' in session:
            return redirect(url_for('main.index'))
        return render_template('login.html')

    data = request.get_json()
    student_id = data.get('student_id')
    encrypted_password = data.get('password')

    if not student_id or not encrypted_password:
        return jsonify({'code': 400, 'msg': '学号和密码不能为空'}), 400

    # RSA 解密
    try:
        private_key_str = current_app.config.get('RSA_PRIVATE_KEY')
        if not private_key_str:
            return jsonify({'code': 500, 'msg': '后端安全配置缺失'}), 500

        key = RSA.importKey(private_key_str)
        cipher = PKCS1_v1_5.new(key)
        decrypted_password = cipher.decrypt(base64.b64decode(encrypted_password), "ERROR")

        if decrypted_password == "ERROR":
            return jsonify({'code': 400, 'msg': '安全校验失败，请刷新页面重试'}), 400

        password_plain = decrypted_password.decode('utf-8')
    except Exception as e:
        current_app.logger.error(f"解密异常: {str(e)}")
        return jsonify({'code': 400, 'msg': '安全解密失败'}), 400

    # 数据库校验
    user = User.query.filter_by(student_id=student_id).first()

    if user and user.check_password(password_plain):

        # ==========================================
        # [新增] 检查黑名单状态，如果被封禁则直接拒绝登录
        # ==========================================
        if getattr(user, 'is_banned', False):
            return jsonify({'code': 403, 'msg': '您的账号已被列入黑名单，禁止登录系统！'}), 403

        # 1. 登录前清理旧 Session
        session.clear()

        # 2. 写入 Session，强制转换类型以防拦截器查询失败
        # 特别是 user.id，确保存入的是整型
        session['user_id'] = int(user.id)
        session['role'] = str(user.role)
        session['name'] = str(user.name)
        session['is_approved'] = bool(user.is_approved)

        # 3. 显式设置持久化（根据 Config 中的 PERMANENT_SESSION_LIFETIME）
        session.permanent = True

        # 终端调试打印，方便观察
        print(f"【DEBUG】用户 {user.name} 登录成功，Session ID: {session['user_id']} 已保存")

        return jsonify({
            'code': 200,
            'msg': '登录成功！',
            'data': {
                'name': user.name,
                'role': user.role,
                'is_approved': user.is_approved
            }
        })

    return jsonify({'code': 401, 'msg': '账号或密码错误'}), 401


@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    if request.method == 'GET':
        return redirect(url_for('auth.login'))
    return jsonify({'code': 200, 'msg': '已退出'})