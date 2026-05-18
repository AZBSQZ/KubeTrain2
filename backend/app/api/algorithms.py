import os
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy import or_
from app.models.user import User
from werkzeug.utils import secure_filename
from app import db
from app.models.algorithm import Algorithm, AlgorithmVersion
from app.models.tag import Tag
from app.utils.audit import log_operation, get_current_user_info

algorithms_bp = Blueprint('algorithms', __name__)


def _get_user_id():
    try:
        return int(get_jwt_identity())
    except Exception:
        return None


@algorithms_bp.route('', methods=['GET'])
@jwt_required()
def list_algorithms():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    q = (request.args.get('q') or request.args.get('search') or request.args.get('keyword', '')).strip()
    framework = request.args.get('framework', '')

    user_id = _get_user_id()
    is_admin = get_jwt().get('role') == 'admin'

    query = Algorithm.query.filter_by(is_deleted=False)

    if not is_admin and user_id:
        admin_ids = [u.id for u in User.query.filter_by(role='admin').with_entities(User.id).all()]
        conditions = [Algorithm.created_by == user_id, Algorithm.is_public == True]
        if admin_ids:
            conditions.append(Algorithm.created_by.in_(admin_ids))
        query = query.filter(or_(*conditions))

    if q:
        query = query.filter(Algorithm.name.ilike(f'%{q}%'))
    if framework:
        query = query.filter_by(framework=framework)

    pagination = query.order_by(Algorithm.updated_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'code': 200,
        'data': {
            'items': [a.to_dict() for a in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
        }
    })


@algorithms_bp.route('/<int:algo_id>', methods=['GET'])
@jwt_required()
def get_algorithm(algo_id):
    algo = Algorithm.query.filter_by(id=algo_id, is_deleted=False).first_or_404()
    return jsonify({'code': 200, 'data': algo.to_dict(include_versions=True)})


@algorithms_bp.route('', methods=['POST'])
@jwt_required()
def create_algorithm():
    """创建算法（支持 JSON 或 multipart/form-data 含脚本文件+参数定义）"""
    import json as _json

    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form
    else:
        data = request.get_json() or {}

    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '算法名称不能为空'}), 400

    user_id = _get_user_id()
    algo = Algorithm(
        name=name,
        description=data.get('description', ''),
        algorithm_type=data.get('algorithm_type', ''),
        framework=data.get('framework', 'PyTorch'),
        is_public=bool(data.get('is_public', False)),
        created_by=user_id,
    )
    db.session.add(algo)
    db.session.flush()

    if isinstance(data, dict):
        tag_names = data.get('tags', [])
    else:
        tag_names = []
    for tag_name in tag_names:
        tag = Tag.query.filter_by(name=tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            db.session.add(tag)
        algo.tags.append(tag)

    # 如果提交了脚本文件或脚本内容，自动创建 v1.0 版本
    script_content = data.get('script_content', '')
    script_path = ''
    has_script = False

    if 'file' in request.files:
        file = request.files['file']
        if file.filename:
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'algorithms', str(algo.id))
            os.makedirs(upload_dir, exist_ok=True)
            filename = secure_filename(file.filename)
            script_path = os.path.join(upload_dir, filename)
            file.save(script_path)
            with open(script_path, 'r', encoding='utf-8') as f:
                script_content = f.read()
            has_script = True
    elif script_content:
        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'algorithms', str(algo.id))
        os.makedirs(upload_dir, exist_ok=True)
        script_path = os.path.join(upload_dir, 'train_v1_0.py')
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
        has_script = True

    if has_script:
        parameters = None
        params_str = data.get('parameters')
        if params_str:
            try:
                parameters = _json.loads(params_str) if isinstance(params_str, str) else params_str
            except Exception:
                pass

        version = AlgorithmVersion(
            algorithm_id=algo.id,
            version_number='v1.0',
            version_name='初始版本',
            script_path=script_path,
            script_content=script_content,
            parameters=parameters,
            is_active=True,
            created_by=user_id,
        )
        db.session.add(version)

    db.session.commit()
    
    user_id, username = get_current_user_info()
    log_operation(
        user_id=user_id, username=username,
        operation_type='create', module='algorithms',
        action=f'创建算法: {name}',
        target_type='algorithm', target_id=algo.id, target_name=name
    )
    return jsonify({'code': 200, 'message': '算法创建成功', 'data': algo.to_dict()})


@algorithms_bp.route('/<int:algo_id>', methods=['PUT'])
@jwt_required()
def update_algorithm(algo_id):
    algo = Algorithm.query.filter_by(id=algo_id, is_deleted=False).first_or_404()
    data = request.get_json() or {}
    if 'name' in data:
        algo.name = data['name']
    if 'description' in data:
        algo.description = data['description']
    if 'framework' in data:
        algo.framework = data['framework']
    if 'algorithm_type' in data:
        algo.algorithm_type = data['algorithm_type']
    if 'is_public' in data:
        algo.is_public = bool(data['is_public'])
    db.session.commit()
    return jsonify({'code': 200, 'message': '更新成功', 'data': algo.to_dict()})


