from app import db
from datetime import datetime, timedelta
from app.utils.datetime_helper import format_datetime


class NodePool(db.Model):
    __tablename__ = 'node_pools'

    id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    description = db.Column(db.Text)
    provider = db.Column(db.String(20), default='bare_metal', nullable=False)
    cpu_per_node = db.Column(db.Integer, default=4)
    memory_per_node = db.Column(db.Integer, default=8192)
    gpu_per_node = db.Column(db.Integer, default=0)
    gpu_type = db.Column(db.String(100))
    max_nodes = db.Column(db.Integer, default=10)
    current_nodes = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='active', nullable=False)
    status_message = db.Column(db.Text)
    labels = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    nodes = db.relationship('PoolNode', backref='pool', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'provider': self.provider,
            'cpu_per_node': self.cpu_per_node,
            'memory_per_node': self.memory_per_node,
            'gpu_per_node': self.gpu_per_node,
            'gpu_type': self.gpu_type,
            'max_nodes': self.max_nodes,
            'current_nodes': self.current_nodes,
            'status': self.status,
            'status_message': self.status_message,
            'labels': self.labels,
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at),
        }


class PoolNode(db.Model):
    __tablename__ = 'pool_nodes'

    id = db.Column(db.String(64), primary_key=True)
    pool_id = db.Column(db.String(64), db.ForeignKey('node_pools.id'), nullable=False, index=True)
    node_type = db.Column(db.String(20), default='standalone', nullable=False)
    cluster_id = db.Column(db.String(64), db.ForeignKey('k8s_clusters.id'), nullable=True, index=True)
    name = db.Column(db.String(255), nullable=False)
    hostname = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    port = db.Column(db.Integer, default=8005)
    worker_id = db.Column(db.String(64))
    status = db.Column(db.String(20), default='offline', nullable=False)
    status_message = db.Column(db.Text)
    cpu_total = db.Column(db.Integer, default=0)
    memory_total = db.Column(db.Integer, default=0)
    gpu_total = db.Column(db.Integer, default=0)
    gpu_model = db.Column(db.String(100))
    storage_total = db.Column(db.Integer, default=0)
    cpu_allocated = db.Column(db.Integer, default=0)
    memory_allocated = db.Column(db.Integer, default=0)
    gpu_allocated = db.Column(db.Integer, default=0)
    cpu_utilization = db.Column(db.Float, default=0.0)
    memory_utilization = db.Column(db.Float, default=0.0)
    gpu_utilization = db.Column(db.Float, default=0.0)
    docker_available = db.Column(db.Boolean, default=False)
    tasks_running = db.Column(db.Integer, default=0)
    max_tasks = db.Column(db.Integer, default=2)
    labels = db.Column(db.JSON)
    capabilities = db.Column(db.JSON)
    gpu_details = db.Column(db.JSON)
    container_runtime = db.Column(db.String(100))
    os_info = db.Column(db.JSON)
    agent_version = db.Column(db.String(50))
    python_version = db.Column(db.String(50))
    cuda_version = db.Column(db.String(50))
    nccl_available = db.Column(db.Boolean, default=False)
    network_bandwidth_mbps = db.Column(db.Integer, default=0)
    heartbeat_interval = db.Column(db.Integer, default=30)
    registered_at = db.Column(db.DateTime)
    deregistered_at = db.Column(db.DateTime)
    last_heartbeat = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    task_slots = db.relationship('WorkerTaskSlot', backref='worker', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def cpu_available(self):
        return max(0, self.cpu_total - self.cpu_allocated)

    @property
    def memory_available(self):
        return max(0, self.memory_total - self.memory_allocated)

    @property
    def gpu_available(self):
        return max(0, self.gpu_total - self.gpu_allocated)

    def is_online(self, timeout_seconds=90):
        if self.node_type == 'k8s_node':
            return self.status in ('idle', 'busy')
        if not self.last_heartbeat:
            return False
        return datetime.utcnow() - self.last_heartbeat < timedelta(seconds=timeout_seconds)

    def can_accept_task(self, cpu_req=0, mem_req=0, gpu_req=0, required_caps=None):
        if self.status in ('offline', 'error'):
            return False
        if not self.is_online():
            return False
        if self.tasks_running >= self.max_tasks:
            return False
        if self.cpu_available < cpu_req:
            return False
        if self.memory_available < mem_req:
            return False
        if self.gpu_available < gpu_req:
            return False
        if required_caps:
            worker_caps = set(self.capabilities or [])
            if not set(required_caps).issubset(worker_caps):
                return False
        return True

    def allocate_slot(self, task_id, cpu=0, memory=0, gpu=0):
        self.cpu_allocated += cpu
        self.memory_allocated += memory
        self.gpu_allocated += gpu
        self.tasks_running += 1

    def release_slot(self, task_id, cpu=0, memory=0, gpu=0):
        self.cpu_allocated = max(0, self.cpu_allocated - cpu)
        self.memory_allocated = max(0, self.memory_allocated - memory)
        self.gpu_allocated = max(0, self.gpu_allocated - gpu)
        self.tasks_running = max(0, self.tasks_running - 1)

    def to_dict(self):
        return {
            'id': self.id,
            'pool_id': self.pool_id,
            'node_type': self.node_type,
            'cluster_id': self.cluster_id,
            'name': self.name,
            'hostname': self.hostname,
            'ip_address': self.ip_address,
            'port': self.port,
            'worker_id': self.worker_id,
            'status': self.status,
            'is_online': self.is_online(),
            'status_message': self.status_message,
            'cpu_total': self.cpu_total,
            'memory_total': self.memory_total,
            'gpu_total': self.gpu_total,
            'gpu_model': self.gpu_model,
            'gpu_details': self.gpu_details,
            'storage_total': self.storage_total,
            'cpu_allocated': self.cpu_allocated,
            'memory_allocated': self.memory_allocated,
            'gpu_allocated': self.gpu_allocated,
            'cpu_available': self.cpu_available,
            'memory_available': self.memory_available,
            'gpu_available': self.gpu_available,
            'cpu_utilization': self.cpu_utilization,
            'memory_utilization': self.memory_utilization,
            'gpu_utilization': self.gpu_utilization,
            'docker_available': self.docker_available,
            'container_runtime': self.container_runtime,
            'tasks_running': self.tasks_running,
            'max_tasks': self.max_tasks,
            'slots_available': max(0, self.max_tasks - self.tasks_running),
            'labels': self.labels,
            'capabilities': self.capabilities,
            'os_info': self.os_info,
            'agent_version': self.agent_version,
            'python_version': self.python_version,
            'cuda_version': self.cuda_version,
            'nccl_available': self.nccl_available,
            'heartbeat_interval': self.heartbeat_interval,
            'registered_at': format_datetime(self.registered_at),
            'last_heartbeat': format_datetime(self.last_heartbeat),
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at),
        }


class WorkerTaskSlot(db.Model):
    __tablename__ = 'worker_task_slots'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    worker_id = db.Column(db.String(64), db.ForeignKey('pool_nodes.id'), nullable=False, index=True)
    task_id = db.Column(db.String(64), nullable=False, index=True)
    cpu_allocated = db.Column(db.Integer, default=0)
    memory_allocated = db.Column(db.Integer, default=0)
    gpu_allocated = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='allocated')
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    released_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'worker_id': self.worker_id,
            'task_id': self.task_id,
            'cpu_allocated': self.cpu_allocated,
            'memory_allocated': self.memory_allocated,
            'gpu_allocated': self.gpu_allocated,
            'status': self.status,
            'assigned_at': format_datetime(self.assigned_at),
            'released_at': format_datetime(self.released_at),
        }
