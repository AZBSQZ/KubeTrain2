from app import db
from datetime import datetime
from app.utils.datetime_helper import format_datetime
from werkzeug.security import generate_password_hash, check_password_hash


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(100))
    role = db.Column(db.Enum('admin', 'user', 'guest'), default='user')
    avatar = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    quota_id = db.Column(db.Integer, db.ForeignKey('resource_quotas.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    quota = db.relationship('ResourceQuota', foreign_keys=[quota_id], backref='users')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'avatar': self.avatar,
            'is_active': self.is_active,
            'quota_id': self.quota_id,
            'quota_name': self.quota.name if self.quota else None,
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at),
            'last_login': format_datetime(self.last_login),
        }
