import os


class Config:
    # 1. Flask 安全密钥 (极其重要)
    # 用于给用户的密码“加盐”加密，以及保证登录状态 (Session) 不被伪造。
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_super_secret_key_voting_system_2026'

    # 2. MySQL 数据库连接配置
    # 填入了你提供的账号 root 和密码 123456。
    # 格式: mysql+pymysql://用户名:密码@地址:端口/我们要建的数据库名
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:123456@127.0.0.1:3306/online_voting_db'

    # 关闭 SQLAlchemy 的事件追踪，可以节省系统内存，提高性能
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 3. Redis 缓存连接配置
    # 填入了你提供的密码 123456。
    # 格式: redis://:密码@地址:端口/数据库编号 (0代表默认的第一个库)
    REDIS_URL = 'redis://:123456@127.0.0.1:6379/0'