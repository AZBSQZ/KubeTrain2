from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app import db
from app.models.tag import Tag

tags_bp = Blueprint('tags', __name__)


@tags_bp.route('', methods=['GET'])
@jwt_required()
def list_tags():
    tags = Tag.query.order_by(Tag.name.asc()).all()
    return jsonify({'code': 200, 'data': [t.to_dict() for t in tags]})


@tags_bp.route('', methods=['POST'])
@jwt_required()
def create_tag():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '标签名称不能为空'}), 400
    if Tag.query.filter_by(name=name).first():
        return jsonify({'code': 400, 'message': '标签已存在'}), 400
    tag = Tag(name=name, color=data.get('color', '#409eff'))
    db.session.add(tag)
    db.session.commit()
    return jsonify({'code': 200, 'message': '标签创建成功', 'data': tag.to_dict()})


@tags_bp.route('/<int:tag_id>', methods=['DELETE'])
@jwt_required()
def delete_tag(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    db.session.delete(tag)
    db.session.commit()
    return jsonify({'code': 200, 'message': '删除成功'})
