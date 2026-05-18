from app import db
from datetime import datetime
from app.utils.datetime_helper import format_datetime


class TaskMetric(db.Model):
    __tablename__ = 'task_metrics'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.String(64), db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, index=True)
    epoch = db.Column(db.Integer)
    step = db.Column(db.Integer)
    loss = db.Column(db.Float)
    accuracy = db.Column(db.Float)
    learning_rate = db.Column(db.Float)
    val_loss = db.Column(db.Float)
    val_accuracy = db.Column(db.Float)
    cpu_utilization = db.Column(db.Float)
    memory_used = db.Column(db.Float)
    gpu_utilization = db.Column(db.Float)
    gpu_memory_used = db.Column(db.Float)
    node_rank = db.Column(db.Integer)
    world_size = db.Column(db.Integer)
    throughput = db.Column(db.Float)
    custom_metrics = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'epoch': self.epoch,
            'step': self.step,
            'loss': self.loss,
            'accuracy': self.accuracy,
            'learning_rate': self.learning_rate,
            'val_loss': self.val_loss,
            'val_accuracy': self.val_accuracy,
            'cpu_utilization': self.cpu_utilization,
            'memory_used': self.memory_used,
            'gpu_utilization': self.gpu_utilization,
            'gpu_memory_used': self.gpu_memory_used,
            'node_rank': self.node_rank,
            'world_size': self.world_size,
            'throughput': self.throughput,
            'custom_metrics': self.custom_metrics,
            'timestamp': format_datetime(self.timestamp),
        }
