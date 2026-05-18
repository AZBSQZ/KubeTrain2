import uuid
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from app import db
from app.models.k8s_cluster import K8sCluster

clusters_bp = Blueprint('clusters', __name__)


def _require_admin():
    if get_jwt().get('role') != 'admin':
        return jsonify({'code': 403, 'message': '需要管理员权限'}), 403
    return None


@clusters_bp.route('', methods=['GET'])
@jwt_required()
def list_clusters():
    clusters = K8sCluster.query.order_by(K8sCluster.created_at.desc()).all()
    return jsonify({'code': 200, 'data': [c.to_dict() for c in clusters]})


@clusters_bp.route('/<cluster_id>', methods=['GET'])
@jwt_required()
def get_cluster(cluster_id):
    cluster = K8sCluster.query.get_or_404(cluster_id)
    return jsonify({'code': 200, 'data': cluster.to_dict()})


@clusters_bp.route('', methods=['POST'])
@jwt_required()
def create_cluster():
    err = _require_admin()
    if err:
        return err
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '集群名称不能为空'}), 400
    if K8sCluster.query.filter_by(name=name).first():
        return jsonify({'code': 400, 'message': '集群名称已存在'}), 400

    is_default = data.get('is_default', False)
    if is_default:
        K8sCluster.query.update({'is_default': False})

    cluster = K8sCluster(
        id=str(uuid.uuid4()),
        name=name,
        description=data.get('description', ''),
        api_server=data.get('api_server', ''),
        kubeconfig_content=data.get('kubeconfig_content') or data.get('kubeconfig') or '',
        auth_type=data.get('auth_type', 'kubeconfig'),
        token=data.get('token', ''),
        namespace=data.get('namespace', 'kubetrain'),
        pvc_name=data.get('pvc_name', 'kubetrain-data-pvc'),
        is_default=is_default,
        labels=data.get('labels'),
    )
    db.session.add(cluster)
    db.session.commit()
    return jsonify({'code': 200, 'message': '集群创建成功', 'data': cluster.to_dict()})


@clusters_bp.route('/<cluster_id>', methods=['PUT'])
@jwt_required()
def update_cluster(cluster_id):
    err = _require_admin()
    if err:
        return err
    cluster = K8sCluster.query.get_or_404(cluster_id)
    data = request.get_json() or {}
    for field in ('name', 'description', 'api_server', 'kubeconfig_content', 'auth_type', 'token', 'namespace', 'pvc_name', 'labels'):
        if field in data:
            setattr(cluster, field, data[field])
    if data.get('is_default'):
        K8sCluster.query.filter(K8sCluster.id != cluster_id).update({'is_default': False})
        cluster.is_default = True
    db.session.commit()
    return jsonify({'code': 200, 'message': '更新成功', 'data': cluster.to_dict()})


@clusters_bp.route('/<cluster_id>', methods=['DELETE'])
@jwt_required()
def delete_cluster(cluster_id):
    err = _require_admin()
    if err:
        return err
    cluster = K8sCluster.query.get_or_404(cluster_id)
    db.session.delete(cluster)
    db.session.commit()
    return jsonify({'code': 200, 'message': '删除成功'})


@clusters_bp.route('/<cluster_id>/test', methods=['POST'])
@jwt_required()
def test_cluster(cluster_id):
    cluster = K8sCluster.query.get_or_404(cluster_id)
    try:
        from app.services.k8s_job_executor import k8s_job_executor
        ok, msg = k8s_job_executor.test_connection(cluster)
        cluster.status = 'connected' if ok else 'error'
        cluster.status_message = msg
        db.session.commit()
        return jsonify({'code': 200, 'data': {'connected': ok, 'message': msg}})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500
