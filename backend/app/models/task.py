from app import db
from datetime import datetime
from app.utils.datetime_helper import format_datetime


class TaskStatus:
    PENDING = 'pending'
    QUEUED = 'queued'
    ASSIGNED = 'assigned'
    STARTING = 'starting'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class ParallelMode:
    SINGLE = 'single'
    DDP = 'ddp'
    FSDP = 'fsdp'


class Task(db.Model):
    __tablename__ = 'tasks'

    id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)

    status = db.Column(db.String(20), default='pending', nullable=False, index=True)
    priority = db.Column(db.Integer, default=5)

    execution_mode = db.Column(db.String(20), default='auto', nullable=False)
    assigned_worker_id = db.Column(db.String(64), nullable=True, index=True)

    parallel_mode = db.Column(db.String(20), default='single', nullable=False)
    num_nodes = db.Column(db.Integer, default=1)
    gpus_per_node = db.Column(db.Integer, default=1)
    nproc_per_node = db.Column(db.Integer, default=1)

    training_script = db.Column(db.String(500), nullable=False)
    training_args = db.Column(db.JSON)
    environment = db.Column(db.JSON)

    dataset_id = db.Column(db.Integer, db.ForeignKey('datasets.id'), nullable=True)
    algorithm_id = db.Column(db.Integer, db.ForeignKey('algorithms.id'), nullable=True)
    algorithm_version_id = db.Column(db.Integer, db.ForeignKey('algorithm_versions.id'), nullable=True)

    base_model_id = db.Column(db.Integer, db.ForeignKey('models.id'), nullable=True)
    base_model_path = db.Column(db.String(500))

    dataset_path = db.Column(db.String(500))
    output_path = db.Column(db.String(500))
    checkpoint_path = db.Column(db.String(500))
    pip_packages = db.Column(db.Text)

    cpu_request = db.Column(db.String(20), default='1')
    cpu_limit = db.Column(db.String(20), default='2')
    memory_request = db.Column(db.String(20), default='2Gi')
    memory_limit = db.Column(db.String(20), default='4Gi')
    gpu_limit = db.Column(db.Integer, default=0)

    job_name = db.Column(db.String(255))
    pod_names = db.Column(db.JSON)

    current_epoch = db.Column(db.Integer, default=0)
    total_epochs = db.Column(db.Integer)
    progress_percent = db.Column(db.Float, default=0.0)

    final_loss = db.Column(db.Float)
    final_accuracy = db.Column(db.Float)
    best_metric = db.Column(db.JSON)
    model_path = db.Column(db.String(500))

    retry_count = db.Column(db.Integer, default=0)
    max_retries = db.Column(db.Integer, default=3)
    error_message = db.Column(db.Text)

    # Pipeline fields
    pipeline_config = db.Column(db.JSON)       # Pipeline definition: {stages: [{name, algorithm_version_id, model_version_id, config}]}
    parent_task_id = db.Column(db.String(64), db.ForeignKey('tasks.id'), nullable=True, index=True)
    stage_index = db.Column(db.Integer)         # 0-based stage index for child tasks
    pipeline_progress = db.Column(db.JSON)      # {current_stage: 0, stages: [{task_id, status, model_path}]}

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    queued_at = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    duration = db.Column(db.Integer)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    dataset = db.relationship('Dataset', backref='tasks')
    algorithm = db.relationship('Algorithm', backref='tasks')
    algorithm_version = db.relationship('AlgorithmVersion', backref='tasks')
    base_model = db.relationship('Model', backref='tasks')
    creator = db.relationship('User', backref='tasks')
    parent_task = db.relationship('Task', remote_side=[id], backref=db.backref('child_tasks', lazy='dynamic'))
    logs = db.relationship('TaskLog', backref='task', lazy='dynamic', cascade='all, delete-orphan')
    metrics = db.relationship('TaskMetric', backref='task', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'priority': self.priority,
            'execution_mode': self.execution_mode,
            'assigned_worker_id': self.assigned_worker_id,
            'parallel_mode': self.parallel_mode,
            'num_nodes': self.num_nodes,
            'gpus_per_node': self.gpus_per_node,
            'nproc_per_node': self.nproc_per_node,
            'training_script': self.training_script,
            'training_args': self.training_args,
            'environment': self.environment,
            'dataset_id': self.dataset_id,
            'dataset_name': self.dataset.name if self.dataset else None,
            'algorithm_id': self.algorithm_id,
            'algorithm_name': self.algorithm.name if self.algorithm else None,
            'algorithm_version_id': self.algorithm_version_id,
            'base_model_id': self.base_model_id,
            'base_model_path': self.base_model_path,
            'dataset_path': self.dataset_path,
            'output_path': self.output_path,
            'checkpoint_path': self.checkpoint_path,
            'pip_packages': self.pip_packages,
            'cpu_request': self.cpu_request,
            'cpu_limit': self.cpu_limit,
            'memory_request': self.memory_request,
            'memory_limit': self.memory_limit,
            'gpu_limit': self.gpu_limit,
            'job_name': self.job_name,
            'pod_names': self.pod_names,
            'current_epoch': self.current_epoch,
            'total_epochs': self.total_epochs,
            'progress_percent': self.progress_percent,
            'final_loss': self.final_loss,
            'final_accuracy': self.final_accuracy,
            'best_metric': self.best_metric,
            'model_path': self.model_path,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'error_message': self.error_message,
            'pipeline_config': self.pipeline_config,
            'parent_task_id': self.parent_task_id,
            'stage_index': self.stage_index,
            'pipeline_progress': self.pipeline_progress,
            'is_pipeline': bool(self.pipeline_config and self.pipeline_config.get('stages')),
            'is_stage_task': self.parent_task_id is not None,
            'created_by': self.created_by,
            'creator_name': self.creator.username if self.creator else None,
            'created_at': format_datetime(self.created_at),
            'queued_at': format_datetime(self.queued_at),
            'started_at': format_datetime(self.started_at),
            'completed_at': format_datetime(self.completed_at),
            'duration': self.duration,
            'updated_at': format_datetime(self.updated_at),
        }
