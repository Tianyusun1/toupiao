from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import hashlib

db = SQLAlchemy()


class User(db.Model):
    """用户表：支持注册审核与个人主页"""
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='student')  # 'student' 或 'admin'

    # --- 身份硬核绑定字段 ---
    department = db.Column(db.String(50))  # 学院
    major = db.Column(db.String(50))  # 专业
    class_name = db.Column(db.String(50))  # 班级
    entry_year = db.Column(db.String(10))  # 入学年份

    # --- 审核状态与个人主页 ---
    is_approved = db.Column(db.Boolean, default=False)  # 是否通过管理员审核
    bio = db.Column(db.Text)  # 个人简介 (用于个人主页)
    avatar = db.Column(db.String(100), default='default.png')  # 头像路径
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Election(db.Model):
    """选举/提议项目表：支持 UGC 提议与多选配置"""
    __tablename__ = 'elections'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # --- 图片上传海报字段 ---
    image_url = db.Column(db.String(255), nullable=True)

    # --- 多选配置 ---
    is_multi_choice = db.Column(db.Boolean, default=False)  # 新增：是否支持多选

    # --- UGC 提议逻辑 ---
    proposer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    review_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    admin_feedback = db.Column(db.Text)

    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='draft')  # draft, active, ended
    is_official = db.Column(db.Boolean, default=False)


class Candidate(db.Model):
    """候选人/选项表：支持独立附件与资质审核"""
    __tablename__ = 'candidates'
    id = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey('elections.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(50))
    manifesto = db.Column(db.Text)

    # --- 每个选项独立上传图片 ---
    image_url = db.Column(db.String(255), nullable=True)

    # --- 资质审核 ---
    is_qualified = db.Column(db.Boolean, default=False)
    qual_materials = db.Column(db.Text)


class VoteRecord(db.Model):
    """投票记录表：支持安全性哈希凭证"""
    __tablename__ = 'vote_records'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    election_id = db.Column(db.Integer, db.ForeignKey('elections.id'), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    vote_time = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50))

    # --- 投票安全凭证 (SHA-256) ---
    vote_hash = db.Column(db.String(64), unique=True)

    # 注意：为了支持多选（一个用户对同一个项目产生多条针对不同候选人的记录），
    # 我们移除了原有的 UniqueConstraint('user_id', 'election_id') 物理约束。
    # 逻辑层面的“一人只能投一次”将在接口中通过代码控制。

    def generate_hash(self):
        """
        生成唯一的投票凭证。
        增加 candidate_id 参与计算，确保多选时每条记录产生不同的哈希指纹。
        """
        raw_str = f"{self.user_id}-{self.election_id}-{self.candidate_id}-{self.vote_time}"
        self.vote_hash = hashlib.sha256(raw_str.encode()).hexdigest()