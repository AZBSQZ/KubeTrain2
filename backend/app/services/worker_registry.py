"""
Worker 注册中心 - 独立 Worker 自注册体系
负责：Worker 注册/注销、心跳检测、自动离线标记、能力发现、任务槽位管理
"""
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from flask import current_app

from app import db
from app.models.node_pool import NodePool, PoolNode, WorkerTaskSlot

logger = logging.getLogger(__name__)


class TEWorkerRegistry:
    """Worker 注册中心"""

    def __init__(self):
        self._running = False
        self._health_thread = None
        self._lock = threading.Lock()

    # ==================== 生命周期 ====================

    def start(self, app):
        if self._running:
            return
        self._running = True
        self._health_thread = threading.Thread(
            target=self._health_loop, args=(app,), daemon=True
        )
        self._health_thread.start()
        logger.info("TE Worker Registry started")

    def stop(self):
        self._running = False
        if self._health_thread:
            self._health_thread.join(timeout=5)
        logger.info("TE Worker Registry stopped")

    def _health_loop(self, app):
        with app.app_context():
            while self._running:
                try:
                    self._check_worker_health()
                except Exception as e:
                    logger.error(f"TE Worker health check error: {e}")
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                time.sleep(current_app.config.get('WORKER_HEALTH_INTERVAL', 30))

    # ==================== 注册 ====================

    def register(self, data: dict) -> Tuple[bool, str, Optional[dict]]:
        """
        Worker 自注册
        支持两种模式：
        1. 指定 pool_id 加入已有池
        2. 不指定 pool_id，自动创建或加入默认池
        """
        with self._lock:
            try:
                hostname = data.get('hostname', '')
                ip_address = data.get('ip_address', '')

                if not hostname and not ip_address:
                    return False, 'hostname or ip_address is required', None

                # 检查是否已注册（按 worker_id → hostname → ip 多级去重）
                existing = None
                worker_id = data.get('worker_id')
                if worker_id:
                    existing = PoolNode.query.filter_by(worker_id=worker_id).first()
                if not existing and hostname:
                    existing = PoolNode.query.filter_by(hostname=hostname, node_type='standalone').first()
                if not existing and ip_address:
                    existing = PoolNode.query.filter_by(ip_address=ip_address, node_type='standalone').first()

                if existing:
                    # 重新注册（Agent 重启场景）— 同步更新 worker_id 以适配稳定ID
                    if worker_id and existing.worker_id != worker_id:
                        logger.info(f"TE Worker {existing.name}: updating worker_id {existing.worker_id} → {worker_id}")
                        existing.worker_id = worker_id
                    self._update_worker_info(existing, data)
                    existing.status = 'idle'
                    existing.registered_at = datetime.utcnow()
                    existing.deregistered_at = None
                    existing.last_heartbeat = datetime.utcnow()
                    db.session.commit()
                    logger.info(f"TE Worker re-registered: {existing.name} ({existing.ip_address})")
                    return True, 'Worker re-registered', existing.to_dict()

                # 新注册
                pool_id = data.get('pool_id')
                pool = None
                if pool_id:
                    pool = NodePool.query.get(pool_id)
                    if not pool:
                        return False, f'Pool {pool_id} not found', None
                else:
                    pool = self._get_or_create_default_pool()

                new_worker_id = worker_id or str(uuid.uuid4())
                node = PoolNode(
                    id=str(uuid.uuid4()),
                    pool_id=pool.id,
                    name=data.get('name', hostname or ip_address),
                    hostname=hostname,
                    ip_address=ip_address,
                    port=data.get('port', 8005),
                    worker_id=new_worker_id,
                    node_type='standalone',
                    status='idle',
                    registered_at=datetime.utcnow(),
                    last_heartbeat=datetime.utcnow(),
                )
                self._update_worker_info(node, data)

                db.session.add(node)
                pool.current_nodes = PoolNode.query.filter_by(pool_id=pool.id).count() + 1
                db.session.commit()

                logger.info(f"TE Worker registered: {node.name} ({node.ip_address}) -> pool {pool.name}")
                return True, 'Worker registered', node.to_dict()

            except Exception as e:
                db.session.rollback()
                logger.error(f"TE Worker register error: {e}")
                return False, str(e), None

    def _update_worker_info(self, node: PoolNode, data: dict):
        """从注册/心跳数据更新 Worker 信息"""
        if data.get('hostname'):
            node.hostname = data['hostname']
        if data.get('ip_address'):
            node.ip_address = data['ip_address']
        if data.get('port'):
            node.port = data['port']
        if data.get('name'):
            node.name = data['name']

        # 硬件信息
        if data.get('cpu_total') is not None:
            node.cpu_total = data['cpu_total']
        if data.get('memory_total') is not None:
            node.memory_total = data['memory_total']
        if data.get('gpu_total') is not None:
            node.gpu_total = data['gpu_total']
        if data.get('gpu_model'):
            node.gpu_model = data['gpu_model']
        if data.get('gpu_details'):
            node.gpu_details = data['gpu_details']
        if data.get('storage_total') is not None:
            node.storage_total = data['storage_total']

        # 能力与环境
        if data.get('capabilities'):
            node.capabilities = data['capabilities']
        if data.get('labels'):
            node.labels = data['labels']
        if data.get('container_runtime'):
            node.container_runtime = data['container_runtime']
        if data.get('os_info'):
            node.os_info = data['os_info']
        if data.get('agent_version'):
            node.agent_version = data['agent_version']
        if data.get('python_version'):
            node.python_version = data['python_version']
        if data.get('cuda_version'):
            node.cuda_version = data['cuda_version']
        if data.get('nccl_available') is not None:
            node.nccl_available = data['nccl_available']
        if data.get('docker_available') is not None:
            node.docker_available = data['docker_available']
        if data.get('max_tasks') is not None:
            node.max_tasks = data['max_tasks']
        if data.get('heartbeat_interval'):
            node.heartbeat_interval = data['heartbeat_interval']
        if data.get('network_bandwidth_mbps'):
            node.network_bandwidth_mbps = data['network_bandwidth_mbps']

    # ==================== 注销 ====================

    def deregister(self, worker_id: str) -> Tuple[bool, str]:
        with self._lock:
            try:
                node = PoolNode.query.filter_by(worker_id=worker_id).first()
                if not node:
                    # 尝试用 id 查找
                    node = PoolNode.query.get(worker_id)
                if not node:
                    return False, 'Worker not found'

                node_name = node.name
                node_ip = node.ip_address
                pool_id = node.pool_id

                # 释放所有活跃槽位
                active_slots = WorkerTaskSlot.query.filter_by(
                    worker_id=node.id, status='allocated'
                ).all()
                for slot in active_slots:
                    slot.status = 'released'
                    slot.released_at = datetime.utcnow()

                # 删除节点记录
                db.session.delete(node)

                # 更新池计数
                pool = NodePool.query.get(pool_id)
                if pool:
                    pool.current_nodes = max(0, (pool.current_nodes or 1) - 1)

                db.session.commit()
                logger.info(f"TE Worker deregistered and deleted: {node_name} ({node_ip})")
                return True, 'Worker deregistered'

            except Exception as e:
                db.session.rollback()
                logger.error(f"TE Worker deregister error: {e}")
                return False, str(e)

    # ==================== 心跳 ====================

    def heartbeat(self, worker_id: str, data: dict) -> Tuple[bool, str, Optional[dict]]:
        """处理 Worker 心跳，返回待执行的指令"""
        try:
            node = PoolNode.query.filter_by(worker_id=worker_id).first()
            if not node:
                return False, 'Worker not registered. Please register first.', None

            # 更新利用率
            node.cpu_utilization = data.get('cpu_utilization', node.cpu_utilization)
            node.memory_utilization = data.get('memory_utilization', node.memory_utilization)
            node.gpu_utilization = data.get('gpu_utilization', node.gpu_utilization)
            node.tasks_running = data.get('tasks_running', node.tasks_running)
            node.docker_available = data.get('docker_available', node.docker_available)
            node.last_heartbeat = datetime.utcnow()

            # 状态更新
            if node.status == 'offline':
                node.status = 'idle'
                node.status_message = '心跳恢复在线'
            else:
                node.status_message = ''
            if node.tasks_running > 0:
                node.status = 'busy'
            elif node.status == 'busy':
                node.status = 'idle'

            # 如果携带了硬件信息更新
            if data.get('cpu_total') is not None:
                node.cpu_total = data['cpu_total']
            if data.get('memory_total') is not None:
                node.memory_total = data['memory_total']
            if data.get('gpu_details'):
                node.gpu_details = data['gpu_details']

            db.session.commit()

            # 构造响应指令
            commands = self._get_pending_commands(node)

            return True, 'OK', {
                'node_id': node.id,
                'status': node.status,
                'commands': commands,
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"TE Worker heartbeat error: {e}")
            return False, str(e), None

    def _get_pending_commands(self, node: PoolNode) -> list:
        """获取待发送给 Worker 的指令（预留扩展点）"""
        commands = []
        # 未来可扩展：远程启动任务、停止任务、更新配置等
        return commands

    # ==================== 健康检查 ====================

    def _check_worker_health(self):
        """检查所有 Worker 健康状态，超时标记为离线
        注意：只检查 standalone 节点，K8s 节点状态由集群同步管理"""
        try:
            db.session.remove()
        except Exception:
            pass

        timeout_seconds = current_app.config.get('WORKER_TIMEOUT', 90)
        cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)

        stale_workers = PoolNode.query.filter(
            PoolNode.status.in_(['idle', 'busy']),
            PoolNode.node_type != 'k8s_node',
            PoolNode.last_heartbeat < cutoff
        ).all()

        for worker in stale_workers:
            worker.status = 'offline'
            worker.status_message = f'Heartbeat timeout (>{timeout_seconds}s)'
            logger.warning(f"TE Worker offline (timeout): {worker.name} ({worker.ip_address})")

            # 释放超时 Worker 的活跃槽位
            active_slots = WorkerTaskSlot.query.filter_by(
                worker_id=worker.id, status='allocated'
            ).all()
            for slot in active_slots:
                slot.status = 'released'
                slot.released_at = datetime.utcnow()
            worker.tasks_running = 0
            worker.cpu_allocated = 0
            worker.memory_allocated = 0
            worker.gpu_allocated = 0

        if stale_workers:
            db.session.commit()

            # 更新所有受影响池的在线节点计数
            affected_pools = set(w.pool_id for w in stale_workers)
            for pool_id in affected_pools:
                pool = NodePool.query.get(pool_id)
                if pool:
                    pool.current_nodes = PoolNode.query.filter(
                        PoolNode.pool_id == pool_id,
                        PoolNode.status != 'offline'
                    ).count()
            db.session.commit()

    # ==================== 发现与查询 ====================

    def get_online_workers(self, pool_id: str = None, capabilities: list = None) -> List[PoolNode]:
        """获取在线 Worker 列表，支持按池和能力过滤"""
        query = PoolNode.query.filter(PoolNode.status.in_(['idle', 'busy']))

        if pool_id:
            query = query.filter_by(pool_id=pool_id)

        workers = query.all()

        # 过滤能力
        if capabilities:
            required = set(capabilities)
            workers = [w for w in workers if w.is_online() and required.issubset(set(w.capabilities or []))]
        else:
            workers = [w for w in workers if w.is_online()]

        return workers

    def find_best_worker(self, cpu_req=0, mem_req=0, gpu_req=0,
                         required_caps=None, pool_id=None) -> Optional[PoolNode]:
        """为任务找到最佳 Worker（负载最低 + 能力匹配）"""
        candidates = self.get_online_workers(pool_id=pool_id, capabilities=required_caps)
        eligible = [w for w in candidates if w.can_accept_task(cpu_req, mem_req, gpu_req, required_caps)]

        if not eligible:
            return None

        # 按负载排序：(GPU利用率*0.4 + CPU利用率*0.3 + 内存利用率*0.3)
        eligible.sort(key=lambda w: (
            (w.gpu_utilization or 0) * 0.4 +
            (w.cpu_utilization or 0) * 0.3 +
            (w.memory_utilization or 0) * 0.3
        ))

        return eligible[0]

    def allocate_task_to_worker(self, worker: PoolNode, task_id: str,
                                 cpu=0, memory=0, gpu=0) -> Optional[WorkerTaskSlot]:
        """将任务分配到 Worker 并创建槽位记录"""
        try:
            slot = WorkerTaskSlot(
                worker_id=worker.id,
                task_id=task_id,
                cpu_allocated=cpu,
                memory_allocated=memory,
                gpu_allocated=gpu,
                status='allocated',
                assigned_at=datetime.utcnow()
            )
            db.session.add(slot)
            worker.allocate_slot(task_id, cpu, memory, gpu)
            db.session.commit()
            logger.info(f"TE Task {task_id} allocated to worker {worker.name}")
            return slot
        except Exception as e:
            db.session.rollback()
            logger.error(f"TE Task allocation error: {e}")
            return None

    def release_task_from_worker(self, task_id: str) -> bool:
        """释放任务占用的 Worker 槽位"""
        try:
            slots = WorkerTaskSlot.query.filter_by(
                task_id=task_id, status='allocated'
            ).all()

            for slot in slots:
                slot.status = 'released'
                slot.released_at = datetime.utcnow()

                worker = PoolNode.query.get(slot.worker_id)
                if worker:
                    worker.release_slot(task_id, slot.cpu_allocated,
                                       slot.memory_allocated, slot.gpu_allocated)

            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"TE Task release error: {e}")
            return False

    def get_worker_stats(self) -> dict:
        """获取 Worker 注册中心统计"""
        total = PoolNode.query.count()
        online = PoolNode.query.filter(PoolNode.status.in_(['idle', 'busy'])).count()
        idle = PoolNode.query.filter_by(status='idle').count()
        busy = PoolNode.query.filter_by(status='busy').count()
        offline = PoolNode.query.filter_by(status='offline').count()

        total_gpu = db.session.query(db.func.sum(PoolNode.gpu_total)).filter(
            PoolNode.status.in_(['idle', 'busy'])
        ).scalar() or 0
        allocated_gpu = db.session.query(db.func.sum(PoolNode.gpu_allocated)).filter(
            PoolNode.status.in_(['idle', 'busy'])
        ).scalar() or 0

        active_slots = WorkerTaskSlot.query.filter_by(status='allocated').count()

        pools = NodePool.query.all()

        return {
            'total_workers': total,
            'online_workers': online,
            'idle_workers': idle,
            'busy_workers': busy,
            'offline_workers': offline,
            'total_gpu': total_gpu,
            'allocated_gpu': allocated_gpu,
            'available_gpu': total_gpu - allocated_gpu,
            'active_task_slots': active_slots,
            'pools': [{'id': p.id, 'name': p.name, 'status': p.status,
                        'current_nodes': p.current_nodes, 'max_nodes': p.max_nodes} for p in pools]
        }

    # ==================== 查询单个 Worker ====================

    def get_worker(self, worker_id_or_node_id: str) -> Optional[dict]:
        """根据 node.id 或 worker_id 获取在线 Worker 信息（供调度器 dispatch 使用）"""
        node = PoolNode.query.get(worker_id_or_node_id)
        if not node:
            node = PoolNode.query.filter_by(worker_id=worker_id_or_node_id).first()
        if not node or not node.is_online():
            return None
        return {
            'id': node.id,
            'worker_id': node.worker_id,
            'name': node.name,
            'hostname': node.hostname,
            'ip_address': node.ip_address,
            'port': node.port or 8005,
            'status': node.status,
            'gpu_total': node.gpu_total or 0,
            'cpu_total': node.cpu_total or 0,
            'memory_total': node.memory_total or 0,
            'node_type': getattr(node, 'node_type', 'standalone'),
        }

    # ==================== 工具方法 ====================

    def _get_or_create_default_pool(self) -> NodePool:
        """获取或创建默认节点池"""
        pool = NodePool.query.filter_by(name='default').first()
        if not pool:
            pool = NodePool(
                id=str(uuid.uuid4()),
                name='default',
                description='Default worker pool (auto-created)',
                provider='bare_metal',
                status='active',
            )
            db.session.add(pool)
            db.session.flush()
        return pool


# 全局实例
worker_registry = TEWorkerRegistry()
