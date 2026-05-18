"""
任务调度器 - 从KubeTrain迁入并适配FT-taitp
基于 Redis 的优先级任务队列，配置项统一使用 TE_ 前缀
"""
import json
import logging
import threading
import time
from datetime import datetime
from typing import List, Optional, Tuple

import redis
from flask import current_app

from app import db
from app.models.task import Task, TaskStatus

logger = logging.getLogger(__name__)


class TaskScheduler:
    """任务调度器"""

    QUEUE_KEY = 'ft_taitp:te_task_queue'
    RUNNING_KEY = 'ft_taitp:te_running_tasks'

    def __init__(self):
        self._redis_client = None
        self._running = False
        self._scheduler_thread = None
        self._lock = threading.Lock()
        self._requeue_counts = {}
        self._requeue_backoff = {}

    def _get_redis(self) -> redis.Redis:
        if self._redis_client is None:
            self._redis_client = redis.from_url(
                current_app.config.get('REDIS_URL', 'redis://localhost:6379/0'),
                decode_responses=True
            )
        return self._redis_client

    def start(self, app):
        if self._running:
            return
        self._running = True
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop, args=(app,), daemon=True
        )
        self._scheduler_thread.start()
        logger.info("TE Task scheduler started")

    def stop(self):
        self._running = False
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        logger.info("TE Task scheduler stopped")

    def _scheduler_loop(self, app):
        with app.app_context():
            while self._running:
                try:
                    interval = current_app.config.get('SCHEDULER_INTERVAL', 5)
                    self._process_queue()
                except Exception as e:
                    logger.error(f"TE Scheduler error: {e}")
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                time.sleep(interval)

    def _process_queue(self):
        try:
            db.session.remove()
        except Exception:
            pass

        max_concurrent = current_app.config.get('MAX_CONCURRENT_TASKS', 5)
        self._cleanup_stale_running()
        running_count = self._get_running_count()

        try:
            r = self._get_redis()
            queue_len = r.zcard(self.QUEUE_KEY)
        except Exception:
            queue_len = -1

        if running_count >= max_concurrent:
            if queue_len > 0:
                logger.info(f"TE Scheduler: {queue_len} queued, {running_count}/{max_concurrent} running (full)")
            return

        if queue_len > 0:
            logger.info(f"TE Scheduler: {queue_len} queued, {running_count}/{max_concurrent} running, processing...")

        available_slots = max_concurrent - running_count
        max_attempts = available_slots + 3
        started_count = 0

        for _ in range(max_attempts):
            if started_count >= available_slots:
                break
            task_id = self._dequeue_task()
            if not task_id:
                break

            backoff_until = self._requeue_backoff.get(task_id, 0)
            if time.time() < backoff_until:
                try:
                    r = self._get_redis()
                    score = -5 * 1000000 + time.time()
                    r.zadd(self.QUEUE_KEY, {task_id: score})
                except Exception:
                    pass
                continue

            started = self._start_task(task_id)
            if started:
                started_count += 1
            else:
                break

    def _requeue_task(self, task: Task):
        count = self._requeue_counts.get(task.id, 0) + 1
        self._requeue_counts[task.id] = count

        max_requeue = 20
        if count > max_requeue:
            logger.error(f"TE Task {task.id} exceeded max requeue attempts ({max_requeue}), auto-cancelling")
            self._requeue_counts.pop(task.id, None)
            self._requeue_backoff.pop(task.id, None)

            from app.services.resource_manager import resource_manager
            resource_manager.release_resources(task.id)

            task.status = 'cancelled'
            task.error_message = f"调度超时：连续 {max_requeue} 次无法分配资源，已自动取消。"
            task.completed_at = datetime.utcnow()
            db.session.commit()
            logger.info(f"TE Task {task.id} cancelled due to scheduling timeout")

            self._notify_taitp_status(task, 'cancelled')
            return

        backoff_seconds = min(10 * (2 ** (count - 1)), 60)
        next_eligible = time.time() + backoff_seconds
        self._requeue_backoff[task.id] = next_eligible

        try:
            r = self._get_redis()
            score = -task.priority * 1000000 + time.time()
            r.zadd(self.QUEUE_KEY, {task.id: score})
            if count <= 1 or count % 5 == 0:
                logger.warning(f"TE Task {task.id} requeued ({count}/{max_requeue}), next retry in {backoff_seconds}s")
        except Exception as e:
            logger.error(f"Failed to requeue TE task {task.id}: {e}")

    def submit_task(self, task: Task) -> tuple:
        """提交任务到调度队列，供API端点调用"""
        if task.status not in ('pending', 'failed'):
            return False, f'任务当前状态为 {task.status}，无法提交'
        success = self.enqueue_task(task)
        if success:
            return True, '任务已提交到调度队列'
        return False, '任务提交失败，请检查调度服务状态'

    # ==================== Pipeline Methods ====================

    def submit_pipeline(self, parent: Task) -> tuple:
        """Submit a pipeline task: set parent to running, start the first child stage."""
        if parent.status not in ('pending', 'failed'):
            return False, f'流水线当前状态为 {parent.status}，无法提交'

        progress = parent.pipeline_progress or {}
        stages = progress.get('stages', [])
        if not stages:
            return False, '流水线配置无效：无阶段信息'

        # Mark parent as running
        parent.status = 'running'
        parent.started_at = datetime.utcnow()
        progress['current_stage'] = 0
        parent.pipeline_progress = progress
        db.session.commit()

        # Submit first stage child task
        first_task_id = stages[0].get('task_id')
        if not first_task_id:
            return False, '流水线第一阶段任务ID缺失'
        first_child = Task.query.get(first_task_id)
        if not first_child:
            return False, '流水线第一阶段任务不存在'

        success = self.enqueue_task(first_child)
        if success:
            # Update stage status
            stages[0]['status'] = 'queued'
            parent.pipeline_progress = progress
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(parent, 'pipeline_progress')
            db.session.commit()

            from app.websocket.handlers import broadcast_status
            broadcast_status(parent.id, parent.status, f'流水线已启动，正在执行阶段 1/{len(stages)}')
            return True, f'流水线已提交，共 {len(stages)} 个阶段'
        return False, '流水线第一阶段提交失败'

    def _advance_pipeline(self, child_task: Task):
        """Called when a pipeline stage child task completes or fails.
        Updates parent pipeline_progress, passes model to next stage, starts next stage.
        """
        from app.websocket.handlers import broadcast_status, broadcast_progress
        from sqlalchemy.orm.attributes import flag_modified

        parent = Task.query.get(child_task.parent_task_id)
        if not parent or not parent.pipeline_progress:
            return

        progress = dict(parent.pipeline_progress)
        stages = progress.get('stages', [])
        stage_idx = child_task.stage_index
        if stage_idx is None or stage_idx >= len(stages):
            return

        # Update this stage's status and model_path
        stages[stage_idx]['status'] = child_task.status
        if child_task.model_path:
            stages[stage_idx]['model_path'] = child_task.model_path
        if child_task.output_path:
            stages[stage_idx]['output_path'] = child_task.output_path

        if child_task.status == 'failed':
            # Stage failed → mark parent as failed
            parent.status = 'failed'
            parent.error_message = f"阶段 {stage_idx + 1} 失败: {child_task.error_message or '未知错误'}"
            parent.completed_at = datetime.utcnow()
            if parent.started_at:
                parent.duration = int((parent.completed_at - parent.started_at).total_seconds())
            progress['current_stage'] = stage_idx
            parent.pipeline_progress = progress
            flag_modified(parent, 'pipeline_progress')
            db.session.commit()
            broadcast_status(parent.id, 'failed', parent.error_message)
            return

        if child_task.status == 'completed':
            # Calculate aggregate progress for parent
            completed_epochs = 0
            for i, st in enumerate(stages):
                st_task = Task.query.get(st.get('task_id')) if st.get('task_id') else None
                if st_task and st_task.status == 'completed':
                    completed_epochs += (st_task.total_epochs or st_task.current_epoch or 0)
                elif st_task and st_task.status == 'running':
                    completed_epochs += (st_task.current_epoch or 0)

            if parent.total_epochs and parent.total_epochs > 0:
                parent.progress_percent = min((completed_epochs / parent.total_epochs) * 100, 99.9)
                parent.current_epoch = completed_epochs

            next_idx = stage_idx + 1
            if next_idx < len(stages):
                # Start next stage
                next_task_id = stages[next_idx].get('task_id')
                next_child = Task.query.get(next_task_id) if next_task_id else None
                if not next_child:
                    parent.status = 'failed'
                    parent.error_message = f'阶段 {next_idx + 1} 任务不存在'
                    parent.completed_at = datetime.utcnow()
                    progress['current_stage'] = stage_idx
                    parent.pipeline_progress = progress
                    flag_modified(parent, 'pipeline_progress')
                    db.session.commit()
                    broadcast_status(parent.id, 'failed', parent.error_message)
                    return

                # Pass model from completed stage to next stage
                model_path = child_task.model_path or child_task.output_path
                if model_path and not next_child.base_model_path:
                    next_child.base_model_path = model_path
                    logger.info(f"Pipeline: passing model from stage {stage_idx} to stage {next_idx}: {model_path}")

                progress['current_stage'] = next_idx
                stages[next_idx]['status'] = 'queued'
                parent.pipeline_progress = progress
                flag_modified(parent, 'pipeline_progress')
                db.session.commit()

                # Enqueue next stage
                self.enqueue_task(next_child)
                broadcast_status(parent.id, 'running',
                                 f'阶段 {stage_idx + 1} 完成，正在执行阶段 {next_idx + 1}/{len(stages)}')
                broadcast_progress(parent.id, parent.progress_percent or 0,
                                   parent.current_epoch or 0, parent.total_epochs)
            else:
                # All stages completed
                parent.status = 'completed'
                parent.progress_percent = 100.0
                parent.completed_at = datetime.utcnow()
                if parent.started_at:
                    parent.duration = int((parent.completed_at - parent.started_at).total_seconds())

                # Use model from last stage as final model
                last_model = None
                for st in reversed(stages):
                    if st.get('model_path'):
                        last_model = st['model_path']
                        break
                if last_model:
                    parent.model_path = last_model

                # Use final metrics from last stage
                if child_task.final_loss is not None:
                    parent.final_loss = child_task.final_loss
                if child_task.final_accuracy is not None:
                    parent.final_accuracy = child_task.final_accuracy
                # Use output_path from last stage
                if child_task.output_path:
                    parent.output_path = child_task.output_path

                progress['current_stage'] = stage_idx
                parent.pipeline_progress = progress
                flag_modified(parent, 'pipeline_progress')
                parent.current_epoch = parent.total_epochs or completed_epochs
                db.session.commit()
                broadcast_status(parent.id, 'completed', '流水线全部阶段完成')
                broadcast_progress(parent.id, 100.0, parent.current_epoch or 0, parent.total_epochs)

    def _update_pipeline_progress(self, child_task: Task):
        """Update parent pipeline task progress when a running child stage reports progress."""
        from app.websocket.handlers import broadcast_progress
        from sqlalchemy.orm.attributes import flag_modified

        parent = Task.query.get(child_task.parent_task_id)
        if not parent or not parent.pipeline_progress:
            return

        progress = dict(parent.pipeline_progress)
        stages = progress.get('stages', [])
        stage_idx = child_task.stage_index
        if stage_idx is not None and stage_idx < len(stages):
            stages[stage_idx]['status'] = 'running'

        # Calculate aggregate epochs across all stages
        completed_epochs = 0
        for st in stages:
            st_task = Task.query.get(st.get('task_id')) if st.get('task_id') else None
            if st_task:
                if st_task.status == 'completed':
                    completed_epochs += (st_task.total_epochs or st_task.current_epoch or 0)
                elif st_task.status == 'running':
                    completed_epochs += (st_task.current_epoch or 0)

        if parent.total_epochs and parent.total_epochs > 0:
            parent.progress_percent = min((completed_epochs / parent.total_epochs) * 100, 99.9)
            parent.current_epoch = completed_epochs
            parent.pipeline_progress = progress
            flag_modified(parent, 'pipeline_progress')
            db.session.commit()
            broadcast_progress(parent.id, parent.progress_percent, parent.current_epoch, parent.total_epochs)

    def enqueue_task(self, task: Task) -> bool:
        try:
            r = self._get_redis()
            score = -task.priority * 1000000 + time.time()
            r.zadd(self.QUEUE_KEY, {task.id: score})

            task.status = 'queued'
            task.queued_at = datetime.utcnow()
            db.session.commit()

            logger.info(f"TE Task {task.id} enqueued with priority {task.priority}")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue TE task: {e}")
            return False

    def _dequeue_task(self) -> Optional[str]:
        try:
            r = self._get_redis()
            result = r.zpopmin(self.QUEUE_KEY, 1)
            if result:
                task_id, _ = result[0]
                return task_id
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue TE task: {e}")
            return None

    def _resolve_execution_mode(self, task):
        """解析任务的实际执行模式，并设置 assigned_worker_id

        前端已严格分离 K8s/Agent 资源选择，此处遵循前端指定的 execution_mode：
        - k8s: 始终走 K8s Job，不 fallback 到 agent（尤其 DDP 模式必须 K8s）
        - agent: 始终走 Agent Docker，不 fallback 到 K8s
        - auto: 优先 K8s，回退 agent（兼容旧版调用）

        Returns:
            str: 'k8s' or 'agent'
        """
        from app.services.resource_manager import resource_manager
        mode = getattr(task, 'execution_mode', 'auto') or 'auto'

        if mode == 'k8s':
            return 'k8s'
        elif mode == 'agent':
            agent = resource_manager.select_best_agent(
                gpu_req=task.gpu_limit or 0,
                cpu_req=resource_manager._parse_cpu(task.cpu_request),
                mem_req=resource_manager._parse_memory(task.memory_request)
            )
            if agent:
                task.assigned_worker_id = agent.id
                return 'agent'
            logger.warning(f"TE Task {task.id}: no agent available, mode=agent but no candidate")
            return 'agent'
        else:
            # auto 模式：多节点DDP/FSDP 必须 K8s，单机DDP可走agent
            parallel = getattr(task, 'parallel_mode', 'single') or 'single'
            num_nodes = getattr(task, 'num_nodes', 1) or 1
            if parallel in ('ddp', 'fsdp') and num_nodes > 1:
                logger.info(f"TE Task {task.id}: auto mode + {parallel} + {num_nodes} nodes → forced k8s")
                return 'k8s'

            has_k8s = resource_manager.has_online_k8s_nodes()
            has_agent = resource_manager.has_online_agents()

            if has_k8s:
                return 'k8s'
            elif has_agent:
                agent = resource_manager.select_best_agent(
                    gpu_req=task.gpu_limit or 0,
                    cpu_req=resource_manager._parse_cpu(task.cpu_request),
                    mem_req=resource_manager._parse_memory(task.memory_request)
                )
                if agent:
                    task.assigned_worker_id = agent.id
                    return 'agent'
            return 'k8s'

    def _start_task(self, task_id: str) -> bool:
        raw_task_id = task_id
        if isinstance(task_id, bytes):
            try:
                task_id = task_id.decode()
            except Exception:
                task_id = str(task_id)
        task_id = str(task_id).strip()
        if (task_id.startswith("b'") and task_id.endswith("'")) or (task_id.startswith('b"') and task_id.endswith('"')):
            task_id = task_id[2:-1]

        task = Task.query.get(task_id)
        if not task:
            logger.warning(f"TE Task not found. raw={raw_task_id!r}, normalized={task_id!r}")
            return True

        if task.status not in ['queued', 'retrying']:
            logger.warning(f"TE Task {task_id} is not in queueable state: {task.status}")
            return True

        try:
            from app.services.resource_manager import resource_manager
            alloc_ok, alloc_msg = resource_manager.allocate_resources(task)
            if not alloc_ok:
                logger.warning(f"TE Resource allocation failed for task {task_id}: {alloc_msg}")
                self._requeue_task(task)
                return False

            self._add_to_running(task_id)

            # 双通道调度：根据 execution_mode 分发
            resolved_mode = self._resolve_execution_mode(task)
            logger.info(f"TE Task {task_id}: resolved execution_mode={resolved_mode}")

            if resolved_mode == 'agent':
                if task.assigned_worker_id:
                    success, result = self._dispatch_to_agent(task)
                else:
                    # 明确要求Agent执行但无可用Agent → 重新排队等待
                    logger.warning(f"TE Task {task_id}: execution_mode=agent but no agent available, requeue")
                    self._remove_from_running(task_id)
                    resource_manager.release_resources(task_id)
                    self._requeue_task(task)
                    return False
            else:
                from app.services.k8s_job_executor import k8s_job_executor
                # 无K8s节点 + 单机无GPU → 直接走本地进程，避免K8s API超时
                is_single_no_gpu = (
                    (getattr(task, 'parallel_mode', 'single') or 'single') == 'single'
                    and (task.gpu_limit or 0) == 0
                )
                if is_single_no_gpu and not resource_manager.has_online_k8s_nodes():
                    logger.info(f"TE Task {task_id}: no K8s nodes, direct local process fallback")
                    k8s_job_executor._load_config()
                    success, result = k8s_job_executor._run_local_process(task)
                else:
                    success, result = k8s_job_executor.create_training_job(task)

            if success:
                self._requeue_counts.pop(task_id, None)
                self._requeue_backoff.pop(task_id, None)
                logger.info(f"TE Task {task_id} started successfully via {resolved_mode}")
            else:
                self._remove_from_running(task_id)
                resource_manager.release_resources(task_id)
                result_str = str(result)
                logger.warning(f"TE Task {task_id} dispatch failed ({resolved_mode}): {result_str}")
                self._handle_task_failure(task, result_str)

            return True

        except Exception as e:
            logger.error(f"Failed to start TE task {task_id}: {e}")
            self._remove_from_running(task_id)
            from app.services.resource_manager import resource_manager
            resource_manager.release_resources(task_id)
            self._handle_task_failure(task, str(e))
            return True

    def _dispatch_to_agent(self, task) -> Tuple[bool, str]:
        """将任务分发给 standalone agent 执行"""
        try:
            from app.services.worker_registry import worker_registry
            worker = worker_registry.get_worker(task.assigned_worker_id)
            if not worker:
                return False, f"Agent {task.assigned_worker_id} not found or offline"

            import requests as http_requests
            import os, tempfile as _tf

            # 读取脚本内容，Agent可能无法访问NFS路径
            script_content = None
            if task.training_script:
                # 尝试多个路径候选：绝对路径 → 本地te_scripts → SFTP
                candidates = [task.training_script]
                if not os.path.isabs(task.training_script):
                    local_base = current_app.config.get('LOCAL_SCRIPT_DIR', '') or os.path.join(_tf.gettempdir(), 'te_scripts')
                    candidates.append(os.path.join(local_base, task.training_script.replace('\\', '/').strip('/')))
                for cand in candidates:
                    try:
                        with open(cand, 'r', encoding='utf-8') as f:
                            script_content = f.read()
                        logger.info(f"Read script for agent dispatch: {cand}")
                        break
                    except Exception:
                        pass
                if script_content is None:
                    logger.warning(f"Cannot read script locally for agent dispatch, tried: {candidates}")
                    try:
                        script_content = self._read_script_via_sftp(task.training_script)
                    except Exception:
                        logger.error(f"SFTP read also failed for {task.training_script}")

            # FIX-5: dispatch 前确保 output_path 已设置
            if not task.output_path:
                nfs_base = current_app.config.get('NFS_MOUNT_PATH', '/data')
                if os.name == 'nt' or not os.path.isdir(nfs_base):
                    task.output_path = os.path.join(_tf.gettempdir(), 'kubetrain2_local', 'outputs', task.id)
                else:
                    task.output_path = os.path.join(nfs_base, 'outputs', task.id)

            agent_url = f"http://{worker['ip_address']}:{worker.get('port', 8005)}/api/agent/execute"
            # 训练镜像：优先从 task.environment 获取，其次从全局配置
            training_image = ''
            if task.environment and isinstance(task.environment, dict):
                training_image = task.environment.get('training_image', '')
            if not training_image:
                training_image = current_app.config.get('TRAINING_IMAGE', '')

            payload = {
                'task_id': task.id,
                'training_script': task.training_script,
                'script_content': script_content,
                'training_args': task.training_args,
                'environment': task.environment,
                'dataset_path': task.dataset_path,
                'output_path': task.output_path,
                'checkpoint_path': task.checkpoint_path,
                'pip_packages': task.pip_packages,
                'gpu_limit': task.gpu_limit,
                'cpu_request': task.cpu_request,
                'memory_request': task.memory_request,
                'training_image': training_image,
                'parallel_mode': task.parallel_mode or 'single',
                'nproc_per_node': task.nproc_per_node or 1,
            }
            resp = http_requests.post(agent_url, json=payload, timeout=10)
            if resp.status_code == 200:
                task.status = 'assigned'
                task.started_at = datetime.utcnow()
                task.job_name = f"agent-{task.assigned_worker_id[:8]}-{task.id[:8]}"
                db.session.commit()
                logger.info(f"TE Task {task.id} dispatched to agent {task.assigned_worker_id}")
                return True, task.job_name
            else:
                return False, f"Agent returned {resp.status_code}: {resp.text[:200]}"

        except Exception as e:
            raw = str(e)
            # 生成用户友好的错误描述
            if 'Max retries' in raw or 'Connection' in raw or 'WinError' in raw:
                friendly = f"Agent节点不可达 ({worker.get('ip_address')}:{worker.get('port', 8005)})，请检查Agent服务是否启动"
            elif 'Timeout' in raw or 'timeout' in raw:
                friendly = f"Agent节点响应超时 ({worker.get('ip_address')}:{worker.get('port', 8005)})"
            else:
                friendly = f"Agent调度失败: {raw[:200]}"
            return False, friendly

    def _handle_task_failure(self, task: Task, error_message: str):
        task.retry_count += 1
        from app.services.resource_manager import resource_manager
        resource_manager.release_resources(task.id)

        if task.retry_count < task.max_retries:
            task.status = 'retrying'
            task.error_message = f"第{task.retry_count}次尝试失败: {error_message}"
            db.session.commit()
            self.enqueue_task(task)
            logger.info(f"TE Task {task.id} will retry (attempt {task.retry_count + 1}/{task.max_retries})")
        else:
            task.status = 'failed'
            task.error_message = f"已达最大重试次数({task.max_retries})。最后错误: {error_message}"
            task.completed_at = datetime.utcnow()
            db.session.commit()
            logger.error(f"TE Task {task.id} failed after {task.max_retries} attempts")

            self._notify_taitp_status(task, 'failed')

    def cancel_task(self, task_id: str) -> Tuple[bool, str]:
        task = Task.query.get(task_id)
        if not task:
            return False, "Task not found"
        try:
            r = self._get_redis()
            r.zrem(self.QUEUE_KEY, task_id)
            self._remove_from_running(task_id)

            from app.services.resource_manager import resource_manager
            resource_manager.release_resources(task_id)

            from app.services.k8s_job_executor import k8s_job_executor
            if task.job_name:
                k8s_job_executor.delete_job(task)

            task.status = 'cancelled'
            task.completed_at = datetime.utcnow()
            if task.started_at:
                task.duration = int((task.completed_at - task.started_at).total_seconds())
            db.session.commit()
            from app.websocket.handlers import broadcast_status
            broadcast_status(task_id, 'cancelled')
            logger.info(f"TE Task {task_id} cancelled")
            return True, "Task cancelled"
        except Exception as e:
            logger.error(f"Failed to cancel TE task: {e}")
            return False, str(e)

    def complete_task(self, task_id: str, success: bool = True,
                      final_metrics: dict = None) -> Tuple[bool, str]:
        task = Task.query.get(task_id)
        if not task:
            return False, "Task not found"
        try:
            self._remove_from_running(task_id)
            task.status = 'completed' if success else 'failed'
            task.completed_at = datetime.utcnow()
            if task.started_at:
                task.duration = int((task.completed_at - task.started_at).total_seconds())
            if final_metrics:
                task.final_loss = final_metrics.get('loss')
                task.final_accuracy = final_metrics.get('accuracy')
                task.best_metric = final_metrics
            db.session.commit()
            logger.info(f"TE Task {task_id} completed with status: {task.status}")
            return True, f"Task {task.status}"
        except Exception as e:
            logger.error(f"Failed to complete TE task: {e}")
            return False, str(e)

    def retry_task(self, task: Task) -> Tuple[bool, str]:
        """手动重试失败/已取消的任务"""
        if task.status not in ('failed', 'cancelled'):
            return False, f'任务当前状态为 {task.status}，无法重试'
        try:
            task.retry_count = 0
            task.error_message = None
            task.completed_at = None
            task.job_name = None
            task.pod_names = None
            success = self.enqueue_task(task)
            if success:
                logger.info(f"TE Task {task.id} manually retried")
                return True, '任务已重新提交到调度队列'
            return False, '任务重新提交失败'
        except Exception as e:
            logger.error(f"Failed to retry TE task {task.id}: {e}")
            return False, str(e)

    def handle_agent_callback(self, task: Task, status: str,
                              message: str = '', metrics: dict = None,
                              logs: list = None, *,
                              current_epoch: int = None,
                              total_epochs: int = None,
                              progress_percent: float = None,
                              output_path: str = None,
                              model_path: str = None):
        """处理 Agent 训练进度回调"""
        from app.websocket.handlers import broadcast_log, broadcast_metric, broadcast_status, broadcast_progress
        from app.models.log import TaskLog, LogLevel
        from app.models.metric import TaskMetric

        # ---- 日志存储 ----
        if logs:
            _LEVEL_MAP = {'debug': LogLevel.DEBUG, 'info': LogLevel.INFO,
                          'warning': LogLevel.WARNING, 'error': LogLevel.ERROR}
            for log_entry in logs:
                if isinstance(log_entry, dict):
                    content = log_entry.get('message', '') or str(log_entry)
                    level_str = (log_entry.get('level') or 'info').lower()
                    source = log_entry.get('source', 'agent')
                else:
                    content = str(log_entry)
                    level_str = 'info'
                    source = 'agent'
                try:
                    log = TaskLog(
                        task_id=task.id, level=_LEVEL_MAP.get(level_str, LogLevel.INFO),
                        source=source, message=content,
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(log)
                    broadcast_log(task.id, {
                        'task_id': task.id, 'level': level_str.upper(),
                        'message': content, 'source': source,
                        'timestamp': datetime.utcnow().isoformat()
                    })
                except Exception as e:
                    logger.error(f"TE: Failed to store agent log: {e}")

        # ---- 顶层 epoch 字段（Agent _callback_progress 发送）----
        if current_epoch is not None:
            try:
                task.current_epoch = int(current_epoch)
            except (ValueError, TypeError):
                pass
        if total_epochs is not None:
            try:
                task.total_epochs = int(total_epochs)
            except (ValueError, TypeError):
                pass

        # ---- 指标存储 ----
        if metrics or current_epoch is not None:
            try:
                metric = TaskMetric(task_id=task.id, timestamp=datetime.utcnow())
                # 兼容 metrics dict 内的 epoch（K8s log_collector 路径）
                if metrics and 'epoch' in metrics:
                    metric.epoch = int(metrics['epoch'])
                    task.current_epoch = metric.epoch
                elif current_epoch is not None:
                    metric.epoch = task.current_epoch
                if metrics and 'total_epochs' in metrics:
                    task.total_epochs = int(metrics['total_epochs'])
                # 计算进度百分比
                if progress_percent is not None:
                    task.progress_percent = float(progress_percent)
                elif task.total_epochs and task.current_epoch:
                    task.progress_percent = (task.current_epoch / task.total_epochs) * 100
                if metrics and 'loss' in metrics:
                    metric.loss = float(metrics['loss'])
                    task.final_loss = metric.loss
                if metrics and 'accuracy' in metrics:
                    metric.accuracy = float(metrics['accuracy'])
                    task.final_accuracy = metric.accuracy
                if metrics and 'learning_rate' in metrics:
                    metric.learning_rate = float(metrics['learning_rate'])
                db.session.add(metric)
                # Defer broadcasts until after commit (see below)
                _pending_metric = {
                    'task_id': task.id, 'epoch': metric.epoch,
                    'loss': metric.loss, 'accuracy': metric.accuracy,
                    'timestamp': datetime.utcnow().isoformat()
                }
            except Exception as e:
                logger.error(f"TE: Failed to store agent metric: {e}")
                _pending_metric = None
        else:
            _pending_metric = None

        old_status = task.status
        if status == 'running' and task.status != 'running':
            task.status = 'running'
            if not task.started_at:
                task.started_at = datetime.utcnow()
        elif status == 'completed':
            task.status = 'completed'
            task.completed_at = datetime.utcnow()
            task.progress_percent = 100.0
            if task.started_at:
                task.duration = int((task.completed_at - task.started_at).total_seconds())
            # FIX-4: 从回调顶层参数提取 output_path / model_path（兼容 metrics 内的旧路径）
            cb_output = output_path or (metrics.get('output_path') if metrics else None)
            cb_model = model_path or (metrics.get('model_path') if metrics else None)
            if cb_output and not task.output_path:
                task.output_path = cb_output
            if cb_model and not task.model_path:
                task.model_path = cb_model
            logger.info(f"TE Agent completed: task={task.id} output_path={task.output_path} model_path={task.model_path}")
            from app.services.resource_manager import resource_manager
            resource_manager.release_resources(task.id)
            self._remove_from_running(task.id)
            self._notify_taitp_status(task, 'completed')
        elif status == 'failed':
            task.status = 'failed'
            task.error_message = message
            task.completed_at = datetime.utcnow()
            if task.started_at:
                task.duration = int((task.completed_at - task.started_at).total_seconds())
            from app.services.resource_manager import resource_manager
            resource_manager.release_resources(task.id)
            self._remove_from_running(task.id)

        # Snapshot broadcast data before commit
        _bcast_progress_pct = task.progress_percent or 0
        _bcast_cur_epoch = task.current_epoch or 0
        _bcast_total = task.total_epochs
        _bcast_status = task.status
        _status_changed = (task.status != old_status)

        db.session.commit()

        # Broadcast AFTER commit so polling reads consistent DB data
        if _pending_metric is not None:
            broadcast_metric(task.id, _pending_metric)
            broadcast_progress(task.id, _bcast_progress_pct, _bcast_cur_epoch, _bcast_total)
        if _status_changed or status in ('completed', 'failed'):
            broadcast_status(task.id, _bcast_status, message)
        logger.info(f"TE Agent callback: task={task.id} status={status}")

        # ---- Pipeline stage advancement ----
        if task.parent_task_id:
            if status in ('completed', 'failed'):
                try:
                    self._advance_pipeline(task)
                except Exception as e:
                    logger.error(f"Pipeline advance failed for stage task {task.id}: {e}")
            elif status == 'running' and current_epoch is not None:
                # Update parent pipeline progress in real-time
                try:
                    self._update_pipeline_progress(task)
                except Exception as e:
                    logger.debug(f"Pipeline progress update failed: {e}")

    def _cleanup_stale_running(self):
        try:
            r = self._get_redis()
            running_ids = r.smembers(self.RUNNING_KEY)
            for task_id in running_ids:
                task = Task.query.get(task_id)
                if not task or task.status in ('completed', 'failed', 'cancelled', 'paused', 'pending', 'queued'):
                    r.srem(self.RUNNING_KEY, task_id)
                    logger.info(f"Cleaned stale TE running task: {task_id[:12]}")
        except Exception as e:
            logger.error(f"Failed to cleanup stale TE running tasks: {e}")

    def _add_to_running(self, task_id: str):
        try:
            r = self._get_redis()
            r.sadd(self.RUNNING_KEY, task_id)
        except Exception as e:
            logger.error(f"Failed to add to TE running set: {e}")

    def _remove_from_running(self, task_id: str):
        try:
            r = self._get_redis()
            r.srem(self.RUNNING_KEY, task_id)
        except Exception as e:
            logger.error(f"Failed to remove from TE running set: {e}")

    def _get_running_count(self) -> int:
        try:
            r = self._get_redis()
            return r.scard(self.RUNNING_KEY)
        except Exception as e:
            logger.error(f"Failed to get TE running count: {e}")
            return 0

    def get_queue_info(self) -> dict:
        try:
            r = self._get_redis()
            queued = r.zcard(self.QUEUE_KEY)
            running = r.scard(self.RUNNING_KEY)
            queued_ids = r.zrange(self.QUEUE_KEY, 0, -1)
            running_ids = list(r.smembers(self.RUNNING_KEY))
            return {
                'queued_count': queued,
                'running_count': running,
                'queued_task_ids': queued_ids,
                'running_task_ids': running_ids,
                'max_concurrent': current_app.config.get('MAX_CONCURRENT_TASKS', 5)
            }
        except Exception as e:
            logger.error(f"Failed to get TE queue info: {e}")
            return {
                'queued_count': 0,
                'running_count': 0,
                'queued_task_ids': [],
                'running_task_ids': [],
                'error': str(e)
            }


    def _read_script_via_sftp(self, remote_path: str) -> Optional[str]:
        """通过SFTP从NFS主机读取脚本内容"""
        try:
            import paramiko
            nfs_host = current_app.config.get('NFS_HOST', '192.168.171.3')
            nfs_user = current_app.config.get('NFS_USER', 'root')
            nfs_password = current_app.config.get('NFS_PASSWORD', '')
            nfs_key_file = current_app.config.get('NFS_KEY_FILE', '')
            nfs_base = current_app.config.get('NFS_BASE_PATH', '/data/kubetrain')

            # 将容器路径 /data/xxx 转换为 NFS 实际路径
            actual_path = remote_path
            if remote_path.startswith('/data/') and not remote_path.startswith(nfs_base):
                actual_path = nfs_base + remote_path[5:]  # /data/scripts/... → /data/kubetrain/scripts/...

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            connect_kwargs = {'hostname': nfs_host, 'username': nfs_user, 'timeout': 10}
            if nfs_key_file:
                connect_kwargs['key_filename'] = nfs_key_file
            elif nfs_password:
                connect_kwargs['password'] = nfs_password
            ssh.connect(**connect_kwargs)
            sftp = ssh.open_sftp()
            with sftp.open(actual_path, 'r') as f:
                content = f.read().decode('utf-8')
            sftp.close()
            ssh.close()
            return content
        except ImportError:
            logger.warning("paramiko not installed, cannot read script via SFTP")
            return None
        except Exception as e:
            logger.warning(f"SFTP read failed for {remote_path}: {e}")
            return None

    def _notify_taitp_status(self, task: Task, status: str):
        """调度器内部状态变更时回调 taitp（复用 task_watcher 的回调逻辑）"""
        try:
            from app.services.task_watcher import task_watcher
            task_watcher._notify_taitp(task, status)
        except Exception as e:
            logger.warning(f"TE Scheduler: failed to notify taitp for task {task.id} status={status}: {e}")


# 全局实例
task_scheduler = TaskScheduler()
