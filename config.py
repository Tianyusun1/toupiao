import os
from datetime import timedelta


class Config:
    # 1. Flask 安全密钥 - [核心修复]
    # 必须是一个绝对固定的字符串。
    # 注意：不要使用 os.urandom，否则服务器热重载时密钥改变，Session 立即失效。
    SECRET_KEY = 'voter_system_2026_fixed_secret_key_v1'

    # 2. Session & Cookie 行为控制 - [深度优化]
    # 确保 Session 能够跨页面读取并被浏览器接受
    SESSION_COOKIE_NAME = 'voting_session_id'
    SESSION_COOKIE_PATH = '/'  # 确保在根路径下可用
    SESSION_COOKIE_HTTPONLY = True  # 防止脚本攻击，增加安全性

    # 本地开发环境下，SameSite 设为 Lax，Secure 设为 False
    # 这样浏览器才会在 127.0.0.1 或 localhost 下允许存储 Cookie
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False

    # 设置 Session 过期时间
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)

    # 3. MySQL 数据库连接配置
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:123456@127.0.0.1:3306/online_voting_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 4. Redis 缓存连接配置
    REDIS_URL = 'redis://127.0.0.1:6379/0'

    # 5. RSA 非对称加密安全配置
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

    # 6. 上传配置
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024