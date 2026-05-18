from app import db
from datetime import datetime
from app.utils.datetime_helper import format_datetime


class ModelTag(db.Model):
    __tablename__ = 'model_tags'
    model_id = db.Column(db.Integer, db.ForeignKey('models.id'), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id'), primary_key=True)


class Model(db.Model):
    __tablename__ = 'models'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    model_type = db.Column(db.String(50))
    framework = db.Column(db.String(50), default='PyTorch')
    source = db.Column(db.String(20), default='training')
    group_id = db.Column(db.Integer, db.ForeignKey('model_groups.id'), nullable=True)
    is_public = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', backref='models')
    versions = db.relationship('ModelVersion', backref='model', lazy='dynamic', cascade='all, delete-orphan')
    tags = db.relationship('Tag', secondary='model_tags', backref='models')
    group = db.relationship('ModelGroup', backref='models')

    def to_dict(self, include_versions=False, _version_count=None):
        if _version_count is None:
            _version_count = self.versions.count()
        latest = self.versions.order_by(ModelVersion.created_at.desc()).first()
        data = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'model_type': self.model_type,
            'framework': self.framework,
            'source': self.source,
            'group_id': self.group_id,
            'group_name': self.group.name if self.group else None,
            'is_public': self.is_public,
            'created_by': self.created_by,
            'creator_name': self.creator.username if self.creator else None,
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at),
            'tags': [tag.to_dict() for tag in self.tags],
            'version_count': _version_count,
            'latest_version': latest.version_number if latest else None,
            'latest_metrics': latest.metrics if latest else None,
        }
        if include_versions:
            data['versions'] = [v.to_dict() for v in self.versions.order_by(ModelVersion.created_at.desc())]
        return data


class ModelVersion(db.Model):
    __tablename__ = 'model_versions'

    id = db.Column(db.Integer, primary_key=True)
    model_id = db.Column(db.Integer, db.ForeignKey('models.id'), nullable=False)
    version_number = db.Column(db.String(20), nullable=False)
    version_name = db.Column(db.String(100))
    file_path = db.Column(db.String(500))
    file_size = db.Column(db.BigInteger, default=0)
    file_format = db.Column(db.String(20))
    model_structure = db.Column(db.JSON)
    metrics = db.Column(db.JSON)
    hyperparameters = db.Column(db.JSON)
    parent_version_id = db.Column(db.Integer, db.ForeignKey('model_versions.id'))
    # 训练来源关联
    task_id = db.Column(db.String(64), nullable=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey('datasets.id'), nullable=True)
    algorithm_version_id = db.Column(db.Integer, db.ForeignKey('algorithm_versions.id'), nullable=True)
    is_production = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.Text)

    creator = db.relationship('User', backref='model_versions')
    parent_version = db.relationship('ModelVersion', remote_side=[id], backref='child_versions')
    dataset = db.relationship('Dataset', backref='model_versions')
    algorithm_version = db.relationship('AlgorithmVersion', backref='model_versions')

    __table_args__ = (
        db.UniqueConstraint('model_id', 'version_number', name='uk_model_version'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'model_id': self.model_id,
            'model_name': self.model.name if self.model else None,
            'version_number': self.version_number,
            'version_name': self.version_name,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'file_format': self.file_format,
            'model_structure': self.model_structure,
            'metrics': self.metrics,
            'hyperparameters': self.hyperparameters,
            'parent_version_id': self.parent_version_id,
            'task_id': self.task_id,
            'dataset_id': self.dataset_id,
            'dataset_name': self.dataset.name if self.dataset else None,
            'algorithm_version_id': self.algorithm_version_id,
            'is_production': self.is_production,
            'created_by': self.created_by,
            'creator_name': self.creator.username if self.creator else None,
            'created_at': format_datetime(self.created_at),
            'description': self.description,
        }
