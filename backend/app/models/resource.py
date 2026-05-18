from app import db
from datetime import datetime
from app.utils.datetime_helper import format_datetime


class ResourceNode(db.Model):
    __tablename__ = 'resource_nodes'

    id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    hostname = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    pool_id = db.Column(db.String(64), nullable=True, index=True)
    status = db.Column(db.String(20), default='online', nullable=False)
    gpu_total = db.Column(db.Integer, default=0)
    gpu_available = db.Column(db.Integer, default=0)
    gpu_model = db.Column(db.String(100))
    gpu_memory = db.Column(db.Integer, default=0)
    cpu_total = db.Column(db.Integer, default=0)
    cpu_available = db.Column(db.Integer, default=0)
    memory_total = db.Column(db.Integer, default=0)
    memory_available = db.Column(db.Integer, default=0)
    storage_total = db.Column(db.Integer, default=0)
    storage_available = db.Column(db.Integer, default=0)
    cpu_utilization = db.Column(db.Float, default=0.0)
    memory_utilization = db.Column(db.Float, default=0.0)
    gpu_utilization = db.Column(db.Float, default=0.0)
    docker_available = db.Column(db.Boolean, default=False)
    labels = db.Column(db.JSON)
    last_heartbeat = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    allocations = db.relationship('ResourceAllocation', backref='node', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'hostname': self.hostname,
            'ip_address': self.ip_address,
            'pool_id': self.pool_id,
            'status': self.status,
            'gpu_total': self.gpu_total,
            'gpu_available': self.gpu_available,
            'gpu_model': self.gpu_model,
            'gpu_memory': self.gpu_memory,
            'cpu_total': self.cpu_total,
            'cpu_available': self.cpu_available,
            'memory_total': self.memory_total,
            'memory_available': self.memory_available,
            'storage_total': self.storage_total,
            'storage_available': self.storage_available,
            'cpu_utilization': self.cpu_utilization,
            'memory_utilization': self.memory_utilization,
            'gpu_utilization': self.gpu_utilization,
            'docker_available': self.docker_available,
            'labels': self.labels,
            'last_heartbeat': format_datetime(self.last_heartbeat),
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at),
        }


class ResourceAllocation(db.Model):
    __tablename__ = 'resource_allocations'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.String(64), db.ForeignKey('tasks.id'), nullable=False, index=True)
    node_id = db.Column(db.String(64), db.ForeignKey('resource_nodes.id'), nullable=True)
    quota_id = db.Column(db.Integer, db.ForeignKey('resource_quotas.id'), nullable=True, index=True)
    task = db.relationship('Task', foreign_keys=[task_id], lazy='joined')
    node = db.relationship('ResourceNode', foreign_keys=[node_id], lazy='joined')
    quota = db.relationship('ResourceQuota', foreign_keys=[quota_id], lazy='joined')
    gpu_allocated = db.Column(db.Integer, default=0)
    cpu_allocated = db.Column(db.Integer, default=0)
    memory_allocated = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    allocated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    released_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'task_name': self.task.name if self.task else None,
            'node_id': self.node_id,
            'node_name': self.node.name if self.node else None,
            'quota_id': self.quota_id,
            'quota_name': self.quota.name if self.quota else None,
            'gpu_allocated': self.gpu_allocated,
            'cpu_allocated': self.cpu_allocated,
            'memory_allocated': self.memory_allocated,
            'is_active': self.is_active,
            'created_by': self.task.created_by if self.task else None,
            'allocated_at': format_datetime(self.allocated_at),
            'released_at': format_datetime(self.released_at),
        }


class ClusterResource(db.Model):
    __tablename__ = 'cluster_resources'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    total_nodes = db.Column(db.Integer, default=0)
    online_nodes = db.Column(db.Integer, default=0)
    total_gpus = db.Column(db.Integer, default=0)
    available_gpus = db.Column(db.Integer, default=0)
    total_cpus = db.Column(db.Integer, default=0)
    available_cpus = db.Column(db.Integer, default=0)
    total_memory = db.Column(db.Integer, default=0)
    available_memory = db.Column(db.Integer, default=0)
    avg_cpu_utilization = db.Column(db.Float, default=0.0)
    avg_memory_utilization = db.Column(db.Float, default=0.0)
    avg_gpu_utilization = db.Column(db.Float, default=0.0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'total_nodes': self.total_nodes,
            'online_nodes': self.online_nodes,
            'total_gpus': self.total_gpus,
            'available_gpus': self.available_gpus,
            'total_cpus': self.total_cpus,
            'available_cpus': self.available_cpus,
            'total_memory': self.total_memory,
            'available_memory': self.available_memory,
            'avg_cpu_utilization': self.avg_cpu_utilization,
            'avg_memory_utilization': self.avg_memory_utilization,
            'avg_gpu_utilization': self.avg_gpu_utilization,
            'updated_at': format_datetime(self.updated_at),
        }


class ResourceQuota(db.Model):
    __tablename__ = 'resource_quotas'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    description = db.Column(db.Text)
    pool_id = db.Column(db.String(64), nullable=True, index=True)
    max_gpus = db.Column(db.Integer, default=0)
    max_cpus = db.Column(db.Integer, default=0)
    max_memory = db.Column(db.Integer, default=0)
    max_tasks = db.Column(db.Integer, default=10)
    used_gpus = db.Column(db.Integer, default=0)
    used_cpus = db.Column(db.Integer, default=0)
    used_memory = db.Column(db.Integer, default=0)
    used_tasks = db.Column(db.Integer, default=0)
    is_enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'pool_id': self.pool_id,
            'max_gpus': self.max_gpus,
            'max_cpus': self.max_cpus,
            'max_memory': self.max_memory,
            'max_tasks': self.max_tasks,
            'used_gpus': self.used_gpus,
            'used_cpus': self.used_cpus,
            'used_memory': self.used_memory,
            'used_tasks': self.used_tasks,
            'is_enabled': self.is_enabled,
            'gpu_usage_percent': round(self.used_gpus / self.max_gpus * 100, 1) if self.max_gpus > 0 else 0,
            'cpu_usage_percent': round(self.used_cpus / self.max_cpus * 100, 1) if self.max_cpus > 0 else 0,
            'memory_usage_percent': round(self.used_memory / self.max_memory * 100, 1) if self.max_memory > 0 else 0,
            'task_usage_percent': round(self.used_tasks / self.max_tasks * 100, 1) if self.max_tasks > 0 else 0,
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at),
        }

    def check_quota(self, gpu_req=0, cpu_req=0, mem_req=0):
        if not self.is_enabled:
            return True, "Quota disabled"
        issues = []
        if self.max_gpus > 0 and self.used_gpus + gpu_req > self.max_gpus:
            issues.append(f"GPU quota exceeded: {self.used_gpus}+{gpu_req}/{self.max_gpus}")
        if self.max_cpus > 0 and self.used_cpus + cpu_req > self.max_cpus:
            issues.append(f"CPU quota exceeded: {self.used_cpus}+{cpu_req}/{self.max_cpus}")
        if self.max_memory > 0 and self.used_memory + mem_req > self.max_memory:
            issues.append(f"Memory quota exceeded: {self.used_memory}+{mem_req}/{self.max_memory}")
        if self.max_tasks > 0 and self.used_tasks + 1 > self.max_tasks:
            issues.append(f"Task quota exceeded: {self.used_tasks}+1/{self.max_tasks}")
        if issues:
            return False, "; ".join(issues)
        return True, "OK"
