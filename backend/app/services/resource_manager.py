"""
资源管理器 - 从KubeTrain迁入并适配FT-taitp
管理集群资源池、分配/释放资源、配额管理，从 Kubernetes API 同步节点信息
配置项统一使用 TE_ 前缀
"""
import logging
import math
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from flask import current_app

from app import db
from app.models.task import Task
from app.models.resource import (
    ResourceNode, ResourceAllocation, ClusterResource, ResourceQuota
)
from app.models.node_pool import PoolNode, NodePool

logger = logging.getLogger(__name__)


class TEResourceManager:
    """资源管理器"""

    def __init__(self):
        self._running = False
        self._sync_thread = None
        self._lock = threading.Lock()
        self._cluster_status = 'unknown'
        self._cluster_message = '集群状态尚未检测'
        self._last_sync_at = None
        self._last_success_at = None
        self._last_error = None
        self._initial_sync_completed = False
        self._last_nodes_snapshot = []

    def start(self, app):
        if self._running:
            return
        self._running = True
        self._sync_thread = threading.Thread(
            target=self._sync_loop, args=(app,), daemon=True
        )
        self._sync_thread.start()
        logger.info("TE Resource manager started")

    def stop(self):
        self._running = False
        if self._sync_thread:
            self._sync_thread.join(timeout=5)
        logger.info("TE Resource manager stopped")

    def _sync_loop(self, app):
        with app.app_context():
            while self._running:
                self.sync_now()
                time.sleep(30)

    def sync_now(self):
        now = datetime.utcnow()
        try:
            try:
                db.session.remove()
            except Exception:
                pass

            # 同步所有已注册的 K8s 集群节点
            k8s_nodes = self._sync_all_k8s_clusters()
            # 同步统一资源汇总（包含 k8s_node + standalone）
            self._update_unified_summary()
            self._check_node_health()

            # 统计所有在线节点（含 standalone agent）
            all_online = PoolNode.query.filter(
                PoolNode.status.in_(['idle', 'busy', 'online'])
            ).count()
            total_nodes = PoolNode.query.count()

            with self._lock:
                if total_nodes > 0:
                    self._cluster_status = 'online'
                    self._cluster_message = f'资源池共 {total_nodes} 个节点，在线 {all_online} 个'
                else:
                    self._cluster_status = 'empty'
                    self._cluster_message = '资源池为空，请注册集群或启动Agent'

                self._last_sync_at = now
                self._last_success_at = now
                self._last_error = None
                self._initial_sync_completed = True
            return True, self._cluster_message
        except Exception as e:
            message = str(e)
            with self._lock:
                self._last_sync_at = now
                self._last_error = message
                self._initial_sync_completed = True
                self._cluster_status = 'error'
                self._cluster_message = f'资源同步异常：{message}'
            logger.error(f"TE Resource sync error: {e}")
            return False, message

    def get_cluster_overview(self):
        with self._lock:
            return {
                'status': self._cluster_status,
                'message': self._cluster_message,
                'last_sync_at': self._last_sync_at.isoformat() if self._last_sync_at else None,
                'last_success_at': self._last_success_at.isoformat() if self._last_success_at else None,
                'last_error': self._last_error,
                'initial_sync_completed': self._initial_sync_completed,
            }

    def get_nodes_snapshot(self):
        return list(self._last_nodes_snapshot)

    def _sync_all_k8s_clusters(self):
        """遍历所有已注册的 K8sCluster，同步节点到 pool_nodes"""
        from app.models.k8s_cluster import K8sCluster
        clusters = K8sCluster.query.filter_by(status='connected').all()
        total_synced = 0
        for cluster in clusters:
            try:
                from app.api.clusters import _sync_cluster_nodes
                ok, msg = _sync_cluster_nodes(cluster)
                if ok:
                    total_synced += cluster.node_count or 0
            except Exception as e:
                logger.warning(f"TE: Failed to sync cluster {cluster.name}: {e}")

        # 同时保持旧的 resource_nodes 同步（兼容）
        try:
            self._sync_nodes_from_k8s_legacy()
        except Exception:
            pass

        return total_synced

    def _sync_nodes_from_k8s_legacy(self):
        """旧逻辑：从默认K8s配置同步到 resource_nodes（兼容）"""
        timeout_seconds = current_app.config.get('K8S_API_TIMEOUT', 5)
        namespace = current_app.config.get('K8S_NAMESPACE', 'kubetrain')

        from app.services.k8s_client import get_core_api
        try:
            core_api = get_core_api()
            nodes = core_api.list_node(_request_timeout=timeout_seconds)
        except Exception:
            return []

        running_pods = []
        try:
            pods = core_api.list_namespaced_pod(
                namespace=namespace, field_selector='status.phase=Running',
                _request_timeout=timeout_seconds
            )
            running_pods = pods.items
        except Exception:
            pass

        training_pods_by_node = {}
        for pod in running_pods:
            node_name = pod.spec.node_name if pod.spec else None
            if not node_name:
                continue
            labels = pod.metadata.labels or {} if pod.metadata else {}
            if labels.get('app') == 'kubetrain' and labels.get('task_id'):
                training_pods_by_node[node_name] = training_pods_by_node.get(node_name, 0) + 1

        synced_ids = set()
        nodes_snapshot = []

        for k8s_node in nodes.items:
            node_id = k8s_node.metadata.uid
            node_name = k8s_node.metadata.name
            synced_ids.add(node_id)

            allocatable = k8s_node.status.allocatable or {}
            capacity = k8s_node.status.capacity or {}

            cpu_total = self._parse_cpu(capacity.get('cpu', '0'))
            cpu_available = self._parse_cpu(allocatable.get('cpu', '0'))
            memory_total = self._parse_memory(capacity.get('memory', '0'))
            memory_available = self._parse_memory(allocatable.get('memory', '0'))
            gpu_total = int(capacity.get('nvidia.com/gpu', 0))
            gpu_available = int(allocatable.get('nvidia.com/gpu', 0))

            status = 'online'
            for condition in (k8s_node.status.conditions or []):
                if condition.type == 'Ready' and condition.status != 'True':
                    status = 'error'
                    break

            ip_address = None
            for addr in (k8s_node.status.addresses or []):
                if addr.type == 'InternalIP':
                    ip_address = addr.address
                    break

            cpu_utilization = 0.0
            if cpu_total > 0:
                used_cpu = cpu_total - cpu_available
                cpu_utilization = round(used_cpu / cpu_total * 100, 1) if used_cpu > 0 else 0.0

            memory_utilization = 0.0
            if memory_total > 0:
                used_mem = memory_total - memory_available
                memory_utilization = round(used_mem / memory_total * 100, 1) if used_mem > 0 else 0.0

            db_node = ResourceNode.query.get(node_id)
            if not db_node:
                db_node = ResourceNode(id=node_id)
                db.session.add(db_node)

            db_node.name = node_name
            db_node.hostname = node_name
            db_node.ip_address = ip_address
            db_node.status = status
            db_node.cpu_total = cpu_total
            db_node.cpu_available = cpu_available
            db_node.memory_total = memory_total
            db_node.memory_available = memory_available
            db_node.gpu_total = gpu_total
            db_node.gpu_available = gpu_available
            db_node.cpu_utilization = cpu_utilization
            db_node.memory_utilization = memory_utilization
            db_node.docker_available = True
            db_node.last_heartbeat = datetime.utcnow()

            nodes_snapshot.append({
                'id': node_id, 'name': node_name, 'ip_address': ip_address,
                'status': status, 'cpu_total': cpu_total, 'cpu_available': cpu_available,
                'memory_total': memory_total, 'memory_available': memory_available,
                'gpu_total': gpu_total, 'gpu_available': gpu_available,
                'cpu_utilization': cpu_utilization, 'memory_utilization': memory_utilization,
                'training_tasks': training_pods_by_node.get(node_name, 0),
            })

        stale_nodes = ResourceNode.query.filter(ResourceNode.id.notin_(synced_ids)).all()
        for node in stale_nodes:
            node.status = 'offline'
            node.cpu_available = 0
            node.memory_available = 0
            node.gpu_available = 0

        db.session.commit()
        self._last_nodes_snapshot = nodes_snapshot
        return nodes_snapshot

    def _build_nodes_snapshot_from_db(self):
        try:
            nodes = PoolNode.query.all()
            return [n.to_dict() for n in nodes]
        except Exception:
            return []

    def _check_node_health(self):
        """检查 pool_nodes 和 resource_nodes 的健康状态"""
        try:
            timeout = timedelta(seconds=120)
            now = datetime.utcnow()
            # 检查 pool_nodes (standalone)
            pool_nodes = PoolNode.query.filter(
                PoolNode.status.in_(['idle', 'busy']),
                PoolNode.node_type == 'standalone'
            ).all()
            for node in pool_nodes:
                if node.last_heartbeat and (now - node.last_heartbeat) > timeout:
                    node.status = 'offline'
                    logger.warning(f"TE: PoolNode {node.name} marked offline (heartbeat timeout)")
            # 检查 resource_nodes (旧兼容)
            res_nodes = ResourceNode.query.filter(ResourceNode.status == 'online').all()
            for node in res_nodes:
                if node.last_heartbeat and (now - node.last_heartbeat) > timeout:
                    node.status = 'offline'
                    logger.warning(f"TE: ResourceNode {node.name} marked offline (heartbeat timeout)")
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"TE: Health check error: {e}")

    def _update_unified_summary(self):
        """统一汇总 pool_nodes 中所有在线节点的资源"""
        try:
            all_pool_nodes = PoolNode.query.all()
            summary = ClusterResource.query.first()
            if not summary:
                summary = ClusterResource()
                db.session.add(summary)

            online_nodes = [n for n in all_pool_nodes if n.status in ('idle', 'busy', 'online')]

            summary.total_nodes = len(all_pool_nodes)
            summary.online_nodes = len(online_nodes)
            summary.total_gpus = sum(n.gpu_total or 0 for n in all_pool_nodes)
            summary.available_gpus = sum(n.gpu_available for n in online_nodes)
            summary.total_cpus = sum(n.cpu_total or 0 for n in all_pool_nodes)
            summary.available_cpus = sum(n.cpu_available for n in online_nodes)
            summary.total_memory = sum(n.memory_total or 0 for n in all_pool_nodes)
            summary.available_memory = sum(n.memory_available for n in online_nodes)

            if online_nodes:
                summary.avg_cpu_utilization = round(sum(n.cpu_utilization or 0 for n in online_nodes) / len(online_nodes), 1)
                summary.avg_memory_utilization = round(sum(n.memory_utilization or 0 for n in online_nodes) / len(online_nodes), 1)
                summary.avg_gpu_utilization = round(sum(n.gpu_utilization or 0 for n in online_nodes) / len(online_nodes), 1)
            else:
                summary.avg_cpu_utilization = 0
                summary.avg_memory_utilization = 0
                summary.avg_gpu_utilization = 0

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"TE: Failed to update unified summary: {e}")

    def has_online_k8s_nodes(self):
        """检查是否有在线的 K8s 节点"""
        return PoolNode.query.filter(
            PoolNode.node_type == 'k8s_node',
            PoolNode.status.in_(['idle', 'busy', 'online'])
        ).count() > 0

    def has_online_agents(self):
        """检查是否有在线的 standalone agent"""
        return PoolNode.query.filter(
            PoolNode.node_type == 'standalone',
            PoolNode.status.in_(['idle', 'busy'])
        ).count() > 0

    def get_resource_availability(self):
        """返回资源可用性信息，供前端智能提示"""
        k8s_online = PoolNode.query.filter(
            PoolNode.node_type == 'k8s_node',
            PoolNode.status.in_(['idle', 'busy', 'online'])
        ).count()
        agent_online = PoolNode.query.filter(
            PoolNode.node_type == 'standalone',
            PoolNode.status.in_(['idle', 'busy'])
        ).count()
        k8s_gpus = db.session.query(
            db.func.coalesce(db.func.sum(PoolNode.gpu_total), 0)
        ).filter(
            PoolNode.node_type == 'k8s_node',
            PoolNode.status.in_(['idle', 'busy', 'online'])
        ).scalar()
        agent_gpus = db.session.query(
            db.func.coalesce(db.func.sum(PoolNode.gpu_total), 0)
        ).filter(
            PoolNode.node_type == 'standalone',
            PoolNode.status.in_(['idle', 'busy'])
        ).scalar()
        return {
            'k8s_nodes_online': k8s_online,
            'agent_nodes_online': agent_online,
            'k8s_gpus': int(k8s_gpus),
            'agent_gpus': int(agent_gpus),
            'has_k8s': k8s_online > 0,
            'has_agent': agent_online > 0,
        }

    def allocate_resources(self, task: Task) -> Tuple[bool, str]:
        with self._lock:
            try:
                num_nodes = task.num_nodes or 1
                per_node_gpu = task.gpu_limit or 0
                per_node_cpu = self._parse_cpu(task.cpu_request)
                per_node_memory = self._parse_memory(task.memory_request)

                total_gpu = per_node_gpu * num_nodes
                total_cpu = per_node_cpu * num_nodes
                total_memory = per_node_memory * num_nodes

                quota = self._get_task_quota(task)
                quota_ok, quota_msg = self._check_quota(quota, total_gpu, total_cpu, total_memory)
                if not quota_ok:
                    return False, f"Quota check failed: {quota_msg}"

                summary = ClusterResource.query.first()
                if not summary:
                    summary = ClusterResource()
                    db.session.add(summary)

                # 判断是否有在线 K8s 节点（K8s 模式由 K8s 调度器处理节点选择）
                has_k8s = self.has_online_k8s_nodes()

                # 判断任务的实际执行模式
                task_exec_mode = getattr(task, 'execution_mode', 'auto') or 'auto'
                is_k8s_mode = task_exec_mode == 'k8s' or (task_exec_mode == 'auto' and has_k8s)

                if num_nodes > 1 or has_k8s:
                    # 多节点 DDP 或 K8s 模式：K8s 调度器负责实际的 per-node 资源分配
                    # GPU 检查：K8s 节点可能未上报 nvidia.com/gpu（如无GPU驱动），
                    # 此时 TE 汇总的 available_gpus=0，但 K8s 仍可调度（gloo后端/CPU训练）
                    # 因此对 K8s 模式仅发出警告，不阻塞调度，让 K8s Job 自行 Pending
                    if total_gpu > 0 and summary.available_gpus < total_gpu:
                        if is_k8s_mode:
                            logger.warning(
                                f"TE Task {task.id}: GPU request ({total_gpu}) exceeds reported "
                                f"available ({summary.available_gpus}), proceeding anyway (K8s will schedule)")
                        else:
                            return False, f"Insufficient GPU: need {total_gpu} (={per_node_gpu}×{num_nodes}), available {summary.available_gpus}"
                    if is_k8s_mode:
                        # K8s 模式：CPU/内存也仅警告，K8s 调度器有完整的节点资源视图
                        if summary.available_cpus < total_cpu:
                            logger.warning(
                                f"TE Task {task.id}: CPU request ({total_cpu}) exceeds reported "
                                f"available ({summary.available_cpus}), proceeding anyway (K8s will schedule)")
                        if summary.available_memory < total_memory:
                            logger.warning(
                                f"TE Task {task.id}: Memory request ({total_memory}MB) exceeds reported "
                                f"available ({summary.available_memory}MB), proceeding anyway (K8s will schedule)")
                    else:
                        if summary.available_cpus < total_cpu:
                            return False, f"Insufficient CPU: need {total_cpu}, available {summary.available_cpus}"
                        if summary.available_memory < total_memory:
                            return False, f"Insufficient memory: need {total_memory}MB, available {summary.available_memory}MB"
                    node_id = None
                else:
                    # 单节点 + 无K8s：找最佳 standalone 节点
                    node = self._select_best_node(per_node_gpu, per_node_cpu, per_node_memory)
                    if not node:
                        # 检查是否完全无节点（无K8s、无Agent、无ResourceNode）
                        has_any_node = (
                            ResourceNode.query.filter(ResourceNode.status == 'online').count() > 0
                            or self.has_online_agents()
                        )
                        if not has_any_node and per_node_gpu == 0:
                            # 无任何节点 + 无GPU需求：允许通过，将回退到本地进程执行
                            logger.info(f"TE Task {task.id}: no nodes registered, allowing local execution fallback")
                        else:
                            if per_node_gpu > 0 and summary.available_gpus < per_node_gpu:
                                return False, f"Insufficient GPU: need {per_node_gpu}, available {summary.available_gpus}"
                            if summary.available_cpus < per_node_cpu:
                                return False, f"Insufficient CPU: need {per_node_cpu}, available {summary.available_cpus}"
                            if summary.available_memory < per_node_memory:
                                return False, f"Insufficient memory: need {per_node_memory}MB, available {summary.available_memory}MB"
                    node_id = node.id if node else None
                    if node:
                        node.gpu_available = max(0, node.gpu_available - per_node_gpu)
                        node.cpu_available = max(0, node.cpu_available - per_node_cpu)
                        node.memory_available = max(0, node.memory_available - per_node_memory)

                allocation = ResourceAllocation(
                    task_id=task.id, node_id=node_id,
                    quota_id=quota.id if quota else None,
                    gpu_allocated=total_gpu, cpu_allocated=total_cpu,
                    memory_allocated=total_memory, is_active=True,
                    allocated_at=datetime.utcnow()
                )
                db.session.add(allocation)

                if summary:
                    summary.available_gpus = max(0, summary.available_gpus - total_gpu)
                    summary.available_cpus = max(0, summary.available_cpus - total_cpu)
                    summary.available_memory = max(0, summary.available_memory - total_memory)

                self._update_quota_usage(quota, total_gpu, total_cpu, total_memory, delta=1)
                db.session.commit()

                logger.info(f"TE: Resources allocated for task {task.id}: "
                           f"GPU={total_gpu}, CPU={total_cpu}, Mem={total_memory}MB "
                           f"(nodes={num_nodes}, per_node: gpu={per_node_gpu} cpu={per_node_cpu}, "
                           f"quota={quota.name if quota else 'none'})")
                return True, "Resources allocated successfully"

            except Exception as e:
                db.session.rollback()
                logger.error(f"TE: Failed to allocate resources: {e}")
                return False, str(e)

    def release_resources(self, task_id: str) -> bool:
        with self._lock:
            try:
                allocations = ResourceAllocation.query.filter_by(
                    task_id=task_id, is_active=True
                ).all()

                if not allocations:
                    return True

                summary = ClusterResource.query.first()

                for alloc in allocations:
                    alloc.is_active = False
                    alloc.released_at = datetime.utcnow()

                    if alloc.node_id:
                        node = ResourceNode.query.get(alloc.node_id)
                        if node:
                            node.gpu_available = min(node.gpu_total, node.gpu_available + alloc.gpu_allocated)
                            node.cpu_available = min(node.cpu_total, node.cpu_available + alloc.cpu_allocated)
                            node.memory_available = min(node.memory_total, node.memory_available + alloc.memory_allocated)

                    if summary:
                        summary.available_gpus += alloc.gpu_allocated
                        summary.available_cpus += alloc.cpu_allocated
                        summary.available_memory += alloc.memory_allocated

                    self._update_quota_usage(alloc.quota, alloc.gpu_allocated, alloc.cpu_allocated, alloc.memory_allocated, delta=-1)

                db.session.commit()
                logger.info(f"TE: Resources released for task {task_id}")
                return True

            except Exception as e:
                db.session.rollback()
                logger.error(f"TE: Failed to release resources: {e}")
                return False

    def _select_best_node(self, gpu_req, cpu_req, mem_req) -> Optional[ResourceNode]:
        nodes = ResourceNode.query.filter(ResourceNode.status == 'online').all()
        candidates = []
        for n in nodes:
            if n.gpu_available >= gpu_req and n.cpu_available >= cpu_req and n.memory_available >= mem_req:
                load = (n.cpu_utilization or 0) * 0.4 + (n.memory_utilization or 0) * 0.3 + (n.gpu_utilization or 0) * 0.3
                candidates.append((n, load))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    def select_best_agent(self, gpu_req=0, cpu_req=0, mem_req=0) -> Optional[PoolNode]:
        """从在线的 standalone agent 中选择最佳节点"""
        nodes = PoolNode.query.filter(
            PoolNode.node_type == 'standalone',
            PoolNode.status.in_(['idle', 'busy'])
        ).all()
        candidates = []
        for n in nodes:
            if n.can_accept_task(cpu_req, mem_req, gpu_req):
                load = (n.cpu_utilization or 0) * 0.4 + (n.memory_utilization or 0) * 0.3 + (n.gpu_utilization or 0) * 0.3
                candidates.append((n, load))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    def _get_task_quota(self, task: Task) -> Optional[ResourceQuota]:
        if not task.created_by:
            return None
        try:
            from app.models.user import User
            user = User.query.get(task.created_by)
            if user and user.quota and user.quota.is_enabled:
                return user.quota
        except Exception as e:
            logger.warning(f"TE: Failed to resolve quota for task {task.id}: {e}")
        return None

    def _check_quota(self, quota: Optional[ResourceQuota], gpu_req, cpu_req, mem_req) -> Tuple[bool, str]:
        if not quota:
            return True, "No user quota assigned"
        ok, msg = quota.check_quota(gpu_req, cpu_req, mem_req)
        if not ok:
            return False, f"{quota.name}: {msg}"
        return True, "OK"

    def _update_quota_usage(self, quota: Optional[ResourceQuota], gpu, cpu, memory, delta=1):
        if not quota:
            return
        if delta > 0:
            quota.used_gpus += gpu
            quota.used_cpus += cpu
            quota.used_memory += memory
            quota.used_tasks += 1
        else:
            quota.used_gpus = max(0, quota.used_gpus - gpu)
            quota.used_cpus = max(0, quota.used_cpus - cpu)
            quota.used_memory = max(0, quota.used_memory - memory)
            quota.used_tasks = max(0, quota.used_tasks - 1)

    def get_resource_summary(self) -> dict:
        summary = ClusterResource.query.first()
        if summary:
            return summary.to_dict()
        return {
            'total_nodes': 0, 'online_nodes': 0,
            'total_gpus': 0, 'available_gpus': 0,
            'total_cpus': 0, 'available_cpus': 0,
            'total_memory': 0, 'available_memory': 0,
            'avg_cpu_utilization': 0, 'avg_memory_utilization': 0, 'avg_gpu_utilization': 0,
        }

    def get_resource_statistics(self) -> dict:
        tasks_running = Task.query.filter(Task.status.in_(['running', 'starting'])).count()
        tasks_queued = Task.query.filter(Task.status == 'queued').count()
        active_allocs = ResourceAllocation.query.filter_by(is_active=True).count()
        summary = self.get_resource_summary()
        return {
            'cluster': summary,
            'tasks': {'running': tasks_running, 'queued': tasks_queued},
            'allocations': {'active': active_allocs},
            'cluster_overview': self.get_cluster_overview(),
        }

    @staticmethod
    def _parse_cpu(value) -> int:
        if not value:
            return 0
        s = str(value).strip()
        try:
            if s.endswith('m'):
                return max(1, math.ceil(float(s[:-1]) / 1000))
            return max(0, int(float(s)))
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _parse_memory(value) -> int:
        if not value:
            return 0
        s = str(value).strip()
        units = {'Ki': 1/1024, 'Mi': 1, 'Gi': 1024, 'Ti': 1048576,
                 'K': 1/1000, 'M': 1, 'G': 1000, 'T': 1000000}
        for unit, mult in units.items():
            if s.endswith(unit):
                try:
                    return max(0, int(float(s[:-len(unit)]) * mult))
                except (ValueError, TypeError):
                    return 0
        try:
            return max(0, int(float(s) / (1024*1024)))
        except (ValueError, TypeError):
            return 0


# 全局实例
resource_manager = TEResourceManager()
