"""操作日志模型"""
from app import db
from datetime import datetime


class OperationLog(db.Model):
    """操作日志 - 记录系统中所有关键操作"""
    __tablename__ = 'operation_logs'

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    username = db.Column(db.String(50))
    operation_type = db.Column(db.String(50), nullable=False)  # create/update/delete/login/logout/submit/cancel
    module = db.Column(db.String(50), nullable=False)  # auth/users/datasets/algorithms/models/tasks/workers/alerts
    target_type = db.Column(db.String(50))  # dataset/algorithm/model/task/user/worker
    target_id = db.Column(db.String(50))  # 目标ID（字符串以支持UUID）
    target_name = db.Column(db.String(200))  # 目标名称
    action = db.Column(db.String(100), nullable=False)  # 操作描述
    detail = db.Column(db.JSON)  # 详细信息
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    result = db.Column(db.String(20), default='success')  # success/failure
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 关联
    user = db.relationship('User', backref='operation_logs', lazy='select')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.username,
            'operation_type': self.operation_type,
            'module': self.module,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'target_name': self.target_name,
            'action': self.action,
            'detail': self.detail,
            'ip_address': self.ip_address,
            'result': self.result,
            'error_message': self.error_message,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }
