from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.model_group import ModelGroup

model_groups_bp = Blueprint('model_groups', __name__)


def _get_user_id():
    try:
        return int(get_jwt_identity())
    except Exception:
        return None


@model_groups_bp.route('', methods=['GET'])
@jwt_required()
def list_groups():
    groups = ModelGroup.query.order_by(ModelGroup.created_at.desc()).all()
    return jsonify({'code': 200, 'data': [g.to_dict() for g in groups]})


@model_groups_bp.route('', methods=['POST'])
@jwt_required()
def create_group():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '分组名称不能为空'}), 400
    if ModelGroup.query.filter_by(name=name).first():
        return jsonify({'code': 400, 'message': '分组名称已存在'}), 400
    group = ModelGroup(name=name, description=data.get('description', ''), created_by=_get_user_id())
    db.session.add(group)
    db.session.commit()
    return jsonify({'code': 200, 'message': '创建成功', 'data': group.to_dict()})


@model_groups_bp.route('/<int:group_id>', methods=['PUT'])
@jwt_required()
def update_group(group_id):
    group = ModelGroup.query.get_or_404(group_id)
    data = request.get_json() or {}
    if 'name' in data:
        group.name = data['name']
    if 'description' in data:
        group.description = data['description']
    db.session.commit()
    return jsonify({'code': 200, 'message': '更新成功', 'data': group.to_dict()})


@model_groups_bp.route('/<int:group_id>', methods=['DELETE'])
@jwt_required()
def delete_group(group_id):
    group = ModelGroup.query.get_or_404(group_id)
    db.session.delete(group)
    db.session.commit()
    return jsonify({'code': 200, 'message': '删除成功'})
