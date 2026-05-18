"""
日志采集器 - 从KubeTrain迁入并适配FT-taitp
从 K8s Pod 收集训练日志，通过正则解析训练指标
配置项统一使用 TE_ 前缀
"""
import logging
import re
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

from flask import current_app
from kubernetes.client.rest import ApiException

from app import db
from app.models.task import Task, TaskStatus
from app.models.log import TaskLog, LogLevel
from app.models.metric import TaskMetric
from app.services.k8s_client import get_core_api

logger = logging.getLogger(__name__)


class TELogCollector:
    """日志采集器 - 从 Pod 收集日志并解析训练指标"""

    def __init__(self):
        self._running = False
        self._collector_thread = None
        self._namespace = None
        self._last_log_lines: Dict[str, int] = {}

    def start(self, app):
        if self._running:
            return
        self._running = True
        self._collector_thread = threading.Thread(
            target=self._collector_loop, args=(app,), daemon=True
        )
        self._collector_thread.start()
        logger.info("TE Log collector started")

    def stop(self):
        self._running = False
        if self._collector_thread:
            self._collector_thread.join(timeout=5)
        logger.info("TE Log collector stopped")

    def _collector_loop(self, app):
        with app.app_context():
            self._namespace = current_app.config.get('K8S_NAMESPACE', 'kubetrain')
            # 优先使用注册集群的 namespace
            try:
                from app.services.k8s_client import get_first_connected_cluster
                cluster = get_first_connected_cluster()
                if cluster and cluster.namespace:
                    self._namespace = cluster.namespace
                    logger.info(f"TE LogCollector: using cluster namespace '{self._namespace}'")
            except Exception as e:
                logger.warning(f"TE LogCollector: failed to get cluster namespace: {e}")
            logger.info(f"TE LogCollector: collector loop started, namespace='{self._namespace}'")
            while self._running:
                try:
                    interval = current_app.config.get('LOG_COLLECT_INTERVAL', 5)
                    self._collect_logs()
                except Exception as e:
                    logger.error(f"TE Log collector error: {e}", exc_info=True)
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                time.sleep(interval)

    def _collect_logs(self):
        try:
            db.session.remove()
        except Exception:
            pass

        running_tasks = Task.query.filter(
            Task.status.in_(['running', 'starting'])
        ).all()

        if running_tasks:
            logger.info(f"TE LogCollector: found {len(running_tasks)} running/starting tasks: "
                        f"{[(t.id[:8], t.status, t.pod_names) for t in running_tasks]}")

        for task in running_tasks:
            try:
                self._collect_task_logs(task)
                self._collect_task_resources(task)
            except Exception as e:
                logger.error(f"TE: Error collecting logs for task {task.id}: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass

    def _is_rank0_pod(self, task: Task, pod_name: str) -> bool:
        """判断是否为 rank-0 pod（只有 rank-0 的指标才写入 TaskMetric）"""
        if task.pod_names and len(task.pod_names) > 0:
            return pod_name == task.pod_names[0]
        return pod_name.endswith('-0')

    def _collect_task_logs(self, task: Task):
        if not task.pod_names:
            logger.debug(f"TE LogCollector: task {task.id[:8]} has no pod_names, skipping")
            return

        if not task.total_epochs and task.training_args:
            epochs_val = task.training_args.get('epochs') or task.training_args.get('num_epochs')
            if epochs_val:
                try:
                    task.total_epochs = int(epochs_val)
                except (ValueError, TypeError):
                    pass

        core_api = get_core_api()
        has_new_data = False

        for pod_name in task.pod_names:
            try:
                cache_key = f"{task.id}:{pod_name}"
                last_lines = self._last_log_lines.get(cache_key, 0)

                tail = current_app.config.get('LOG_TAIL_LINES', 500)
                logs = core_api.read_namespaced_pod_log(
                    name=pod_name, namespace=self._namespace,
                    container='trainer', tail_lines=tail, timestamps=True
                )

                if logs:
                    lines = logs.strip().split('\n')
                    new_lines = lines[last_lines:] if last_lines < len(lines) else []
                    logger.info(f"TE LogCollector: pod={pod_name[:20]} total_lines={len(lines)} "
                                f"last={last_lines} new={len(new_lines)}")
                    if new_lines:
                        is_rank0 = self._is_rank0_pod(task, pod_name)
                        if is_rank0:
                            self._process_pod_logs(task, pod_name, '\n'.join(new_lines))
                        else:
                            self._store_pod_logs_only(task, pod_name, '\n'.join(new_lines))
                        self._last_log_lines[cache_key] = len(lines)
                        has_new_data = True
                else:
                    logger.info(f"TE LogCollector: pod={pod_name[:20]} returned empty logs")

            except ApiException as e:
                if e.status == 404:
                    logger.info(f"TE LogCollector: pod {pod_name[:20]} not found (404)")
                    continue
                logger.warning(f"TE LogCollector: API error for pod {pod_name}: {e.status} {e.reason}")
            except Exception as e:
                logger.warning(f"TE LogCollector: Error reading logs for pod {pod_name}: {e}", exc_info=True)

        if has_new_data:
            try:
                db.session.commit()
            except Exception as e:
                logger.error(f"TE LogCollector: Commit failed for task {task.id}: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass

    def _process_pod_logs(self, task: Task, pod_name: str, logs: str):
        from app.websocket.handlers import broadcast_log, broadcast_metric, broadcast_progress
        lines = logs.strip().split('\n')
        for line in lines:
            if not line.strip():
                continue
            parts = line.split(' ', 1)
            content = parts[1] if len(parts) > 1 else line
            level = self._detect_log_level(content)
            try:
                log = TaskLog(
                    task_id=task.id, level=level, source=pod_name,
                    pod_name=pod_name, container_name='trainer',
                    message=content, timestamp=datetime.utcnow()
                )
                db.session.add(log)
                # WebSocket 实时推送日志
                broadcast_log(task.id, {
                    'task_id': task.id, 'level': level.value if hasattr(level, 'value') else str(level),
                    'message': content, 'pod_name': pod_name,
                    'timestamp': datetime.utcnow().isoformat()
                })
            except Exception as e:
                logger.error(f"TE: Failed to store log: {e}")
            metric_emitted = self._parse_training_metrics(task, pod_name, content)
            # WebSocket 实时推送指标（仅当有新 epoch 级别指标时）
            if metric_emitted:
                broadcast_metric(task.id, metric_emitted)
                broadcast_progress(task.id, task.progress_percent or 0,
                                   task.current_epoch or 0, task.total_epochs)

    def _detect_log_level(self, content: str) -> LogLevel:
        content_lower = content.lower()
        if 'error' in content_lower or 'exception' in content_lower or 'traceback' in content_lower:
            return LogLevel.ERROR
        elif 'warning' in content_lower or 'warn' in content_lower:
            return LogLevel.WARNING
        elif 'debug' in content_lower:
            return LogLevel.DEBUG
        return LogLevel.INFO

    def _parse_training_metrics(self, task: Task, pod_name: str, content: str):
        """解析训练指标，返回 metric dict 供 WebSocket 推送（无新指标时返回 None）"""
        # 优先解析 METRICS: JSON 行（训练脚本显式输出的结构化指标）
        metrics_match = re.search(r'METRICS:\s*(\{.*\})', content)
        if metrics_match:
            try:
                import json as _json
                mdata = _json.loads(metrics_match.group(1))
                metric = TaskMetric(task_id=task.id, timestamp=datetime.utcnow())
                if '-' in pod_name:
                    try:
                        metric.node_rank = int(pod_name.rsplit('-', 1)[-1])
                    except ValueError:
                        pass
                epoch = mdata.get('epoch')
                if epoch is not None:
                    metric.epoch = int(epoch)
                    task.current_epoch = metric.epoch
                total = mdata.get('total_epochs')
                if total:
                    task.total_epochs = int(total)
                if task.total_epochs and task.total_epochs > 0 and task.current_epoch:
                    task.progress_percent = (task.current_epoch / task.total_epochs) * 100
                if 'loss' in mdata:
                    metric.loss = float(mdata['loss'])
                    task.final_loss = metric.loss
                if 'accuracy' in mdata:
                    metric.accuracy = float(mdata['accuracy'])
                    task.final_accuracy = metric.accuracy
                if 'test_loss' in mdata:
                    metric.val_loss = float(mdata['test_loss'])
                if 'test_accuracy' in mdata:
                    metric.val_accuracy = float(mdata['test_accuracy'])
                    task.final_accuracy = metric.val_accuracy
                if 'learning_rate' in mdata:
                    metric.learning_rate = float(mdata['learning_rate'])
                db.session.add(metric)
                db.session.commit()
                return {
                    'task_id': task.id, 'epoch': metric.epoch,
                    'loss': metric.loss, 'accuracy': metric.accuracy,
                    'val_loss': metric.val_loss, 'val_accuracy': metric.val_accuracy,
                    'learning_rate': metric.learning_rate,
                    'timestamp': datetime.utcnow().isoformat()
                }
            except Exception as e:
                logger.debug(f"METRICS JSON parse failed: {e}")

        patterns = {
            'epoch_train_test': r'[Ee]poch\s+(\d+)/(\d+)\s*-\s*(?:[Tt]rain\s+)?[Ll]oss[:\s]+([0-9.]+).*?[Tt]rain\s+[Aa]cc[:\s]+([0-9.]+)%.*?[Tt]est\s+[Aa]cc[:\s]+([0-9.]+)%',
            'epoch_bracket_loss_acc': r'[Ee]poch\s*\[(\d+)/(\d+)\].*?[Ll]oss[:\s]+([0-9.]+).*?[Aa]cc(?:uracy)?[:\s]+([0-9.]+)',
            'epoch_loss_acc': r'[Ee]poch[:\s]+(\d+)(?:/(\d+))?\s*[,\s-]+(?:[Tt]rain\s+)?[Ll]oss[:\s]+([0-9.]+)(?:.*?(?:[Tt]rain\s+)?[Aa]cc(?:uracy)?[:\s]+([0-9.]+)%?)?',
            'epoch_batch_loss': r'[Ee]poch\s+(\d+)\s+\[.*?\]\s+[Ll]oss[:\s]+([0-9.]+)(?:\s+[Aa]cc[:\s]+([0-9.]+)%?)?',
            'test_set_result': r'[Tt]est\s+set.*[Aa]verage\s+loss[:\s]+([0-9.]+).*[Aa]ccuracy[:\s]+(?:\d+/\d+\s+\()?([0-9.]+)%\)?',
            'epoch_lr': r'[Ee]poch\s+(\d+)/(\d+)\s*[,\s]+(?:LR|lr|learning.rate)[:\s]+([0-9.e-]+)',
            'best_accuracy': r'[Bb]est\s+accuracy[:\s]+([0-9.]+)%?',
            'step_loss': r'[Ss]tep[:\s]+(\d+)\s*[,\s]+[Ll]oss[:\s]+([0-9.]+)',
            'training_loss': r'[Tt]raining\s+[Ll]oss[:\s]+([0-9.]+)',
            'val_accuracy': r'(?:[Vv]al(?:idation)?|[Tt]est)\s+[Aa]cc(?:uracy)?[:\s]+([0-9.]+)',
            'learning_rate': r'(?:lr|learning[_\s]rate)[:\s]+([0-9.e-]+)',
            'throughput': r'[Tt]hroughput[:\s]+([0-9.]+)\s*(?:samples?/s|it/s)',
        }
        for pattern_name, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                return self._store_metric(task, pod_name, pattern_name, match)
        return None

    def _store_metric(self, task: Task, pod_name: str, pattern_name: str, match):
        """存储指标记录并返回 metric dict 供 WS 推送（epoch_batch_loss 只更新进度不存储）"""
        try:
            old_epoch = task.current_epoch
            metric = TaskMetric(task_id=task.id, timestamp=datetime.utcnow())
            if '-' in pod_name:
                try:
                    index_str = pod_name.rsplit('-', 1)[-1]
                    metric.node_rank = int(index_str)
                except ValueError:
                    pass

            if pattern_name == 'epoch_batch_loss':
                # 批次级进度行：只更新 current_epoch 和 progress，不创建 metric 记录
                batch_epoch = int(match.group(1))
                if task.current_epoch != batch_epoch:
                    task.current_epoch = batch_epoch
                    if task.total_epochs and task.total_epochs > 0:
                        task.progress_percent = (batch_epoch / task.total_epochs) * 100
                return None  # 不创建 metric 记录，不推送

            elif pattern_name == 'test_set_result':
                metric.val_loss = float(match.group(1))
                acc_pct = float(match.group(2))
                metric.val_accuracy = acc_pct / 100.0
                metric.accuracy = metric.val_accuracy
                metric.loss = metric.val_loss
                metric.epoch = task.current_epoch
                task.final_accuracy = metric.val_accuracy
                task.final_loss = metric.val_loss

            elif pattern_name == 'best_accuracy':
                best_acc = float(match.group(1)) / 100.0
                metric.accuracy = best_acc
                if not task.final_accuracy or best_acc > task.final_accuracy:
                    task.final_accuracy = best_acc
                task.best_metric = {'best_accuracy': round(best_acc * 100, 2)}

            elif pattern_name == 'epoch_train_test':
                metric.epoch = int(match.group(1))
                task.total_epochs = int(match.group(2))
                task.current_epoch = metric.epoch
                task.progress_percent = (metric.epoch / task.total_epochs) * 100
                metric.loss = float(match.group(3))
                metric.accuracy = float(match.group(4)) / 100.0
                metric.val_accuracy = float(match.group(5)) / 100.0
                task.final_loss = metric.loss
                task.final_accuracy = metric.val_accuracy

            elif pattern_name == 'epoch_bracket_loss_acc':
                metric.epoch = int(match.group(1))
                task.total_epochs = int(match.group(2))
                task.current_epoch = metric.epoch
                task.progress_percent = (metric.epoch / task.total_epochs) * 100
                metric.loss = float(match.group(3))
                task.final_loss = metric.loss
                acc_val = float(match.group(4))
                metric.accuracy = acc_val if acc_val <= 1.0 else acc_val / 100.0
                task.final_accuracy = metric.accuracy

            elif pattern_name == 'epoch_loss_acc':
                metric.epoch = int(match.group(1))
                if match.group(2):
                    task.total_epochs = int(match.group(2))
                    task.current_epoch = metric.epoch
                    task.progress_percent = (metric.epoch / task.total_epochs) * 100
                metric.loss = float(match.group(3))
                task.final_loss = metric.loss
                if match.group(4):
                    metric.accuracy = float(match.group(4))
                    task.final_accuracy = metric.accuracy

            elif pattern_name == 'step_loss':
                metric.step = int(match.group(1))
                metric.loss = float(match.group(2))
                task.final_loss = metric.loss

            elif pattern_name == 'training_loss':
                metric.loss = float(match.group(1))
                task.final_loss = metric.loss

            elif pattern_name == 'val_accuracy':
                metric.val_accuracy = float(match.group(1))
                task.final_accuracy = metric.val_accuracy

            elif pattern_name == 'learning_rate':
                metric.learning_rate = float(match.group(1))

            elif pattern_name == 'throughput':
                metric.throughput = float(match.group(1))

            elif pattern_name == 'epoch_lr':
                metric.epoch = int(match.group(1))
                task.total_epochs = int(match.group(2))
                task.current_epoch = metric.epoch
                task.progress_percent = (metric.epoch / task.total_epochs) * 100
                metric.learning_rate = float(match.group(3))

            db.session.add(metric)

            # epoch 变化时通过 WebSocket 推送进度
            if task.current_epoch and task.current_epoch != old_epoch:
                try:
                    from app.websocket.handlers import broadcast_status
                    broadcast_status(task.id, 'running',
                                     f'Epoch {task.current_epoch}/{task.total_epochs}')
                except Exception as cb_err:
                    logger.debug(f"TE: Epoch progress broadcast failed: {cb_err}")

            return {
                'task_id': task.id, 'epoch': metric.epoch,
                'loss': metric.loss, 'accuracy': metric.accuracy,
                'val_loss': metric.val_loss, 'val_accuracy': metric.val_accuracy,
                'learning_rate': metric.learning_rate,
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"TE: Failed to store metric: {e}")

    def _collect_task_resources(self, task: Task):
        """从 K8s metrics-server 采集任务 Pod 的 CPU/内存使用"""
        if not task.pod_names:
            return
        namespace = self._namespace or current_app.config.get('K8S_NAMESPACE', 'kubetrain')
        try:
            from app.services.k8s_client import get_k8s_clients
            clients = get_k8s_clients()
            custom_api = clients.get('custom')
            if not custom_api:
                from kubernetes import client as k8s_client
                custom_api = k8s_client.CustomObjectsApi()
                clients['custom'] = custom_api

            total_cpu_nano = 0
            total_mem_bytes = 0
            pod_count = 0

            for pn in task.pod_names:
                try:
                    pod_metrics = custom_api.get_namespaced_custom_object(
                        group='metrics.k8s.io', version='v1beta1',
                        namespace=namespace, plural='pods', name=pn
                    )
                    for container in pod_metrics.get('containers', []):
                        usage = container.get('usage', {})
                        cpu_str = usage.get('cpu', '0')
                        mem_str = usage.get('memory', '0')
                        if cpu_str.endswith('n'):
                            total_cpu_nano += int(cpu_str[:-1])
                        elif cpu_str.endswith('m'):
                            total_cpu_nano += int(cpu_str[:-1]) * 1000000
                        else:
                            try:
                                total_cpu_nano += int(float(cpu_str) * 1e9)
                            except (ValueError, TypeError):
                                pass
                        if mem_str.endswith('Ki'):
                            total_mem_bytes += int(mem_str[:-2]) * 1024
                        elif mem_str.endswith('Mi'):
                            total_mem_bytes += int(mem_str[:-2]) * 1024 * 1024
                        elif mem_str.endswith('Gi'):
                            total_mem_bytes += int(float(mem_str[:-2]) * 1024 * 1024 * 1024)
                        else:
                            try:
                                total_mem_bytes += int(mem_str)
                            except (ValueError, TypeError):
                                pass
                    pod_count += 1
                except Exception:
                    pass

            if pod_count > 0:
                cpu_cores = total_cpu_nano / 1e9
                mem_mb = total_mem_bytes / (1024 * 1024)
                cpu_limit_val = self._parse_cpu_value(task.cpu_limit) * task.num_nodes if task.cpu_limit else 1
                cpu_pct = min((cpu_cores / cpu_limit_val) * 100, 100) if cpu_limit_val > 0 else 0
                mem_limit_val = self._parse_mem_value(task.memory_limit) * task.num_nodes if task.memory_limit else 1
                mem_pct = min((mem_mb / mem_limit_val) * 100, 100) if mem_limit_val > 0 else 0

                metric = TaskMetric(
                    task_id=task.id,
                    cpu_utilization=round(cpu_pct, 1),
                    memory_used=round(mem_pct, 1),
                    gpu_utilization=0.0,
                    gpu_memory_used=0.0,
                    timestamp=datetime.utcnow()
                )
                db.session.add(metric)
                db.session.commit()
        except Exception as e:
            logger.debug(f"TE: Resource collection failed for task {task.id}: {e}")

    @staticmethod
    def _parse_cpu_value(cpu_str):
        if not cpu_str:
            return 1
        cpu_str = str(cpu_str)
        if cpu_str.endswith('m'):
            return int(cpu_str[:-1]) / 1000
        try:
            return float(cpu_str)
        except (ValueError, TypeError):
            return 1

    @staticmethod
    def _parse_mem_value(mem_str):
        """Parse memory string to MB"""
        if not mem_str:
            return 1024
        mem_str = str(mem_str)
        if mem_str.endswith('Gi'):
            return float(mem_str[:-2]) * 1024
        if mem_str.endswith('Mi'):
            return float(mem_str[:-2])
        if mem_str.endswith('Ki'):
            return float(mem_str[:-2]) / 1024
        try:
            return float(mem_str) / (1024 * 1024)
        except (ValueError, TypeError):
            return 1024

    def final_collect_task_logs(self, task: Task):
        if not task.job_name:
            return

        from app.services.k8s_job_executor import k8s_job_executor

        if not task.pod_names:
            pod_names = k8s_job_executor.get_pod_names(task.job_name)
            if pod_names:
                task.pod_names = pod_names
            else:
                return

        namespace = self._namespace or current_app.config.get('K8S_NAMESPACE', 'kubetrain')
        core_api = get_core_api()

        # 先采集完整日志到临时列表，再一次性替换，避免中间态被客户端看到
        collected_logs = []
        collected_metrics_task = None  # rank-0 pod 的完整日志用于解析指标

        for pn in task.pod_names:
            cache_key = f"{task.id}:{pn}"
            self._last_log_lines.pop(cache_key, None)

        for i, pn in enumerate(task.pod_names):
            try:
                logs = core_api.read_namespaced_pod_log(
                    name=pn, namespace=namespace,
                    container='trainer', timestamps=True
                )
                if logs:
                    collected_logs.append((i, pn, logs))
            except Exception as e:
                logger.debug(f"TE: Final collect error for pod {pn}: {e}")

        if not collected_logs:
            return

        # 增量补充：只处理之前未采集到的新日志行，不删除已有数据
        for i, pn, logs in collected_logs:
            cache_key = f"{task.id}:{pn}"
            existing_count = TaskLog.query.filter_by(task_id=task.id, pod_name=pn).count()
            lines = logs.strip().split('\n')
            new_lines = lines[existing_count:] if existing_count < len(lines) else []
            if new_lines:
                new_logs_text = '\n'.join(new_lines)
                if i == 0:
                    self._process_pod_logs(task, pn, new_logs_text)
                else:
                    self._store_pod_logs_only(task, pn, new_logs_text)
            self._last_log_lines[cache_key] = len(lines)

        if not task.total_epochs and task.training_args:
            epochs_str = task.training_args.get('epochs') or task.training_args.get('num_epochs')
            if epochs_str:
                try:
                    task.total_epochs = int(epochs_str)
                except (ValueError, TypeError):
                    pass

        if task.total_epochs and task.current_epoch >= task.total_epochs:
            task.progress_percent = 100.0

        try:
            db.session.commit()
            logger.info(f"TE: Final log collection done for task {task.id}: "
                       f"epoch={task.current_epoch}, loss={task.final_loss}, acc={task.final_accuracy}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"TE: Failed to commit final logs for task {task.id}: {e}")

    def _store_pod_logs_only(self, task: Task, pod_name: str, logs: str):
        lines = logs.strip().split('\n')
        for line in lines:
            if not line.strip():
                continue
            parts = line.split(' ', 1)
            content = parts[1] if len(parts) > 1 else line
            level = self._detect_log_level(content)
            try:
                log = TaskLog(
                    task_id=task.id, level=level, source=pod_name,
                    pod_name=pod_name, container_name='trainer',
                    message=content, timestamp=datetime.utcnow()
                )
                db.session.add(log)
            except Exception as e:
                logger.error(f"TE: Failed to store log: {e}")

    def get_task_logs(self, task_id: str, limit: int = 100,
                      level: LogLevel = None, pod_name: str = None) -> List[TaskLog]:
        query = TaskLog.query.filter_by(task_id=task_id)
        if level:
            query = query.filter_by(level=level)
        if pod_name:
            query = query.filter_by(pod_name=pod_name)
        return query.order_by(TaskLog.timestamp.desc()).limit(limit).all()

    def get_live_logs(self, task: Task, pod_name: str = None, tail_lines: int = 100) -> Optional[str]:
        if not task.pod_names:
            return None

        namespace = self._namespace or current_app.config.get('K8S_NAMESPACE', 'kubetrain')
        core_api = get_core_api()
        target_pods = [pod_name] if pod_name else task.pod_names

        logs = []
        for pn in target_pods:
            try:
                pod_logs = core_api.read_namespaced_pod_log(
                    name=pn, namespace=namespace,
                    container='trainer', tail_lines=tail_lines, timestamps=True
                )
                logs.append(f"=== Pod: {pn} ===\n{pod_logs}")
            except Exception as e:
                logs.append(f"=== Pod: {pn} ===\nError: {e}")

        return '\n\n'.join(logs)


# 全局实例
log_collector = TELogCollector()
