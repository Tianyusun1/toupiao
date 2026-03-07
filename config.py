import os


class Config:
    # 1. Flask 安全密钥 (极其重要)
    # 用于保证登录状态 (Session) 的安全，防止被伪造。
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_super_secret_key_voting_system_2026'

    # 2. MySQL 数据库连接配置
    # 使用你提供的账号 root 和密码 123456。
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:123456@127.0.0.1:3306/online_voting_db'

    # 关闭 SQLAlchemy 的事件追踪，提高性能并节省内存
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 3. Redis 缓存连接配置
    # 用于高并发下的“防刷票限流”，限制同一用户/IP的请求频率。
    REDIS_URL = 'redis://:123456@127.0.0.1:6379/0'

    # 4. RSA 非对称加密安全配置 (新增)
    # 这是后端的【私钥】，绝对不能泄露给前端！
    # 它必须与 login.html 里的 PUBLIC_KEY（公钥）成对使用。
    # 如果你还没有生成密钥对，请确保此处填写的私钥格式正确。
    RSA_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIICWwIBAAKBgQCs10mGwu4ex3jHFDpaQp+FNAirec+UVkdR6pRcdViwSD1FQnpN
RrxrTJGy4XeubsTt8MygeOYWoJLJqJk9Oezi5hJx5fFvA7eHeo0Q6txHNFlynf19
MH4Hb7dRBt05PAoZcjiZJa/J1WOehfvp19IrnHBEiIcGyxA+qaoBgWIGcwIDAQAB
AoGACqKKjySyYylx6In5lzEvQJJ1kBuEJsPySnuNGm1MAjjHsFnJTbTzBgUll+Sg
qRZ+vodJB/y4Z58EuSzLFQXZ6fgMU3MeEazVGOl7ptrLgmOjgG84L0dMX9hekIb0
wmmWkDQeaSq2fvfNiB9OMSa1WhelSJUTKrcsiI46+RlikmUCQQC3Fz9OETg2glk4
8wE8hdT2DiWMl8uZIALauQneECn8XkqktS5ScR8/qXmHs+mfV6LQi9hsTewt/tet
bUTgk629AkEA8ask6n/TlQHGU9l15Nj1Q+tfLbxBKW9Gx9Fu1e+aco4kZlACOiRv
ls5utXHnNtPuyLG3OJWtXgtLETeKvRPP7wJAcLnRciFL+NOcV2HWWwsTKUNgfwVe
hzKcT0op9x0AnK75Sht7H6siUDHp71En/8EXL0tKvrPjPBZxeAeUpqiGCQJAQlD0
kGUDaqBSDDBgaawfocO1GpfOSdB/W9Xc1FgrycO3uVu7QLk+5eM//gqDqEf//pLF
9IEeUfBHaTIUoE4PgQJAR//k62IqopsgHguS1yMmQNh2lpZEbcdlqhGWi92xPyZK
0KFp2I4K1AIpavGo6lE6tE3d2jw9PXajcRLj86vnEg==
-----END RSA PRIVATE KEY-----"""

    # 5. 上传配置
    # 限制上传图片的最大尺寸为 5MB，防止恶意上传超大文件挤爆磁盘。
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024