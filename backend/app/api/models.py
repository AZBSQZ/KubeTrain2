import os
from flask import Blueprint, request, jsonify, send_file, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy import or_
from app import db
from app.models.model import Model, ModelVersion
from app.models.model_group import ModelGroup
from app.models.user import User
from app.models.tag import Tag
from app.utils.audit import log_operation, get_current_user_info

models_bp = Blueprint('models', __name__)


def _get_user_id():
    try:
        return int(get_jwt_identity())
    except Exception:
        return None


@models_bp.route('', methods=['GET'])
@jwt_required()
def list_models():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    q = (request.args.get('q') or request.args.get('search') or request.args.get('keyword', '')).strip()
    source = request.args.get('source', '')
    group_id = request.args.get('group_id', type=int)

    user_id = _get_user_id()
    is_admin = get_jwt().get('role') == 'admin'

    query = Model.query.filter_by(is_deleted=False)

    if not is_admin and user_id:
        admin_ids = [u.id for u in User.query.filter_by(role='admin').with_entities(User.id).all()]
        conditions = [Model.created_by == user_id, Model.is_public == True]
        if admin_ids:
            conditions.append(Model.created_by.in_(admin_ids))
        query = query.filter(or_(*conditions))

    if q:
        query = query.filter(Model.name.ilike(f'%{q}%'))
    if source:
        query = query.filter_by(source=source)
    if group_id:
        query = query.filter_by(group_id=group_id)

    pagination = query.order_by(Model.updated_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'code': 200,
        'data': {
            'items': [m.to_dict() for m in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
        }
    })


@models_bp.route('/<int:model_id>', methods=['GET'])
@jwt_required()
def get_model(model_id):
    model = Model.query.filter_by(id=model_id, is_deleted=False).first_or_404()
    return jsonify({'code': 200, 'data': model.to_dict(include_versions=True)})


@models_bp.route('', methods=['POST'])
@jwt_required()
def create_model():
    """创建模型（支持 JSON 或 multipart/form-data 含模型文件）"""
    from werkzeug.utils import secure_filename

    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form
    else:
        data = request.get_json() or {}

    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '模型名称不能为空'}), 400

    is_public_raw = data.get('is_public', False)
    if isinstance(is_public_raw, str):
        is_public = is_public_raw.lower() in ('true', '1', 'yes')
    else:
        is_public = bool(is_public_raw)

    user_id = _get_user_id()
    model = Model(
        name=name,
        description=data.get('description', ''),
        model_type=data.get('model_type', ''),
        framework=data.get('framework', 'PyTorch'),
        source=data.get('source', 'upload'),
        group_id=data.get('group_id', type=int) if hasattr(data, 'getlist') else data.get('group_id'),
        is_public=is_public,
        created_by=user_id,
    )
    db.session.add(model)
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
        model.tags.append(tag)

    # 处理模型文件上传 → 自动创建 v1.0 版本
    file_path = ''
    file_size = 0
    file_format = ''
    has_file = False

    if 'model_file' in request.files:
        file = request.files['model_file']
        if file.filename:
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'models', str(model.id))
            os.makedirs(upload_dir, exist_ok=True)
            filename = secure_filename(file.filename)
            file_path = os.path.join(upload_dir, filename)
            file.save(file_path)
            file_size = os.path.getsize(file_path)
            ext = os.path.splitext(filename)[1].lower()
            file_format = ext.lstrip('.')
            has_file = True

    if has_file:
        version = ModelVersion(
            model_id=model.id,
            version_number='v1.0',
            version_name='初始版本',
            file_path=file_path,
            file_size=file_size,
            file_format=file_format,
            description='上传创建',
            created_by=user_id,
        )
        db.session.add(version)
    elif isinstance(data, dict):
        # 兼容 JSON 方式包含版本信息
        version_data = data.get('version')
        if version_data:
            version = ModelVersion(
                model_id=model.id,
                version_number=version_data.get('version_number', 'v1.0'),
                version_name=version_data.get('version_name', ''),
                file_path=version_data.get('file_path', ''),
                file_size=version_data.get('file_size', 0),
                file_format=version_data.get('file_format', ''),
                metrics=version_data.get('metrics'),
                hyperparameters=version_data.get('hyperparameters'),
                task_id=version_data.get('task_id'),
                dataset_id=version_data.get('dataset_id'),
                algorithm_version_id=version_data.get('algorithm_version_id'),
                description=version_data.get('description', ''),
                created_by=user_id,
            )
            db.session.add(version)

    db.session.commit()
    
    user_id, username = get_current_user_info()
    log_operation(
        user_id=user_id, username=username,
        operation_type='create', module='models',
        action=f'创建模型: {name}',
        target_type='model', target_id=model.id, target_name=name
    )
    return jsonify({'code': 200, 'message': '模型创建成功', 'data': model.to_dict()})


