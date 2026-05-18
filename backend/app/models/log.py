from app import db
from datetime import datetime
from app.utils.datetime_helper import format_datetime


class LogLevel:
    DEBUG = 'debug'
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'


class TaskLog(db.Model):
    __tablename__ = 'task_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.String(64), db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, index=True)
    level = db.Column(db.String(20), default='info')
    source = db.Column(db.String(100))
    message = db.Column(db.Text, nullable=False)
    pod_name = db.Column(db.String(255))
    container_name = db.Column(db.String(100))
    epoch = db.Column(db.Integer)
    extra_data = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'level': self.level,
            'source': self.source,
            'message': self.message,
            'pod_name': self.pod_name,
            'container_name': self.container_name,
            'epoch': self.epoch,
            'extra_data': self.extra_data,
            'timestamp': format_datetime(self.timestamp),
        }
