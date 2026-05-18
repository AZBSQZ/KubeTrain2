"""
任务状态 Watcher - 从KubeTrain迁入并适配FT-taitp
监控 K8s Job 状态并同步到数据库，配置项统一使用 TE_ 前缀
"""
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime
from typing import Dict, Optional

from flask import current_app

from app import db
from app.models.task import Task, TaskStatus
from app.models.log import TaskLog, LogLevel
from app.services.k8s_job_executor import k8s_job_executor
from app.services.k8s_client import get_batch_api, get_core_api

logger = logging.getLogger(__name__)


class TaskWatcher:
    """任务状态监视器"""

    def __init__(self):
        self._running = False
        self._watcher_thread = None
        self._namespace = None

    def start(self, app):
        if self._running:
            return
        self._running = True
        self._watcher_thread = threading.Thread(
            target=self._watcher_loop, args=(app,), daemon=True
        )
        self._watcher_thread.start()
        logger.info("TE Task watcher started")

    def stop(self):
        self._running = False
        if self._watcher_thread:
            self._watcher_thread.join(timeout=5)
        logger.info("TE Task watcher stopped")

    def _watcher_loop(self, app):
        with app.app_context():
            self._namespace = current_app.config.get('K8S_NAMESPACE', 'kubetrain')
            # 优先使用注册集群的 namespace
            try:
                from app.services.k8s_client import get_first_connected_cluster
                cluster = get_first_connected_cluster()
                if cluster and cluster.namespace:
                    self._namespace = cluster.namespace
                    logger.info(f"TE Watcher: using cluster namespace '{self._namespace}'")
            except Exception:
                pass
            while self._running:
                try:
                    interval = current_app.config.get('WATCHER_INTERVAL', 10)
                    self._check_running_tasks()
                except Exception as e:
                    logger.error(f"TE Watcher error: {e}")
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                time.sleep(interval)

    def _check_running_tasks(self):
        try:
            db.session.remove()
        except Exception:
            pass

        running_tasks = Task.query.filter(
            Task.status.in_(['starting', 'running'])
        ).all()

        for task in running_tasks:
            try:
                self._check_task_status(task)
            except Exception as e:
                logger.error(f"TE: Error checking task {task.id}: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass

    def _check_task_status(self, task: Task):
        if not task.job_name:
            return

        if task.status in ('completed', 'failed', 'cancelled'):
            from app.services.task_scheduler import task_scheduler
            task_scheduler._remove_from_running(task.id)
            return

        # 本地进程任务：由 _run_local_process 的后台线程自行管理状态，仅做超时守护
        if task.job_name and task.job_name.startswith('local-'):
            local_timeout = current_app.config.get('LOCAL_TASK_TIMEOUT', 86400)  # 默认24h
            if task.started_at:
                elapsed = (datetime.utcnow() - task.started_at).total_seconds()
                if elapsed > local_timeout:
                    logger.warning(f"TE Task {task.id}: Local task timed out after {int(elapsed)}s")
                    task.status = 'failed'
                    task.error_message = f'Local task timed out after {int(elapsed / 3600)}h'
                    task.completed_at = datetime.utcnow()
                    from app.services.task_scheduler import task_scheduler
                    task_scheduler._remove_from_running(task.id)
                    from app.services.resource_manager import resource_manager
                    resource_manager.release_resources(task.id)
                    db.session.commit()
                    self._notify_taitp(task, 'failed')
            return  # 本地进程任务不走 K8s Job 状态检查

        # Agent 任务超时守护：Agent 崩溃后任务不会永远 stuck
        if task.execution_mode == 'agent' or (task.job_name and task.job_name.startswith('agent-')):
            agent_timeout = current_app.config.get('AGENT_TASK_TIMEOUT', 86400)  # 默认24h
            if task.started_at:
                elapsed = (datetime.utcnow() - task.started_at).total_seconds()
                if elapsed > agent_timeout:
                    logger.warning(f"TE Task {task.id}: Agent task timed out after {int(elapsed)}s (limit={agent_timeout}s)")
                    task.status = 'failed'
                    task.error_message = f'Agent task timed out after {int(elapsed / 3600)}h (no callback received)'
                    task.completed_at = datetime.utcnow()
                    from app.services.task_scheduler import task_scheduler
                    task_scheduler._remove_from_running(task.id)
                    from app.services.resource_manager import resource_manager
                    resource_manager.release_resources(task.id)
                    db.session.commit()
                    self._notify_taitp(task, 'failed')
            return  # Agent 任务不走 K8s Job 状态检查

        job_status = k8s_job_executor.get_job_status(task.job_name)

        if job_status is None:
            if task.status == 'starting':
                return
            else:
                self._handle_job_missing(task)
                return

        pod_names = k8s_job_executor.get_pod_names(task.job_name)
        if pod_names and pod_names != task.pod_names:
            task.pod_names = pod_names
            db.session.commit()

        conditions = job_status.get('conditions', [])
        is_complete = False
        is_failed = False
        fail_reason = None
        fail_message = None

        for condition in conditions:
            if condition['type'] == 'Failed' and condition['status'] == 'True':
                is_failed = True
                fail_reason = condition.get('reason')
                fail_message = condition.get('message')
            elif condition['type'] == 'Complete' and condition['status'] == 'True':
                is_complete = True

        if is_failed:
            self._handle_job_failed(task, fail_reason, fail_message)
            return

        if is_complete:
            failed_count = job_status.get('failed', 0)
            if failed_count > 0:
                logger.warning(f"TE Task {task.id}: Job Complete but {failed_count} pods failed")

            has_pod_failure = self._check_pods_exit_codes(task)
            if has_pod_failure:
                self._handle_job_failed(task, 'PodFailure',
                                       '训练进程异常退出（Job标记Complete但Pod有非零退出码）')
            else:
                self._handle_job_completed(task, job_status)
            return

        if job_status.get('active', 0) > 0:
            if task.status == 'starting':
                task.status = 'running'
                db.session.commit()
                # 推送运行状态到 taitp
                self._notify_taitp(task, 'running')

        self._check_pod_status(task)

    def _check_pods_exit_codes(self, task: Task) -> bool:
        if not task.pod_names:
            return False
        try:
            core_api = get_core_api()
            for pod_name in task.pod_names:
                try:
                    pod = core_api.read_namespaced_pod(name=pod_name, namespace=self._namespace)
                    if pod.status.container_statuses:
                        for cs in pod.status.container_statuses:
                            if cs.state.terminated and cs.state.terminated.exit_code != 0:
                                logger.warning(f"TE Task {task.id}: Pod {pod_name} exited with code {cs.state.terminated.exit_code}")
                                return True
                except Exception as e:
                    logger.debug(f"TE: Could not read pod {pod_name}: {e}")
        except Exception as e:
            logger.error(f"TE: Error checking pod exit codes: {e}")
        return False

    def _check_pod_status(self, task: Task):
        if not task.pod_names:
            return
        try:
            core_api = get_core_api()
            for pod_name in task.pod_names:
                try:
                    pod = core_api.read_namespaced_pod(name=pod_name, namespace=self._namespace)
                    if pod.status.container_statuses:
                        for cs in pod.status.container_statuses:
                            if cs.state.waiting:
                                waiting = cs.state.waiting
                                if waiting.reason in ['ImagePullBackOff', 'ErrImagePull', 'CrashLoopBackOff']:
                                    self._handle_pod_error(task, pod_name, waiting.reason, waiting.message)
                                    return
                            elif cs.state.terminated:
                                terminated = cs.state.terminated
                                if terminated.exit_code != 0:
                                    self._handle_pod_error(task, pod_name,
                                        f"Exit code {terminated.exit_code}",
                                        terminated.message or terminated.reason)
                                    return
                except Exception as e:
                    logger.debug(f"TE: Could not read pod {pod_name}: {e}")
        except Exception as e:
            logger.error(f"TE: Error checking pod status: {e}")

    def _handle_job_completed(self, task: Task, job_status: Dict):
        logger.info(f"TE Task {task.id}: Job completed, starting final processing...")
        try:
            from app.services.log_collector import log_collector
            log_collector.final_collect_task_logs(task)
        except Exception as e:
            logger.error(f"TE: Final log collection failed for task {task.id}: {e}")

        try:
            self._export_results_to_nfs(task)
        except Exception as e:
            logger.error(f"TE: Result export failed for task {task.id}: {e}")

        logger.info(f"TE Task {task.id}: model_path after export = {task.model_path}")
        task.status = 'completed'
        task.completed_at = datetime.utcnow()
        task.progress_percent = 100.0
        if task.started_at:
            task.duration = int((task.completed_at - task.started_at).total_seconds())

        from app.services.resource_manager import resource_manager
        from app.services.task_scheduler import task_scheduler
        resource_manager.release_resources(task.id)
        task_scheduler._remove_from_running(task.id)

        self._add_log(task.id, LogLevel.INFO, "system", "Training completed successfully")
        db.session.commit()
        logger.info(f"TE Task {task.id} completed successfully")

        from app.websocket.handlers import broadcast_status
        broadcast_status(task.id, 'completed', 'Training completed successfully')

        # 推送完成状态到 taitp
        self._notify_taitp(task, 'completed')

    def _handle_job_failed(self, task: Task, reason: str, message: str):
        error_msg = f"{reason}: {message}" if message else reason

        from app.services.resource_manager import resource_manager
        from app.services.task_scheduler import task_scheduler

        if task.retry_count < task.max_retries:
            task.retry_count += 1
            task.status = 'retrying'
            task.error_message = f"Attempt {task.retry_count} failed: {error_msg}"

            if task.job_name:
                k8s_job_executor.delete_job(task)
            task.job_name = None
            task.pod_names = None

            resource_manager.release_resources(task.id)
            task_scheduler._remove_from_running(task.id)
            task_scheduler.enqueue_task(task)

            self._add_log(task.id, LogLevel.WARNING, "system",
                         f"Task failed, retrying ({task.retry_count}/{task.max_retries}): {error_msg}")
            logger.info(f"TE Task {task.id} will retry (attempt {task.retry_count + 1})")
        else:
            task.status = 'failed'
            task.error_message = f"Max retries exceeded. Last error: {error_msg}"
            task.completed_at = datetime.utcnow()
            if task.started_at:
                task.duration = int((task.completed_at - task.started_at).total_seconds())

            resource_manager.release_resources(task.id)
            task_scheduler._remove_from_running(task.id)

            # 失败时也做最终日志采集，确保已有指标被保存
            try:
                from app.services.log_collector import log_collector
                log_collector.final_collect_task_logs(task)
            except Exception as e:
                logger.error(f"TE: Final log collection on failure for task {task.id}: {e}")

            self._add_log(task.id, LogLevel.ERROR, "system",
                         f"Task failed after {task.max_retries} attempts: {error_msg}")
            logger.error(f"TE Task {task.id} failed: {error_msg}")

        db.session.commit()

        # 推送失败状态（仅最终失败，重试中不推送）
        if task.status == 'failed':
            from app.websocket.handlers import broadcast_status
            broadcast_status(task.id, 'failed', error_msg)
            self._notify_taitp(task, 'failed')

    def _handle_job_missing(self, task: Task):
        error_msg = "Job was unexpectedly deleted"
        from app.services.resource_manager import resource_manager
        from app.services.task_scheduler import task_scheduler

        if task.retry_count < task.max_retries:
            task.retry_count += 1
            task.status = 'retrying'
            task.error_message = error_msg
            task.job_name = None
            task.pod_names = None

            resource_manager.release_resources(task.id)
            task_scheduler._remove_from_running(task.id)
            task_scheduler.enqueue_task(task)

            self._add_log(task.id, LogLevel.WARNING, "system", f"Job missing, retrying: {error_msg}")
        else:
            task.status = 'failed'
            task.error_message = error_msg
            task.completed_at = datetime.utcnow()

            resource_manager.release_resources(task.id)
            task_scheduler._remove_from_running(task.id)

            self._add_log(task.id, LogLevel.ERROR, "system", error_msg)

        db.session.commit()

    def _handle_pod_error(self, task: Task, pod_name: str, reason: str, message: str):
        error_msg = f"Pod {pod_name} error - {reason}: {message or 'No details'}"
        self._add_log(task.id, LogLevel.ERROR, pod_name, error_msg)

        from app.services.resource_manager import resource_manager
        from app.services.task_scheduler import task_scheduler

        if reason in ['ImagePullBackOff', 'ErrImagePull']:
            task.status = 'failed'
            task.error_message = f"Image pull failed: {message}"
            task.completed_at = datetime.utcnow()

            resource_manager.release_resources(task.id)
            task_scheduler._remove_from_running(task.id)
            k8s_job_executor.delete_job(task)

            db.session.commit()
            logger.error(f"TE Task {task.id} failed due to image pull error")

        elif reason in ['CrashLoopBackOff'] or reason.startswith('Exit code'):
            if task.job_name:
                k8s_job_executor.delete_job(task)
            self._handle_job_failed(task, reason, message or error_msg)

    def _export_results_to_nfs(self, task: Task):
        from app.models.metric import TaskMetric

        nfs_mount = current_app.config.get('NFS_MOUNT_PATH', '/data')
        # 优先使用 task.output_path（训练脚本的真实输出目录）
        if task.output_path:
            output_dir = task.output_path
            # 如果是容器路径如 /data/kubetrain/... 映射到 NFS 挂载
            nfs_base = current_app.config.get('NFS_REMOTE_BASE', '/data/kubetrain')
            if output_dir.startswith(nfs_base):
                output_dir_local = output_dir.replace(nfs_base, os.path.join(nfs_mount, 'kubetrain'), 1)
            else:
                output_dir_local = output_dir
        else:
            output_dir = os.path.join(nfs_mount, 'outputs', task.id)
            output_dir_local = output_dir

        nfs_root_accessible = (sys.platform == 'linux') and os.path.isdir(nfs_mount)
        if not nfs_root_accessible:
            logger.warning(f"TE Task {task.id}: NFS mount {nfs_mount} not accessible, trying SFTP scan")
            if not task.model_path:
                self._sftp_scan_model_path(task)
            return

        namespace = current_app.config.get('K8S_NAMESPACE', 'kubetrain')
        core_api = get_core_api()
        all_logs = []
        for pn in (task.pod_names or []):
            try:
                pod_log = core_api.read_namespaced_pod_log(
                    name=pn, namespace=namespace, container='trainer', timestamps=True)
                if pod_log:
                    all_logs.append(f"=== Pod: {pn} ===\n{pod_log}")
            except Exception as e:
                all_logs.append(f"=== Pod: {pn} ===\n[Error reading log: {e}]")
        full_log = '\n\n'.join(all_logs)

        metrics = TaskMetric.query.filter_by(task_id=task.id).order_by(TaskMetric.epoch).all()
        epoch_data = []
        for m in metrics:
            entry = {}
            if m.epoch is not None: entry['epoch'] = m.epoch
            if m.step is not None: entry['step'] = m.step
            if m.loss is not None: entry['loss'] = round(m.loss, 6)
            if m.accuracy is not None: entry['accuracy'] = round(m.accuracy, 6)
            if m.val_loss is not None: entry['val_loss'] = round(m.val_loss, 6)
            if m.val_accuracy is not None: entry['val_accuracy'] = round(m.val_accuracy, 6)
            if m.learning_rate is not None: entry['learning_rate'] = m.learning_rate
            if m.throughput is not None: entry['throughput'] = round(m.throughput, 2)
            if entry:
                epoch_data.append(entry)

        elapsed = None
        if task.started_at and task.completed_at:
            elapsed = round((task.completed_at - task.started_at).total_seconds(), 1)
        elif task.started_at:
            elapsed = round((datetime.utcnow() - task.started_at).total_seconds(), 1)

        summary = {
            'task_id': task.id,
            'task_name': task.name,
            'training_script': task.training_script,
            'parallel_mode': task.parallel_mode,
            'num_nodes': task.num_nodes,
            'total_epochs': task.total_epochs,
            'current_epoch': task.current_epoch,
            'final_loss': round(task.final_loss, 6) if task.final_loss is not None else None,
            'final_accuracy': round(task.final_accuracy, 6) if task.final_accuracy is not None else None,
            'elapsed_seconds': elapsed,
            'status': 'completed',
        }

        try:
            os.makedirs(os.path.join(output_dir, 'logs'), exist_ok=True)
            os.makedirs(os.path.join(output_dir, 'metrics'), exist_ok=True)

            with open(os.path.join(output_dir, 'logs', 'training.log'), 'w') as f:
                f.write(full_log)

            if epoch_data:
                with open(os.path.join(output_dir, 'metrics', 'epoch_metrics.json'), 'w') as f:
                    json.dump(epoch_data, f, indent=2, ensure_ascii=False)

            with open(os.path.join(output_dir, 'training_summary.json'), 'w') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)

            model_extensions = {'.pt', '.pth', '.bin', '.onnx', '.h5', '.pkl', '.joblib', '.safetensors'}
            model_files = []
            for root, dirs, files in os.walk(output_dir):
                for fname in files:
                    if any(fname.lower().endswith(ext) for ext in model_extensions):
                        model_files.append(os.path.join(root, fname))

            if model_files:
                best = None
                for mf in model_files:
                    basename = os.path.basename(mf).lower()
                    if 'final' in basename:
                        best = mf; break
                    if 'best' in basename and not best:
                        best = mf
                if not best:
                    best = model_files[0]
                task.model_path = best
                logger.info(f"TE Task {task.id} model_path set to {best}")

            logger.info(f"TE Task {task.id} results exported to NFS: {output_dir}")

        except Exception as e:
            logger.error(f"TE: Result export failed for task {task.id}: {e}")

    def _sftp_scan_model_path(self, task: Task):
        try:
            import paramiko
            host = current_app.config.get('SSH_HOST', '192.168.171.3')
            user = current_app.config.get('SSH_USER', 'root')
            port = int(current_app.config.get('SSH_PORT', 22))
            nfs_base = current_app.config.get('NFS_REMOTE_BASE', '/data/kubetrain')

            # 容器内 /data 是 PVC 挂载点，对应 NFS 服务器上的 nfs_base（如 /data/kubetrain）
            # 例: 容器 /data/kubetrain/outputs/exp1/ → NFS /data/kubetrain/kubetrain/outputs/exp1/
            if task.output_path and task.output_path.startswith('/data'):
                remote_output = nfs_base + task.output_path[len('/data'):]
            else:
                remote_output = f"{nfs_base}/outputs/{task.id}"
            logger.info(f"TE Task {task.id}: SFTP scan remote_output={remote_output}")

            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=host, port=port, username=user, timeout=10,
                          allow_agent=True, look_for_keys=True)

            model_extensions = {'.pt', '.pth', '.bin', '.onnx', '.h5', '.pkl', '.safetensors'}
            stdin, stdout, stderr = client.exec_command(
                f'find {remote_output} -type f \\( '
                + ' -o '.join(f'-name "*{ext}"' for ext in model_extensions)
                + f' \\) 2>/dev/null'
            )
            model_files = [line.strip() for line in stdout.readlines() if line.strip()]
            client.close()

            if model_files:
                best = None
                for mf in model_files:
                    basename = os.path.basename(mf).lower()
                    if 'final' in basename:
                        best = mf; break
                    if 'best' in basename and not best:
                        best = mf
                if not best:
                    best = model_files[0]
                container_path = best.replace(nfs_base, '/data', 1)
                task.model_path = container_path
                logger.info(f"TE Task {task.id} model_path set via SFTP: {container_path}")
            else:
                logger.warning(f"TE Task {task.id}: SFTP scan found no model files")

        except Exception as e:
            logger.warning(f"TE Task {task.id}: SFTP model scan failed: {e}")

    def _classify_error(self, error_message: str) -> str:
        """分类错误类型"""
        if not error_message:
            return 'UNKNOWN_ERROR'
        msg = error_message.lower()
        if 'oom' in msg or 'out of memory' in msg:
            return 'RESOURCE_ERROR'
        elif 'image' in msg and 'pull' in msg:
            return 'IMAGE_ERROR'
        elif 'crash' in msg:
            return 'CRASH_ERROR'
        elif 'timeout' in msg or 'time limit' in msg:
            return 'TIMEOUT_ERROR'
        elif 'script' in msg or 'syntax' in msg or 'import' in msg:
            return 'SCRIPT_ERROR'
        elif 'cuda' in msg or 'gpu' in msg or 'nccl' in msg:
            return 'GPU_ERROR'
        elif 'agent' in msg and ('dispatch' in msg or 'connect' in msg or 'max retries' in msg or 'connection' in msg):
            return 'AGENT_UNREACHABLE'
        elif 'ssl' in msg or 'certificate' in msg:
            return 'SSL_ERROR'
        elif 'pvc' in msg or 'nfs' in msg or 'persistent' in msg:
            return 'STORAGE_ERROR'
        elif 'max retries' in msg or 'connection' in msg:
            return 'CONNECTION_ERROR'
        else:
            return 'EXECUTION_ERROR'

    def _build_training_summary(self, task: Task) -> dict:
        """构建训练摘要"""
        elapsed = None
        if task.started_at and task.completed_at:
            elapsed = round((task.completed_at - task.started_at).total_seconds(), 1)
        elif task.started_at:
            elapsed = round((datetime.utcnow() - task.started_at).total_seconds(), 1)
        return {
            'task_id': task.id,
            'task_name': task.name,
            'parallel_mode': task.parallel_mode,
            'num_nodes': task.num_nodes,
            'total_epochs': task.total_epochs,
            'current_epoch': task.current_epoch,
            'final_loss': round(task.final_loss, 6) if task.final_loss is not None else None,
            'final_accuracy': round(task.final_accuracy, 6) if task.final_accuracy is not None else None,
            'elapsed_seconds': elapsed,
            'status': task.status,
        }

    def _notify_taitp(self, task: Task, status: str, extra: dict = None):
        """训练状态变更钩子：completed 时自动注册模型到仓库"""
        if status == 'completed' and task.model_path:
            try:
                self._auto_register_model(task)
            except Exception as e:
                logger.warning(f"KubeTrain2: auto model registration failed for task {task.id}: {e}")

    def _auto_register_model(self, task: Task):
        """训练完成后自动将模型输出注册到模型仓库"""
        from app.models.model import Model, ModelVersion
        existing = ModelVersion.query.filter_by(task_id=task.id).first()
        if existing:
            logger.info(f"KubeTrain2: Model already registered for task {task.id}, skipping")
            return
        model = Model(
            name=task.name,
            description=f'来自训练任务: {task.name}',
            framework='PyTorch',
            source='training',
            created_by=task.created_by,
        )
        db.session.add(model)
        db.session.flush()
        version = ModelVersion(
            model_id=model.id,
            version_number='v1.0',
            file_path=task.model_path or '',
            metrics={
                'final_loss': task.final_loss,
                'final_accuracy': task.final_accuracy,
                'best_metric': task.best_metric,
            },
            task_id=task.id,
            dataset_id=task.dataset_id,
            algorithm_version_id=task.algorithm_version_id,
            description=f'训练任务 {task.name} 自动注册，epochs={task.total_epochs}',
            created_by=task.created_by,
        )
        db.session.add(version)
        db.session.commit()
        logger.info(f"KubeTrain2: Model auto-registered from task {task.id} → model_id={model.id}")

    def _add_log(self, task_id: str, level: LogLevel, source: str, message: str):
        try:
            log = TaskLog(
                task_id=task_id, level=level, source=source,
                message=message, timestamp=datetime.utcnow()
            )
            db.session.add(log)
        except Exception as e:
            logger.error(f"TE: Failed to add log: {e}")


# 全局实例
task_watcher = TaskWatcher()
