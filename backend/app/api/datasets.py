import os
import hashlib
from flask import Blueprint, request, jsonify, current_app, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from werkzeug.utils import secure_filename
from app import db
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User
from app.models.tag import Tag
from sqlalchemy import func, or_, false
from app.utils.audit import log_operation, get_current_user_info

datasets_bp = Blueprint('datasets', __name__)

ALLOWED_EXTENSIONS = {'zip', 'tar', 'gz', 'csv', 'json', 'txt', 'parquet', 'h5', 'hdf5', 'npy', 'npz',
                      'jpg', 'jpeg', 'png', 'pdf', 'pkl', 'pickle', 'xlsx', 'xls', 'mp4', 'avi', 'wav', 'mp3'}

_EXT_TYPE_MAP = {
    '.csv': 'CSV', '.json': 'JSON', '.xml': 'XML', '.txt': 'TXT',
    '.xlsx': 'Excel', '.xls': 'Excel', '.parquet': 'Parquet',
    '.jpg': 'Image', '.jpeg': 'Image', '.png': 'Image', '.gif': 'Image', '.bmp': 'Image',
    '.mp4': 'Video', '.avi': 'Video', '.mov': 'Video',
    '.mp3': 'Audio', '.wav': 'Audio',
    '.zip': 'Archive', '.tar': 'Archive', '.gz': 'Archive', '.rar': 'Archive',
    '.pdf': 'PDF', '.h5': 'HDF5', '.hdf5': 'HDF5',
    '.npy': 'NumPy', '.npz': 'NumPy',
    '.pkl': 'Pickle', '.pickle': 'Pickle',
}


def _detect_file_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    return _EXT_TYPE_MAP.get(ext, 'Other')


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_user_id():
    try:
        return int(get_jwt_identity())
    except Exception:
        return None


def _get_role():
    try:
        return get_jwt().get('role', 'user')
    except Exception:
        return 'user'


@datasets_bp.route('', methods=['GET'])
@jwt_required()
def list_datasets():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    q = (request.args.get('q') or request.args.get('search') or request.args.get('keyword', '')).strip()
    data_type = request.args.get('data_type', '')

    user_id = _get_user_id()
    is_admin = _get_role() == 'admin'

    query = Dataset.query.filter_by(is_deleted=False)

    # 角色过滤：管理员看全部，普通用户看自己的+公开的+管理员的
    if not is_admin and user_id:
        admin_ids = [u.id for u in User.query.filter_by(role='admin').with_entities(User.id).all()]
        conditions = [
            Dataset.created_by == user_id,
            Dataset.is_public == True,
        ]
        if admin_ids:
            conditions.append(Dataset.created_by.in_(admin_ids))
        query = query.filter(or_(*conditions))

    if q:
        query = query.filter(Dataset.name.ilike(f'%{q}%'))
    if data_type:
        query = query.filter_by(data_type=data_type)

    pagination = query.order_by(Dataset.updated_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    # Batch-load version counts
    ds_ids = [d.id for d in pagination.items]
    version_counts = {}
    if ds_ids:
        rows = db.session.query(
            DatasetVersion.dataset_id, func.count(DatasetVersion.id)
        ).filter(DatasetVersion.dataset_id.in_(ds_ids)).group_by(DatasetVersion.dataset_id).all()
        version_counts = {did: cnt for did, cnt in rows}

    return jsonify({
        'code': 200,
        'data': {
            'items': [d.to_dict(_version_count=version_counts.get(d.id, 0)) for d in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
        }
    })


@datasets_bp.route('/<int:dataset_id>', methods=['GET'])
@jwt_required()
def get_dataset(dataset_id):
    dataset = Dataset.query.filter_by(id=dataset_id, is_deleted=False).first_or_404()
    return jsonify({'code': 200, 'data': dataset.to_dict(include_versions=True)})


@datasets_bp.route('', methods=['POST'])
@jwt_required()
def create_dataset():
    """创建数据集（先建元数据，再上传文件）"""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '数据集名称不能为空'}), 400

    user_id = _get_user_id()

    # 同名检查
    if Dataset.query.filter_by(name=name, is_deleted=False).first():
        return jsonify({'code': 409, 'message': f'已存在同名数据集"{name}"，请使用不同名称或在现有数据集下上传新版本'}), 409

    dataset = Dataset(
        name=name,
        description=data.get('description', ''),
        data_type=data.get('data_type', ''),
        source_type=data.get('source_type', 'upload'),
        is_public=data.get('is_public', False),
        created_by=user_id,
    )
    db.session.add(dataset)
    db.session.flush()

    tag_names = data.get('tags', [])
    for tag_name in tag_names:
        tag = Tag.query.filter_by(name=tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            db.session.add(tag)
        dataset.tags.append(tag)

    db.session.commit()
    
    user_id, username = get_current_user_info()
    log_operation(
        user_id=user_id, username=username,
        operation_type='create', module='datasets',
        action=f'创建数据集: {name}',
        target_type='dataset', target_id=dataset.id, target_name=name
    )
    return jsonify({'code': 200, 'message': '数据集创建成功', 'data': dataset.to_dict()})


@datasets_bp.route('/<int:dataset_id>/upload', methods=['POST'])
@jwt_required()
def upload_dataset_file(dataset_id):
    """上传数据集文件，自动创建新版本"""
    dataset = Dataset.query.filter_by(id=dataset_id, is_deleted=False).first_or_404()
    user_id = _get_user_id()

    if 'file' not in request.files:
        return jsonify({'code': 400, 'message': '未选择文件'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'code': 400, 'message': '文件名为空'}), 400
    if not _allowed_file(file.filename):
        return jsonify({'code': 400, 'message': f'不支持的文件类型'}), 400

    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'datasets', str(dataset_id))
    os.makedirs(upload_dir, exist_ok=True)

    filename = secure_filename(file.filename)
    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)

    file_size = os.path.getsize(file_path)
    file_hash = _calc_md5(file_path)

    # 自动识别文件类型（若数据集 data_type 为空则更新）
    if not dataset.data_type:
        dataset.data_type = _detect_file_type(filename)

    version_count = dataset.versions.count()
    version_number = f'v{version_count + 1}.0'

    version = DatasetVersion(
        dataset_id=dataset_id,
        version_number=version_number,
        version_name=request.form.get('version_name', ''),
        file_path=file_path,
        file_size=file_size,
        file_hash=file_hash,
        description=request.form.get('description', ''),
        created_by=user_id,
    )
    db.session.add(version)
    dataset.total_size = file_size
    dataset.original_filename = filename
    db.session.commit()
    
    user_id, username = get_current_user_info()
    log_operation(
        user_id=user_id, username=username,
        operation_type='upload', module='datasets',
        action=f'上传数据集文件: {dataset.name} ({version_number})',
        target_type='dataset', target_id=dataset.id, target_name=dataset.name,
        detail={'version': version_number, 'file_size': file_size, 'filename': filename}
    )
    return jsonify({'code': 200, 'message': '上传成功', 'data': version.to_dict()})


