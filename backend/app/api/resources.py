from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from app import db
from app.models.resource import ResourceNode, ResourceAllocation, ClusterResource, ResourceQuota

resources_bp = Blueprint('resources', __name__)


def _require_admin():
    if get_jwt().get('role') != 'admin':
        return jsonify({'code': 403, 'message': '需要管理员权限'}), 403
    return None


@resources_bp.route('/overview', methods=['GET'])
@jwt_required()
def get_overview():
    try:
        from app.services.resource_manager import resource_manager
        data = resource_manager.get_cluster_overview()
        return jsonify({'code': 200, 'data': data})
    except Exception as e:
        cr = ClusterResource.query.order_by(ClusterResource.id.desc()).first()
        return jsonify({'code': 200, 'data': cr.to_dict() if cr else {}})


@resources_bp.route('/nodes', methods=['GET'])
@jwt_required()
def list_nodes():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    status = request.args.get('status')
    query = ResourceNode.query
    if status:
        query = query.filter_by(status=status)
    pagination = query.order_by(ResourceNode.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'code': 200,
        'data': {
            'items': [n.to_dict() for n in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
        }
    })


@resources_bp.route('/nodes/<node_id>', methods=['GET'])
@jwt_required()
def get_node(node_id):
    node = ResourceNode.query.get_or_404(node_id)
    return jsonify({'code': 200, 'data': node.to_dict()})


@resources_bp.route('/quotas', methods=['GET'])
@jwt_required()
def list_quotas():
    quotas = ResourceQuota.query.order_by(ResourceQuota.created_at.desc()).all()
    return jsonify({'code': 200, 'data': [q.to_dict() for q in quotas]})


@resources_bp.route('/quotas', methods=['POST'])
@jwt_required()
def create_quota():
    err = _require_admin()
    if err:
        return err
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '配额名称不能为空'}), 400
    if ResourceQuota.query.filter_by(name=name).first():
        return jsonify({'code': 400, 'message': '配额名称已存在'}), 400
    quota = ResourceQuota(
        name=name,
        description=data.get('description', ''),
        pool_id=data.get('pool_id'),
        max_gpus=data.get('max_gpus', 0),
        max_cpus=data.get('max_cpus', 0),
        max_memory=data.get('max_memory', 0),
        max_tasks=data.get('max_tasks', 10),
    )
    db.session.add(quota)
    db.session.commit()
    return jsonify({'code': 200, 'message': '配额创建成功', 'data': quota.to_dict()})


@resources_bp.route('/quotas/<int:quota_id>', methods=['PUT'])
@jwt_required()
def update_quota(quota_id):
    err = _require_admin()
    if err:
        return err
    quota = ResourceQuota.query.get_or_404(quota_id)
    data = request.get_json() or {}
    for field in ('name', 'description', 'max_gpus', 'max_cpus', 'max_memory', 'max_tasks', 'is_enabled'):
        if field in data:
            setattr(quota, field, data[field])
    db.session.commit()
    return jsonify({'code': 200, 'message': '更新成功', 'data': quota.to_dict()})


@resources_bp.route('/quotas/<int:quota_id>', methods=['DELETE'])
@jwt_required()
def delete_quota(quota_id):
    err = _require_admin()
    if err:
        return err
    quota = ResourceQuota.query.get_or_404(quota_id)
    db.session.delete(quota)
    db.session.commit()
    return jsonify({'code': 200, 'message': '删除成功'})


@resources_bp.route('/allocations', methods=['GET'])
@jwt_required()
def list_allocations():
    is_active = request.args.get('active', 'true').lower() == 'true'
    allocs = ResourceAllocation.query.filter_by(is_active=is_active).order_by(ResourceAllocation.allocated_at.desc()).limit(100).all()
    return jsonify({'code': 200, 'data': [a.to_dict() for a in allocs]})


@resources_bp.route('/compute-resources', methods=['GET'])
@jwt_required()
def get_compute_resources():
    """聚合计算资源端点（对齐FTv1 compute-resources）
    返回: 在线节点统计、按类型分组的资源列表、节点池列表
    """
    from app.models.node_pool import PoolNode, NodePool
    from datetime import datetime, timedelta

    # 检查心跳超时
    timeout_seconds = 90
    cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)

    all_nodes = PoolNode.query.all()
    pools = NodePool.query.filter_by(status='active').all()

    online_nodes = []
    offline_nodes = []
    for node in all_nodes:
        if node.is_online(timeout_seconds):
            online_nodes.append(node)
        else:
            offline_nodes.append(node)

    # 按类型统计
    total_cpu = sum(n.cpu_total for n in online_nodes)
    total_gpu = sum(n.gpu_total for n in online_nodes)
    total_memory = sum(n.memory_total for n in online_nodes)
    avail_cpu = sum(n.cpu_available for n in online_nodes)
    avail_gpu = sum(n.gpu_available for n in online_nodes)
    avail_memory = sum(n.memory_available for n in online_nodes)

    # 按 node_type 分组
    standalone_nodes = [n for n in online_nodes if n.node_type == 'standalone']
    k8s_nodes = [n for n in online_nodes if n.node_type == 'k8s_node']

    # GPU 节点 vs CPU-only 节点
    gpu_nodes = [n for n in online_nodes if n.gpu_total > 0]
    cpu_only_nodes = [n for n in online_nodes if n.gpu_total == 0]

    # 构建资源选项列表（供前端选择器使用）
    resources = []
    if cpu_only_nodes:
        resources.append({
            'type': 'cpu',
            'label': f'CPU 节点 ({len(cpu_only_nodes)} 台在线)',
            'node_count': len(cpu_only_nodes),
            'total_cpu': sum(n.cpu_total for n in cpu_only_nodes),
            'available_cpu': sum(n.cpu_available for n in cpu_only_nodes),
        })
    if gpu_nodes:
        gpu_models = list(set(n.gpu_model for n in gpu_nodes if n.gpu_model))
        resources.append({
            'type': 'gpu',
            'label': f'GPU 节点 ({len(gpu_nodes)} 台在线, {sum(n.gpu_total for n in gpu_nodes)} GPU)',
            'node_count': len(gpu_nodes),
            'total_gpu': sum(n.gpu_total for n in gpu_nodes),
            'available_gpu': sum(n.gpu_available for n in gpu_nodes),
            'gpu_models': gpu_models,
        })

    return jsonify({
        'code': 200,
        'data': {
            'summary': {
                'total_nodes': len(all_nodes),
                'online_nodes': len(online_nodes),
                'offline_nodes': len(offline_nodes),
                'total_cpu': total_cpu,
                'total_gpu': total_gpu,
                'total_memory': total_memory,
                'available_cpu': avail_cpu,
                'available_gpu': avail_gpu,
                'available_memory': avail_memory,
            },
            'resources': resources,
            'node_pools': [p.to_dict() for p in pools],
            'standalone_nodes': len(standalone_nodes),
            'k8s_nodes': len(k8s_nodes),
            'node_details': [n.to_dict() for n in online_nodes],
        }
    })
