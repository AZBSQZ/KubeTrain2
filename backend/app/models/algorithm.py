from app import db
from datetime import datetime
from app.utils.datetime_helper import format_datetime


class AlgorithmTag(db.Model):
    __tablename__ = 'algorithm_tags'
    algorithm_id = db.Column(db.Integer, db.ForeignKey('algorithms.id'), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id'), primary_key=True)


class Algorithm(db.Model):
    __tablename__ = 'algorithms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    algorithm_type = db.Column(db.String(50))
    framework = db.Column(db.String(50), default='PyTorch')
    is_public = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', backref='algorithms')
    versions = db.relationship('AlgorithmVersion', backref='algorithm', lazy='dynamic', cascade='all, delete-orphan')
    tags = db.relationship('Tag', secondary='algorithm_tags', backref='algorithms')

    def to_dict(self, include_versions=False, _version_count=None, _active_version=None):
        if _active_version is None:
            _active_version = self.versions.filter_by(is_active=True).first()
            if not _active_version:
                _active_version = self.versions.order_by(AlgorithmVersion.created_at.desc()).first()
        if _version_count is None:
            _version_count = self.versions.count()
        data = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'algorithm_type': self.algorithm_type,
            'framework': self.framework,
            'is_public': self.is_public,
            'created_by': self.created_by,
            'creator_name': self.creator.username if self.creator else None,
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at),
            'tags': [tag.to_dict() for tag in self.tags],
            'version_count': _version_count,
            'latest_version': _active_version.version_number if _active_version else None,
        }
        if include_versions:
            data['versions'] = [v.to_dict() for v in self.versions.order_by(AlgorithmVersion.created_at.desc())]
        return data


class AlgorithmVersion(db.Model):
    __tablename__ = 'algorithm_versions'

    id = db.Column(db.Integer, primary_key=True)
    algorithm_id = db.Column(db.Integer, db.ForeignKey('algorithms.id'), nullable=False)
    version_number = db.Column(db.String(20), nullable=False)
    version_name = db.Column(db.String(100))
    script_path = db.Column(db.String(500))
    script_content = db.Column(db.Text)
    parameters = db.Column(db.JSON)
    dependencies = db.Column(db.JSON)
    parent_version_id = db.Column(db.Integer, db.ForeignKey('algorithm_versions.id'))
    is_active = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.Text)

    creator = db.relationship('User', backref='algorithm_versions')
    parent_version = db.relationship('AlgorithmVersion', remote_side=[id], backref='child_versions')

    __table_args__ = (
        db.UniqueConstraint('algorithm_id', 'version_number', name='uk_algorithm_version'),
    )

    def to_dict(self, include_content=False):
        data = {
            'id': self.id,
            'algorithm_id': self.algorithm_id,
            'algorithm_name': self.algorithm.name if self.algorithm else None,
            'version_number': self.version_number,
            'version_name': self.version_name,
            'script_path': self.script_path,
            'parameters': self.parameters,
            'dependencies': self.dependencies,
            'parent_version_id': self.parent_version_id,
            'is_active': self.is_active,
            'created_by': self.created_by,
            'creator_name': self.creator.username if self.creator else None,
            'created_at': format_datetime(self.created_at),
            'description': self.description,
        }
        if include_content:
            data['script_content'] = self.script_content
        return data
