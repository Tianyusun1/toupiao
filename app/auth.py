from flask import Blueprint, request, jsonify, session, current_app
from app.models import db, User
import functools
import base64
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

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

    dept = data.get('department')
    major = data.get('major')
    class_name = data.get('class_name')
    year = data.get('entry_year')

    if not all([student_id, name, password, dept]):
        return jsonify({'code': 400, 'msg': '必填项（学号、姓名、密码、院系）不能为空！'}), 400

    if User.query.filter_by(student_id=student_id).first():
        return jsonify({'code': 400, 'msg': '该学号已被注册！'}), 400

    new_user = User(
        student_id=student_id,
        name=name,
        department=dept,
        major=major,
        class_name=class_name,
        entry_year=year,
        role='student',
        is_approved=False
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
    """增强版登录：集成 RSA 解密与终端调试输出"""
    data = request.get_json()
    student_id = data.get('student_id')
    encrypted_password = data.get('password')

    if not student_id or not encrypted_password:
        return jsonify({'code': 400, 'msg': '学号和密码不能为空'}), 400

    # --- 调试打印 1：前端发送的加密原始数据 ---
    print("\n" + "=" * 50)
    print(f"【DEBUG】前端请求学号: {student_id}")
    print(f"【DEBUG】收到前端 RSA 加密串: \n{encrypted_password}")
    print("=" * 50)

    # --- 核心：RSA 解密逻辑 ---
    try:
        private_key_str = current_app.config.get('RSA_PRIVATE_KEY')
        if not private_key_str:
            print("【ERROR】后端配置中未找到 RSA_PRIVATE_KEY")
            return jsonify({'code': 500, 'msg': '后端安全配置缺失'}), 500

        key = RSA.importKey(private_key_str)
        cipher = PKCS1_v1_5.new(key)

        # 执行解密
        decrypted_password = cipher.decrypt(base64.b64decode(encrypted_password), "ERROR")

        if decrypted_password == "ERROR":
            print("【DEBUG】！！！解密失败：密文无法被私钥解析")
            return jsonify({'code': 400, 'msg': '解密失败，请检查加密链路'}), 400

        # 解密成功后的明文
        password_plain = decrypted_password.decode('utf-8')

        # --- 调试打印 2：后端解密出的结果 ---
        print(f"【DEBUG】后端解密成功！还原后的明文密码为: {password_plain}")
        print("=" * 50 + "\n")

    except Exception as e:
        print(f"【ERROR】解密过程发生异常: {str(e)}")
        return jsonify({'code': 400, 'msg': f'安全校验失败: {str(e)}'}), 400

    # --- 后续：常规登录校验 ---
    user = User.query.filter_by(student_id=student_id).first()

    if user and user.check_password(password_plain):
        session['user_id'] = user.id
        session['student_id'] = user.student_id
        session['role'] = user.role
        session['name'] = user.name
        session['is_approved'] = user.is_approved
        session['department'] = user.department

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