@datasets_bp.route('/<int:dataset_id>', methods=['PUT'])
@jwt_required()
def update_dataset(dataset_id):
    dataset = Dataset.query.filter_by(id=dataset_id, is_deleted=False).first_or_404()
    data = request.get_json() or {}
    if 'name' in data:
        dataset.name = data['name']
    if 'description' in data:
        dataset.description = data['description']
    if 'data_type' in data:
        dataset.data_type = data['data_type']
    if 'is_public' in data:
        dataset.is_public = bool(data['is_public'])
    db.session.commit()
    return jsonify({'code': 200, 'message': '更新成功', 'data': dataset.to_dict()})


@datasets_bp.route('/<int:dataset_id>', methods=['DELETE'])
@jwt_required()
def delete_dataset(dataset_id):
    dataset = Dataset.query.filter_by(id=dataset_id, is_deleted=False).first_or_404()
    dataset_name = dataset.name
    dataset.is_deleted = True
    db.session.commit()
    
    user_id, username = get_current_user_info()
    log_operation(
        user_id=user_id, username=username,
        operation_type='delete', module='datasets',
        action=f'删除数据集: {dataset_name}',
        target_type='dataset', target_id=dataset_id, target_name=dataset_name
    )
    return jsonify({'code': 200, 'message': '删除成功'})


@datasets_bp.route('/<int:dataset_id>/versions', methods=['GET'])
@jwt_required()
def list_versions(dataset_id):
    dataset = Dataset.query.filter_by(id=dataset_id, is_deleted=False).first_or_404()
    versions = dataset.versions.order_by(DatasetVersion.created_at.desc()).all()
    return jsonify({'code': 200, 'data': [v.to_dict() for v in versions]})


@datasets_bp.route('/<int:dataset_id>/download', methods=['GET'])
@jwt_required()
def download_dataset(dataset_id):
    """下载数据集最新版本"""
    dataset = Dataset.query.filter_by(id=dataset_id, is_deleted=False).first_or_404()
    version = dataset.versions.order_by(DatasetVersion.created_at.desc()).first()
    if not version or not version.file_path:
        return jsonify({'code': 404, 'message': '无可下载文件'}), 404
    if not os.path.exists(version.file_path):
        return jsonify({'code': 404, 'message': '文件不存在'}), 404
    
    user_id, username = get_current_user_info()
    log_operation(
        user_id=user_id, username=username,
        operation_type='download', module='datasets',
        action=f'下载数据集: {dataset.name}',
        target_type='dataset', target_id=dataset_id, target_name=dataset.name
    )
    return send_file(version.file_path, as_attachment=True, download_name=dataset.original_filename or os.path.basename(version.file_path))


@datasets_bp.route('/<int:dataset_id>/versions/<int:version_id>/download', methods=['GET'])
@jwt_required()
def download_dataset_version(dataset_id, version_id):
    """下载数据集指定版本"""
    dataset = Dataset.query.filter_by(id=dataset_id, is_deleted=False).first_or_404()
    version = DatasetVersion.query.filter_by(id=version_id, dataset_id=dataset_id).first_or_404()
    if not version.file_path or not os.path.exists(version.file_path):
        return jsonify({'code': 404, 'message': '文件不存在'}), 404
    
    user_id, username = get_current_user_info()
    log_operation(
        user_id=user_id, username=username,
        operation_type='download', module='datasets',
        action=f'下载数据集版本: {dataset.name} ({version.version_number})',
        target_type='dataset', target_id=dataset_id, target_name=dataset.name
    )
    return send_file(version.file_path, as_attachment=True, download_name=os.path.basename(version.file_path))


def _calc_md5(filepath):
    h = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()
