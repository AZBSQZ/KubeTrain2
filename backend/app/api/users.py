from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy import or_
from app import db
from app.models.user import User
from app.models.resource import ResourceQuota

users_bp = Blueprint('users', __name__)


def _require_admin():
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'code': 403, 'message': '需要管理员权限'}), 403
    return None


@users_bp.route('', methods=['GET'])
@jwt_required()
def list_users():
    err = _require_admin()
    if err:
        return err
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    # 兼容 search / q / keyword 三种参数名
    q = (request.args.get('search') or request.args.get('q') or request.args.get('keyword', '')).strip()
    role = request.args.get('role', '').strip()
    is_active_param = request.args.get('is_active')

    query = User.query  # admin 看全部，包括被禁用的

    if q:
        query = query.filter(
            or_(User.username.ilike(f'%{q}%'), User.email.ilike(f'%{q}%'))
        )
    if role:
        query = query.filter(User.role == role)
    if is_active_param is not None and is_active_param != '':
        query = query.filter(User.is_active == (str(is_active_param) in ('1', 'true', 'True')))

    pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'code': 200,
        'data': {
            'items': [u.to_dict() for u in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
        }
    })


@users_bp.route('', methods=['POST'])
@jwt_required()
def create_user():
    err = _require_admin()
    if err:
        return err
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    email = data.get('email', '')
    role = data.get('role', 'user')
    if not username or not password:
        return jsonify({'code': 400, 'message': '用户名和密码不能为空'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'code': 400, 'message': '用户名已存在'}), 400
    if role not in ('admin', 'user', 'guest'):
        role = 'user'
    user = User(username=username, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({'code': 200, 'message': '用户创建成功', 'data': user.to_dict()})


@users_bp.route('/<int:user_id>', methods=['GET'])
@jwt_required()
def get_user(user_id):
    identity = int(get_jwt_identity())
    claims = get_jwt()
    if claims.get('role') != 'admin' and identity != user_id:
        return jsonify({'code': 403, 'message': '无权访问'}), 403
    user = User.query.get_or_404(user_id)
    return jsonify({'code': 200, 'data': user.to_dict()})


@users_bp.route('/<int:user_id>', methods=['PUT'])
@jwt_required()
def update_user(user_id):
    err = _require_admin()
    if err:
        return err
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}
    if 'email' in data:
        user.email = data['email']
    if 'role' in data and data['role'] in ('admin', 'user', 'guest'):
        user.role = data['role']
    if 'is_active' in data:
        user.is_active = bool(data['is_active'])
    if 'password' in data and data['password']:
        user.set_password(data['password'])
    db.session.commit()
    return jsonify({'code': 200, 'message': '用户更新成功', 'data': user.to_dict()})


@users_bp.route('/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    err = _require_admin()
    if err:
        return err
    current_user_id = int(get_jwt_identity())
    if user_id == current_user_id:
        return jsonify({'code': 400, 'message': '不能删除自己'}), 400
    user = User.query.get_or_404(user_id)
    try:
        cleanup_sqls = [
            'UPDATE tasks SET created_by = NULL WHERE created_by = :uid',
            'UPDATE datasets SET created_by = NULL WHERE created_by = :uid',
            'UPDATE dataset_versions SET created_by = NULL WHERE created_by = :uid',
            'UPDATE algorithms SET created_by = NULL WHERE created_by = :uid',
            'UPDATE algorithm_versions SET created_by = NULL WHERE created_by = :uid',
            'UPDATE models SET created_by = NULL WHERE created_by = :uid',
            'UPDATE model_versions SET created_by = NULL WHERE created_by = :uid',
            'UPDATE model_groups SET created_by = NULL WHERE created_by = :uid',
        ]
        from sqlalchemy import text
        for sql in cleanup_sqls:
            try:
                db.session.execute(text(sql), {'uid': user_id})
            except Exception:
                pass
        db.session.delete(user)
        db.session.commit()
        return jsonify({'code': 200, 'message': '用户已删除'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'message': f'删除失败: {str(e)}'}), 500


@users_bp.route('/<int:user_id>/quota', methods=['PUT'])
@jwt_required()
def set_user_quota(user_id):
    err = _require_admin()
    if err:
        return err
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}
    quota_id = data.get('quota_id')
    if quota_id:
        quota = ResourceQuota.query.get(quota_id)
        if not quota:
            return jsonify({'code': 404, 'message': '配额不存在'}), 404
        user.quota_id = quota_id
    else:
        user.quota_id = None
    db.session.commit()
    return jsonify({'code': 200, 'message': '配额设置成功', 'data': user.to_dict()})
