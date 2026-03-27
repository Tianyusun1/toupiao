from flask import Flask, session, request, redirect, url_for, flash
import redis
from config import Config
from app.models import db  # 核心修改：直接从 models 引入 db，避免循环导入

# 1. 提前占位：初始化 Redis 客户端
redis_client = None


def create_app():
    """
    这是 Flask 的应用工厂函数。
    每次调用这个函数，都会“生产”出一个配置好的 Flask 实例。
    """
    # 初始化 Flask 应用
    app = Flask(__name__)

    # 将 config.py 里写的数据库密码、Redis地址加载进来
    app.config.from_object(Config)

    # 2. 把数据库对象和当前生成的 app 绑定
    db.init_app(app)

    # 3. 初始化 Redis 连接
    # decode_responses=True 会自动把 Redis 里取出来的字节码转换成字符串，方便后续处理
    global redis_client
    try:
        redis_client = redis.from_url(app.config['REDIS_URL'], decode_responses=True)
    except Exception as e:
        print(f"警告：Redis 连接失败，防刷票缓存功能可能受限 ({e})")

    # ==========================================
    # [新增] 全局请求拦截器：实现小黑屋（黑名单）功能
    # ==========================================
    @app.before_request
    def check_banned_user():
        # 放行的白名单路由：这些页面不需要拦截（登录、登出、注册、静态文件如CSS/JS/图片）
        allowed_endpoints = ['auth.login', 'auth.logout', 'auth.register', 'static']

        # 如果访问的路由在白名单内，或者没有匹配到路由，直接放行
        if request.endpoint in allowed_endpoints or not request.endpoint:
            return

        # 检查当前是否有用户登录（从 session 中获取 user_id）
        user_id = session.get('user_id')
        if user_id:
            # 局部导入 User 模型，避免在初始化时与 models.py 发生循环依赖
            from app.models import User
            user = User.query.get(user_id)

            # 如果查到了这个用户，并且他的 is_banned 字段为 True
            if user and getattr(user, 'is_banned', False):
                session.clear()  # 强制踢下线（清空登录凭证）
                flash("🚨 您的账号已被限制使用系统，请联系系统管理员解除限制。", "danger")
                return redirect(url_for('auth.login'))

    # 4. 注册蓝图 (Blueprint)
    # 把我们写好的三大核心业务模块全部挂载到这辆“汽车”上

    from app.auth import auth_bp
    app.register_blueprint(auth_bp)  # 挂载：登录与注册模块

    from app.admin import admin_bp
    app.register_blueprint(admin_bp)  # 挂载：管理员后台模块

    from app.vote import vote_bp
    app.register_blueprint(vote_bp)  # 挂载：核心投票与防刷票模块

    from app.main import main_bp
    app.register_blueprint(main_bp)

    return app