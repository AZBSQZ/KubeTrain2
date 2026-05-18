from app import db
from datetime import datetime
from app.utils.datetime_helper import format_datetime


class DatasetTag(db.Model):
    __tablename__ = 'dataset_tags'
    dataset_id = db.Column(db.Integer, db.ForeignKey('datasets.id'), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id'), primary_key=True)


class Dataset(db.Model):
    __tablename__ = 'datasets'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    data_type = db.Column(db.String(50))
    source_type = db.Column(db.String(50), default='upload')
    original_filename = db.Column(db.String(255))
    total_size = db.Column(db.BigInteger, default=0)
    record_count = db.Column(db.Integer, default=0)
    is_public = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', backref='datasets')
    versions = db.relationship('DatasetVersion', backref='dataset', lazy='dynamic', cascade='all, delete-orphan')
    tags = db.relationship('Tag', secondary='dataset_tags', backref='datasets')

    def to_dict(self, include_versions=False, _version_count=None):
        if _version_count is None:
            _version_count = self.versions.count()
        data = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'data_type': self.data_type,
            'source_type': self.source_type,
            'original_filename': self.original_filename,
            'total_size': self.total_size,
            'record_count': self.record_count,
            'is_public': self.is_public,
            'created_by': self.created_by,
            'creator_name': self.creator.username if self.creator else None,
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at),
            'tags': [tag.to_dict() for tag in self.tags],
            'version_count': _version_count,
        }
        if include_versions:
            data['versions'] = [v.to_dict() for v in self.versions.order_by(DatasetVersion.created_at.desc())]
        return data


class DatasetVersion(db.Model):
    __tablename__ = 'dataset_versions'

    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey('datasets.id'), nullable=False)
    version_number = db.Column(db.String(20), nullable=False)
    version_name = db.Column(db.String(100))
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.BigInteger, default=0)
    file_hash = db.Column(db.String(64))
    record_count = db.Column(db.Integer, default=0)
    schema_info = db.Column(db.JSON)
    processing_info = db.Column(db.JSON)
    parent_version_id = db.Column(db.Integer, db.ForeignKey('dataset_versions.id'))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.Text)

    creator = db.relationship('User', backref='dataset_versions')
    parent_version = db.relationship('DatasetVersion', remote_side=[id], backref='child_versions')

    __table_args__ = (
        db.UniqueConstraint('dataset_id', 'version_number', name='uk_dataset_version'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'dataset_id': self.dataset_id,
            'dataset_name': self.dataset.name if self.dataset else None,
            'version_number': self.version_number,
            'version_name': self.version_name,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'file_hash': self.file_hash,
            'record_count': self.record_count,
            'schema_info': self.schema_info,
            'processing_info': self.processing_info,
            'parent_version_id': self.parent_version_id,
            'created_by': self.created_by,
            'creator_name': self.creator.username if self.creator else None,
            'created_at': format_datetime(self.created_at),
            'description': self.description,
        }