@algorithms_bp.route('/<int:algo_id>', methods=['DELETE'])
@jwt_required()
def delete_algorithm(algo_id):
    algo = Algorithm.query.filter_by(id=algo_id, is_deleted=False).first_or_404()
    algo_name = algo.name
    algo.is_deleted = True
    db.session.commit()
    
    user_id, username = get_current_user_info()
    log_operation(
        user_id=user_id, username=username,
        operation_type='delete', module='algorithms',
        action=f'删除算法: {algo_name}',
        target_type='algorithm', target_id=algo_id, target_name=algo_name
    )
    return jsonify({'code': 200, 'message': '删除成功'})


@algorithms_bp.route('/<int:algo_id>/versions', methods=['GET'])
@jwt_required()
def list_versions(algo_id):
    algo = Algorithm.query.filter_by(id=algo_id, is_deleted=False).first_or_404()
    versions = algo.versions.order_by(AlgorithmVersion.created_at.desc()).all()
    return jsonify({'code': 200, 'data': [v.to_dict() for v in versions]})


@algorithms_bp.route('/<int:algo_id>/versions', methods=['POST'])
@jwt_required()
def create_version(algo_id):
    """创建新版本（支持直接提交脚本内容或上传文件）"""
    algo = Algorithm.query.filter_by(id=algo_id, is_deleted=False).first_or_404()
    user_id = _get_user_id()

    # 支持 JSON 方式（脚本内容直接传入）
    if request.is_json:
        data = request.get_json() or {}
        script_content = data.get('script_content', '')
        version_number = data.get('version_number', '')
    else:
        data = request.form
        script_content = data.get('script_content', '')
        version_number = data.get('version_number', '')

    if not version_number:
        count = algo.versions.count()
        version_number = f'v{count + 1}.0'

    # 检查版本号是否重复
    if algo.versions.filter_by(version_number=version_number).first():
        return jsonify({'code': 400, 'message': f'版本号 {version_number} 已存在'}), 400

    # 保存脚本文件
    script_path = ''
    if script_content:
        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'algorithms', str(algo_id))
        os.makedirs(upload_dir, exist_ok=True)
        script_filename = f'train_{version_number.replace(".", "_")}.py'
        script_path = os.path.join(upload_dir, script_filename)
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
    elif 'file' in request.files:
        file = request.files['file']
        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'algorithms', str(algo_id))
        os.makedirs(upload_dir, exist_ok=True)
        filename = secure_filename(file.filename)
        script_path = os.path.join(upload_dir, filename)
        file.save(script_path)
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()

    # 将之前的版本设为非活跃
    algo.versions.filter_by(is_active=True).update({'is_active': False})

    version = AlgorithmVersion(
        algorithm_id=algo_id,
        version_number=version_number,
        version_name=data.get('version_name', ''),
        script_path=script_path,
        script_content=script_content,
        parameters=data.get('parameters') if request.is_json else None,
        dependencies=data.get('dependencies') if request.is_json else None,
        description=data.get('description', ''),
        is_active=True,
        created_by=user_id,
    )
    db.session.add(version)
    db.session.commit()
    return jsonify({'code': 200, 'message': '版本创建成功', 'data': version.to_dict(include_content=True)})


@algorithms_bp.route('/<int:algo_id>/versions/<int:version_id>', methods=['GET'])
@jwt_required()
def get_version(algo_id, version_id):
    version = AlgorithmVersion.query.filter_by(id=version_id, algorithm_id=algo_id).first_or_404()
    return jsonify({'code': 200, 'data': version.to_dict(include_content=True)})


@algorithms_bp.route('/versions/<int:version_id>', methods=['GET'])
@jwt_required()
def get_version_by_id(version_id):
    """通过版本ID直接获取算法版本详情（含参数定义）"""
    version = AlgorithmVersion.query.get_or_404(version_id)
    return jsonify({'code': 200, 'data': version.to_dict(include_content=True)})


@algorithms_bp.route('/<int:algo_id>/versions/<int:version_id>/script', methods=['PUT'])
@jwt_required()
def update_script(algo_id, version_id):
    """在线编辑脚本内容"""
    version = AlgorithmVersion.query.filter_by(id=version_id, algorithm_id=algo_id).first_or_404()
    data = request.get_json() or {}
    script_content = data.get('script_content', '')
    version.script_content = script_content
    if version.script_path and os.path.isfile(version.script_path):
        with open(version.script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
    db.session.commit()
    return jsonify({'code': 200, 'message': '脚本更新成功', 'data': version.to_dict(include_content=True)})


@algorithms_bp.route('/<int:algo_id>/versions/<int:version_id>/activate', methods=['POST'])
@jwt_required()
def activate_version(algo_id, version_id):
    algo = Algorithm.query.filter_by(id=algo_id, is_deleted=False).first_or_404()
    algo.versions.filter_by(is_active=True).update({'is_active': False})
    version = AlgorithmVersion.query.filter_by(id=version_id, algorithm_id=algo_id).first_or_404()
    version.is_active = True
    db.session.commit()
    return jsonify({'code': 200, 'message': '版本已激活'})
