from app import db
from datetime import datetime
from app.utils.datetime_helper import format_datetime


class AlertLevel:
    """告警级别兼容 shim"""
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'


class AlertType:
    """告警类型兼容 shim"""
    TASK_FAILURE = 'task_failure'
    RESOURCE_EXHAUSTION = 'resource_exhaustion'
    NODE_OFFLINE = 'node_offline'
    TRAINING_ANOMALY = 'training_anomaly'
    GPU_ERROR = 'gpu_error'
    GPU_LOW_UTILIZATION = 'gpu_low_utilization'
    MEMORY_HIGH_USAGE = 'memory_high_usage'
    LOSS_NOT_DECREASING = 'loss_not_decreasing'
    TRAINING_TIMEOUT = 'training_timeout'
    SYSTEM = 'system'


class AlertStatus:
    """告警状态兼容 shim"""
    ACTIVE = 'active'
    ACKNOWLEDGED = 'acknowledged'
    RESOLVED = 'resolved'


class AlertRule(db.Model):
    __tablename__ = 'alert_rules'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    alert_type = db.Column(db.String(50), nullable=False)
    level = db.Column(db.String(20), default='warning')
    is_enabled = db.Column(db.Boolean, default=True)
    condition = db.Column(db.JSON, nullable=False)
    actions = db.Column(db.JSON)
    cooldown_seconds = db.Column(db.Integer, default=300)
    last_triggered_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'alert_type': self.alert_type,
            'level': self.level,
            'is_enabled': self.is_enabled,
            'condition': self.condition,
            'actions': self.actions,
            'cooldown_seconds': self.cooldown_seconds,
            'last_triggered_at': format_datetime(self.last_triggered_at),
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at),
        }


class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    alert_type = db.Column(db.String(50), nullable=False)
    level = db.Column(db.String(20), default='warning')
    status = db.Column(db.String(20), default='active')
    task_id = db.Column(db.String(64), nullable=True)
    node_id = db.Column(db.String(64), nullable=True)
    pod_name = db.Column(db.String(255))
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    details = db.Column(db.JSON)
    rule_id = db.Column(db.Integer, db.ForeignKey('alert_rules.id'), nullable=True)
    acknowledged_by = db.Column(db.String(100))
    acknowledged_at = db.Column(db.DateTime)
    resolved_by = db.Column(db.String(100))
    resolved_at = db.Column(db.DateTime)
    resolution_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'alert_type': self.alert_type,
            'level': self.level,
            'status': self.status,
            'task_id': self.task_id,
            'node_id': self.node_id,
            'pod_name': self.pod_name,
            'title': self.title,
            'message': self.message,
            'details': self.details,
            'rule_id': self.rule_id,
            'acknowledged_by': self.acknowledged_by,
            'acknowledged_at': format_datetime(self.acknowledged_at),
            'resolved_by': self.resolved_by,
            'resolved_at': format_datetime(self.resolved_at),
            'resolution_note': self.resolution_note,
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at),
        }
