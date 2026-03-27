from flask import Flask, session, request, redirect, url_for, flash
import redis
from config import Config
from app.models import db

# 1. 初始化 Redis 客户端占位
redis_client = None

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 2. 绑定数据库
    db.init_app(app)

    # 3. 初始化 Redis 连接
    global redis_client
    try:
        redis_client = redis.from_url(
            app.config.get('REDIS_URL', 'redis://localhost:6379/0'),
            decode_responses=True
        )
    except Exception as e:
        print(f"警告：Redis 连接失败 ({e})")

    # ==========================================
    # [终极修复] 全局请求拦截器
    # ==========================================
    @app.before_request
    def check_auth_and_banned():
        # 1. 静态资源和图标直接放行（最高优先级）
        if request.path.startswith('/static') or request.path == '/favicon.ico':
            return

        # 2. 定义【绝对白名单】路径
        # 注意：这里直接用路径判断，绕过可能识别失败的 endpoint
        public_paths = ['/auth/login', '/auth/register', '/register', '/login']
        if request.path in public_paths:
            return

        # 3. 检查登录状态
        user_id = session.get('user_id')

        # 4. 如果未登录，且访问的不是白名单，强制去登录
        if user_id is None:
            # 调试打印，看看是谁被拦截了
            print(f"【拦截器】未登录访问 {request.path}，跳转到登录页")
            return redirect(url_for('auth.login'))

        # 5. 已登录用户：检查黑名单
        from app.models import User
        try:
            user = User.query.get(int(user_id))
            if user:
                if getattr(user, 'is_banned', False):
                    session.clear()
                    flash("🚨 您的账号已被限制使用系统。", "danger")
                    return redirect(url_for('auth.login'))
            else:
                # 查无此人，清理无效 session
                session.clear()
                return redirect(url_for('auth.login'))
        except Exception as e:
            print(f"【错误】拦截器查询数据库失败: {e}")
            return

    # 4. 注册蓝图
    from app.auth import auth_bp
    from app.admin import admin_bp
    from app.vote import vote_bp
    from app.main import main_bp

    # 核心：确保蓝图注册顺序
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(vote_bp)
    app.register_blueprint(main_bp)

    return app