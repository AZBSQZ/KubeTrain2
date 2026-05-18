from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from datetime import datetime
from app import db
from app.models.user import User
from app.utils.audit import log_operation

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    email = data.get('email', '').strip()

    if not username or not password:
        return jsonify({'code': 400, 'message': '用户名和密码不能为空'}), 400
    if len(username) < 3 or len(username) > 50:
        return jsonify({'code': 400, 'message': '用户名长度须在3-50个字符之间'}), 400
    if len(password) < 6:
        return jsonify({'code': 400, 'message': '密码长度不能少于6位'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'code': 400, 'message': '用户名已存在'}), 400
    if email and User.query.filter_by(email=email).first():
        return jsonify({'code': 400, 'message': '邮箱已被注册'}), 400

    user = User(username=username, email=email or None, role='user', is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    log_operation(
        user_id=user.id, username=user.username,
        operation_type='register', module='auth',
        action=f'用户注册: {username}',
        target_type='user', target_id=user.id, target_name=username
    )
    return jsonify({'code': 200, 'message': '注册成功，请登录'})


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'code': 400, 'message': '用户名和密码不能为空'}), 400

    user = User.query.filter(
        db.or_(User.username == username, User.email == username),
        User.is_active == True
    ).first()

    if not user or not user.check_password(password):
        return jsonify({'code': 401, 'message': '用户名或密码错误'}), 401

    user.last_login = datetime.utcnow()
    db.session.commit()
    
    log_operation(
        user_id=user.id, username=user.username,
        operation_type='login', module='auth',
        action=f'用户登录: {user.username}',
        target_type='user', target_id=user.id, target_name=user.username
    )

    additional_claims = {'username': user.username, 'role': user.role or 'user'}
    access_token = create_access_token(identity=str(user.id), additional_claims=additional_claims)
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims=additional_claims)

    return jsonify({
        'code': 200,
        'message': '登录成功',
        'data': {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict()
        }
    })


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    if not user or not user.is_active:
        return jsonify({'code': 401, 'message': '用户不存在或已禁用'}), 401
    claims = {'username': user.username, 'role': user.role or 'user'}
    access_token = create_access_token(identity=identity, additional_claims=claims)
    return jsonify({'code': 200, 'data': {'access_token': access_token}})


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    identity = get_jwt_identity()
    claims = get_jwt()
    log_operation(
        user_id=int(identity) if identity else None,
        username=claims.get('username'),
        operation_type='logout', module='auth',
        action=f'用户退出: {claims.get("username")}',
        target_type='user', target_id=identity, target_name=claims.get('username')
    )
    return jsonify({'code': 200, 'message': '退出成功'})


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    if not user:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404
    return jsonify({'code': 200, 'data': user.to_dict()})


@auth_bp.route('/me/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    if not user:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404
    data = request.get_json() or {}

    if 'username' in data and data['username']:
        new_username = data['username'].strip()
        if new_username != user.username:
            if len(new_username) < 3 or len(new_username) > 50:
                return jsonify({'code': 400, 'message': '用户名长度须在3-50个字符之间'}), 400
            if User.query.filter(User.username == new_username, User.id != user.id).first():
                return jsonify({'code': 400, 'message': '用户名已被使用'}), 400
            user.username = new_username

    if 'email' in data:
        email = (data['email'] or '').strip()
        if email and User.query.filter(User.email == email, User.id != user.id).first():
            return jsonify({'code': 400, 'message': '邮箱已被使用'}), 400
        user.email = email or None

    db.session.commit()
    return jsonify({'code': 200, 'message': '资料更新成功', 'data': user.to_dict()})


@auth_bp.route('/me/password', methods=['PUT'])
@jwt_required()
def change_password():
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    if not user:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404
    data = request.get_json() or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    if not user.check_password(old_password):
        return jsonify({'code': 400, 'message': '原密码错误'}), 400
    if len(new_password) < 6:
        return jsonify({'code': 400, 'message': '新密码长度不能少于6位'}), 400
    user.set_password(new_password)
    db.session.commit()
    return jsonify({'code': 200, 'message': '密码修改成功'})