@models_bp.route('/<int:model_id>', methods=['PUT'])
@jwt_required()
def update_model(model_id):
    model = Model.query.filter_by(id=model_id, is_deleted=False).first_or_404()
    data = request.get_json() or {}
    for field in ('name', 'description', 'model_type', 'framework'):
        if field in data:
            setattr(model, field, data[field])
    if 'group_id' in data:
        model.group_id = data['group_id']
    if 'is_public' in data:
        model.is_public = bool(data['is_public'])
    db.session.commit()
    return jsonify({'code': 200, 'message': '更新成功', 'data': model.to_dict()})


@models_bp.route('/<int:model_id>', methods=['DELETE'])
@jwt_required()
def delete_model(model_id):
    model = Model.query.filter_by(id=model_id, is_deleted=False).first_or_404()
    model_name = model.name
    model.is_deleted = True
    db.session.commit()
    
    user_id, username = get_current_user_info()
    log_operation(
        user_id=user_id, username=username,
        operation_type='delete', module='models',
        action=f'删除模型: {model_name}',
        target_type='model', target_id=model_id, target_name=model_name
    )
    return jsonify({'code': 200, 'message': '删除成功'})


@models_bp.route('/<int:model_id>/versions', methods=['GET'])
@jwt_required()
def list_versions(model_id):
    model = Model.query.filter_by(id=model_id, is_deleted=False).first_or_404()
    versions = model.versions.order_by(ModelVersion.created_at.desc()).all()
    return jsonify({'code': 200, 'data': [v.to_dict() for v in versions]})


@models_bp.route('/<int:model_id>/versions/<int:version_id>/download', methods=['GET'])
@jwt_required()
def download_version(model_id, version_id):
    model = Model.query.filter_by(id=model_id, is_deleted=False).first_or_404()
    version = ModelVersion.query.filter_by(id=version_id, model_id=model_id).first_or_404()
    if not version.file_path or not os.path.isfile(version.file_path):
        return jsonify({'code': 404, 'message': '模型文件不存在'}), 404
    
    user_id, username = get_current_user_info()
    log_operation(
        user_id=user_id, username=username,
        operation_type='download', module='models',
        action=f'下载模型: {model.name} ({version.version_number})',
        target_type='model', target_id=model_id, target_name=model.name
    )
    return send_file(version.file_path, as_attachment=True)


@models_bp.route('/<int:model_id>/download', methods=['GET'])
@jwt_required()
def download_model(model_id):
    """下载模型最新版本"""
    model = Model.query.filter_by(id=model_id, is_deleted=False).first_or_404()
    version = model.versions.order_by(ModelVersion.created_at.desc()).first()
    if not version or not version.file_path or not os.path.isfile(version.file_path):
        return jsonify({'code': 404, 'message': '无可下载文件'}), 404
    
    user_id, username = get_current_user_info()
    log_operation(
        user_id=user_id, username=username,
        operation_type='download', module='models',
        action=f'下载模型: {model.name}',
        target_type='model', target_id=model_id, target_name=model.name
    )
    return send_file(version.file_path, as_attachment=True)


@models_bp.route('/<int:model_id>/versions/<int:version_id>/production', methods=['POST'])
@jwt_required()
def mark_production(model_id, version_id):
    """标记生产版本"""
    model = Model.query.filter_by(id=model_id, is_deleted=False).first_or_404()
    model.versions.update({'is_production': False})
    version = ModelVersion.query.filter_by(id=version_id, model_id=model_id).first_or_404()
    version.is_production = True
    db.session.commit()
    return jsonify({'code': 200, 'message': '已标记为生产版本'})


@models_bp.route('/from-task/<task_id>', methods=['POST'])
@jwt_required()
def register_from_task(task_id):
    """从训练任务结果自动注册模型"""
    from app.models.task import Task
    task = Task.query.get_or_404(task_id)
    if not task.model_path:
        return jsonify({'code': 400, 'message': '训练任务没有模型输出路径'}), 400

    user_id = _get_user_id()
    data = request.get_json() or {}
    model_name = data.get('name', task.name)

    model = Model(
        name=model_name,
        description=data.get('description', f'来自训练任务: {task.name}'),
        framework=data.get('framework', 'PyTorch'),
        source='training',
        group_id=data.get('group_id'),
        created_by=user_id or task.created_by,
    )
    db.session.add(model)
    db.session.flush()

    version = ModelVersion(
        model_id=model.id,
        version_number='v1.0',
        file_path=task.model_path,
        metrics={
            'final_loss': task.final_loss,
            'final_accuracy': task.final_accuracy,
            'best_metric': task.best_metric,
        },
        task_id=task.id,
        dataset_id=task.dataset_id,
        algorithm_version_id=task.algorithm_version_id,
        description=f'训练任务 {task.name} 完成，epochs={task.total_epochs}',
        created_by=user_id or task.created_by,
    )
    db.session.add(version)
    db.session.commit()
    return jsonify({'code': 200, 'message': '模型注册成功', 'data': model.to_dict(include_versions=True)})
