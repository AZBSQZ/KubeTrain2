from app import db
from datetime import datetime
from app.utils.datetime_helper import format_datetime


class K8sCluster(db.Model):
    __tablename__ = 'k8s_clusters'

    id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    description = db.Column(db.Text)
    api_server = db.Column(db.String(500))
    kubeconfig_path = db.Column(db.String(500))
    kubeconfig_content = db.Column(db.Text)
    auth_type = db.Column(db.String(20), default='kubeconfig')
    token = db.Column(db.Text)
    ca_cert = db.Column(db.Text)
    namespace = db.Column(db.String(100), default='kubetrain')
    pvc_name = db.Column(db.String(255), default='kubetrain-data-pvc')
    status = db.Column(db.String(20), default='unknown')
    status_message = db.Column(db.Text)
    node_count = db.Column(db.Integer, default=0)
    is_default = db.Column(db.Boolean, default=False)
    labels = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self, include_kubeconfig=False):
        data = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'api_server': self.api_server,
            'kubeconfig_path': self.kubeconfig_path,
            'namespace': self.namespace,
            'pvc_name': self.pvc_name,
            'status': self.status,
            'status_message': self.status_message,
            'node_count': self.node_count,
            'is_default': self.is_default,
            'labels': self.labels,
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at),
        }
        if include_kubeconfig:
            data['kubeconfig_content'] = self.kubeconfig_content
        return data
