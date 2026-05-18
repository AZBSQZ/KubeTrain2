from app import db
from datetime import datetime
from app.utils.datetime_helper import format_datetime


class ModelGroup(db.Model):
    __tablename__ = 'model_groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', backref='model_groups')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'model_count': len(self.models),
            'created_by': self.created_by,
            'creator_name': self.creator.username if self.creator else None,
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at),
        }
