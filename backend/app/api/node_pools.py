import uuid
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from app import db
from app.models.node_pool import NodePool, PoolNode

node_pools_bp = Blueprint('node_pools', __name__)


def _require_admin():
    if get_jwt().get('role') != 'admin':
        return jsonify({'code': 403, 'message': '需要管理员权限'}), 403
    return None


@node_pools_bp.route('', methods=['GET'])
@jwt_required()
def list_pools():
    pools = NodePool.query.order_by(NodePool.created_at.desc()).all()
    result = []
    for pool in pools:
        d = pool.to_dict()
        nodes = pool.nodes.all()
        d['node_count'] = len(nodes)
        d['online_count'] = sum(1 for n in nodes if n.is_online())
        d['total_gpus'] = sum(n.gpu_total for n in nodes)
        d['available_gpus'] = sum(n.gpu_available for n in nodes)
        result.append(d)
    return jsonify({'code': 200, 'data': result})


@node_pools_bp.route('/<pool_id>', methods=['GET'])
@jwt_required()
def get_pool(pool_id):
    pool = NodePool.query.get_or_404(pool_id)
    d = pool.to_dict()
    nodes = pool.nodes.order_by(PoolNode.created_at.desc()).all()
    d['nodes'] = [n.to_dict() for n in nodes]
    return jsonify({'code': 200, 'data': d})


@node_pools_bp.route('', methods=['POST'])
@jwt_required()
def create_pool():
    err = _require_admin()
    if err:
        return err
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '节点池名称不能为空'}), 400
    if NodePool.query.filter_by(name=name).first():
        return jsonify({'code': 400, 'message': '节点池名称已存在'}), 400
    pool = NodePool(
        id=str(uuid.uuid4()),
        name=name,
        description=data.get('description', ''),
        provider=data.get('provider', 'bare_metal'),
        cpu_per_node=data.get('cpu_per_node', 4),
        memory_per_node=data.get('memory_per_node', 8192),
        gpu_per_node=data.get('gpu_per_node', 0),
        gpu_type=data.get('gpu_type', ''),
        max_nodes=data.get('max_nodes', 10),
        labels=data.get('labels'),
    )
    db.session.add(pool)
    db.session.commit()
    return jsonify({'code': 200, 'message': '节点池创建成功', 'data': pool.to_dict()})


@node_pools_bp.route('/<pool_id>', methods=['PUT'])
@jwt_required()
def update_pool(pool_id):
    err = _require_admin()
    if err:
        return err
    pool = NodePool.query.get_or_404(pool_id)
    data = request.get_json() or {}
    for field in ('name', 'description', 'max_nodes', 'gpu_type', 'labels', 'status'):
        if field in data:
            setattr(pool, field, data[field])
    db.session.commit()
    return jsonify({'code': 200, 'message': '更新成功', 'data': pool.to_dict()})


@node_pools_bp.route('/<pool_id>', methods=['DELETE'])
@jwt_required()
def delete_pool(pool_id):
    err = _require_admin()
    if err:
        return err
    pool = NodePool.query.get_or_404(pool_id)
    db.session.delete(pool)
    db.session.commit()
    return jsonify({'code': 200, 'message': '删除成功'})


@node_pools_bp.route('/<pool_id>/nodes', methods=['POST'])
@jwt_required()
def add_node(pool_id):
    err = _require_admin()
    if err:
        return err
    pool = NodePool.query.get_or_404(pool_id)
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '节点名称不能为空'}), 400
    node = PoolNode(
        id=str(uuid.uuid4()),
        pool_id=pool_id,
        name=name,
        node_type=data.get('node_type', 'standalone'),
        cluster_id=data.get('cluster_id'),
        hostname=data.get('hostname', ''),
        ip_address=data.get('ip_address', ''),
        port=data.get('port', 8005),
        max_tasks=data.get('max_tasks', 2),
        labels=data.get('labels'),
    )
    db.session.add(node)
    db.session.commit()
    return jsonify({'code': 200, 'message': '节点添加成功', 'data': node.to_dict()})


@node_pools_bp.route('/<pool_id>/nodes/<node_id>', methods=['DELETE'])
@jwt_required()
def remove_node(pool_id, node_id):
    err = _require_admin()
    if err:
        return err
    node = PoolNode.query.filter_by(id=node_id, pool_id=pool_id).first_or_404()
    db.session.delete(node)
    db.session.commit()
    return jsonify({'code': 200, 'message': '节点删除成功'})
