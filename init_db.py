import pymysql
from flask import Flask
from config import Config
from app.models import db, User


def reset_database():
    """强制重置数据库：删除旧库并新建"""
    print(">>> 正在连接 MySQL 服务器...")
    try:
        conn = pymysql.connect(host='127.0.0.1', user='root', password='123456', port=3306)  # 注意填对密码
        cursor = conn.cursor()

        print(">>> 正在清理旧数据库...")
        cursor.execute("DROP DATABASE IF EXISTS online_voting_db;")

        print(">>> 正在创建全新数据库...")
        cursor.execute("CREATE DATABASE online_voting_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")

        conn.commit()
        cursor.close()
        conn.close()
        print(">>> 数据库重置成功！")
    except Exception as e:
        print(f"!!! 操作失败: {e}")
        exit(1)


def init_tables_and_admin():
    """初始化全新的表结构和管理员"""
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        print(">>> 正在同步最新的 models.py 字段到数据库...")
        db.create_all()

        print(">>> 正在初始化超级管理员账号...")
        # 注意：这里要符合我们最新的 User 模型字段
        admin = User(
            student_id='admin',
            name='系统管理员',
            role='admin',
            department='校团委',
            is_approved=True  # 管理员默认已审核
        )
        admin.set_password('123456')
        db.session.add(admin)
        db.session.commit()
        print(">>> 管理员创建成功！账号: admin, 密码: 123456")


if __name__ == '__main__':
    print("=== 开始执行数据库强制同步 ===")
    reset_database()
    init_tables_and_admin()
    print("=== 同步完成，你的数据库现在是最新版了！ ===")