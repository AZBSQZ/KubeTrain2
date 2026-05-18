"""
告警服务 - 从KubeTrain迁入并适配FT-taitp
异常检测、告警生成、告警推送，配置项统一使用 TE_ 前缀
"""
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from flask import current_app

from app import db
from app.models.task import Task
from app.models.metric import TaskMetric
from app.models.alert import Alert, AlertRule, AlertLevel, AlertType, AlertStatus
from app.models.resource import ResourceNode

logger = logging.getLogger(__name__)


class AlertService:
    """告警服务"""

    def __init__(self):
        self._running = False
        self._alert_thread = None
        self._default_rules_created = False

    def start(self, app):
        if self._running:
            return
        self._running = True
        self._alert_thread = threading.Thread(
            target=self._alert_loop, args=(app,), daemon=True
        )
        self._alert_thread.start()
        logger.info("TE Alert service started")

    def stop(self):
        self._running = False
        if self._alert_thread:
            self._alert_thread.join(timeout=5)
        logger.info("TE Alert service stopped")

    def _alert_loop(self, app):
        with app.app_context():
            if not self._default_rules_created:
                self._create_default_rules()
                self._default_rules_created = True
            while self._running:
                try:
                    self._check_all_rules()
                except Exception as e:
                    logger.error(f"TE Alert service error: {e}")
                time.sleep(current_app.config.get('ALERT_CHECK_INTERVAL', 30))

    def _create_default_rules(self):
        default_rules = [
            {
                'name': 'TE-GPU低利用率告警',
                'description': 'GPU利用率低于50%持续5分钟',
                'alert_type': AlertType.GPU_LOW_UTILIZATION,
                'level': AlertLevel.WARNING,
                'condition': {'metric': 'gpu_utilization', 'operator': '<', 'threshold': 50, 'duration_minutes': 5},
                'cooldown_seconds': 600
            },
            {
                'name': 'TE-内存使用率过高告警',
                'description': '内存使用率超过90%',
                'alert_type': AlertType.MEMORY_HIGH_USAGE,
                'level': AlertLevel.ERROR,
                'condition': {'metric': 'memory_utilization', 'operator': '>', 'threshold': 90, 'duration_minutes': 1},
                'cooldown_seconds': 300
            },
            {
                'name': 'TE-训练损失不下降告警',
                'description': '训练损失连续10轮不下降',
                'alert_type': AlertType.LOSS_NOT_DECREASING,
                'level': AlertLevel.WARNING,
                'condition': {'metric': 'loss', 'check_type': 'no_decrease', 'epochs': 10},
                'cooldown_seconds': 1800
            },
            {
                'name': 'TE-训练超时告警',
                'description': '训练时间超过预期2倍',
                'alert_type': AlertType.TRAINING_TIMEOUT,
                'level': AlertLevel.ERROR,
                'condition': {'check_type': 'timeout', 'multiplier': 2},
                'cooldown_seconds': 3600
            },
            {
                'name': 'TE-节点离线告警',
                'description': '检测到节点离线',
                'alert_type': AlertType.NODE_OFFLINE,
                'level': AlertLevel.CRITICAL,
                'condition': {'check_type': 'node_status', 'status': 'offline'},
                'cooldown_seconds': 300
            }
        ]
        try:
            for rule_data in default_rules:
                existing = AlertRule.query.filter_by(name=rule_data['name']).first()
                if not existing:
                    rule = AlertRule(
                        name=rule_data['name'], description=rule_data['description'],
                        alert_type=rule_data['alert_type'], level=rule_data['level'],
                        condition=rule_data['condition'], cooldown_seconds=rule_data['cooldown_seconds'],
                        is_enabled=True
                    )
                    db.session.add(rule)
            db.session.commit()
            logger.info("TE: Default alert rules created")
        except Exception as e:
            db.session.rollback()
            logger.error(f"TE: Failed to create default rules: {e}")

    def _check_all_rules(self):
        try:
            db.session.remove()
        except Exception:
            pass
        rules = AlertRule.query.filter_by(is_enabled=True).all()
        for rule in rules:
            try:
                if rule.last_triggered_at:
                    cooldown_end = rule.last_triggered_at + timedelta(seconds=rule.cooldown_seconds)
                    if datetime.utcnow() < cooldown_end:
                        continue
                self._check_rule(rule)
            except Exception as e:
                logger.error(f"TE: Error checking rule {rule.name}: {e}")

    def _check_rule(self, rule: AlertRule):
        condition = rule.condition
        if rule.alert_type == AlertType.GPU_LOW_UTILIZATION:
            self._check_gpu_utilization(rule, condition)
        elif rule.alert_type == AlertType.MEMORY_HIGH_USAGE:
            self._check_memory_usage(rule, condition)
        elif rule.alert_type == AlertType.LOSS_NOT_DECREASING:
            self._check_loss_trend(rule, condition)
        elif rule.alert_type == AlertType.TRAINING_TIMEOUT:
            self._check_training_timeout(rule, condition)
        elif rule.alert_type == AlertType.NODE_OFFLINE:
            self._check_node_status(rule, condition)

    def _check_gpu_utilization(self, rule: AlertRule, condition: Dict):
        threshold = condition.get('threshold', 50)
        duration = condition.get('duration_minutes', 5)
        running_tasks = Task.query.filter_by(status='running').all()
        for task in running_tasks:
            if task.gpu_limit == 0:
                continue
            since = datetime.utcnow() - timedelta(minutes=duration)
            metrics = TaskMetric.query.filter(
                TaskMetric.task_id == task.id,
                TaskMetric.gpu_utilization.isnot(None),
                TaskMetric.timestamp >= since
            ).all()
            if len(metrics) >= 3:
                avg_util = sum(m.gpu_utilization for m in metrics) / len(metrics)
                if avg_util < threshold:
                    self._create_alert(rule=rule, task_id=task.id,
                        title=f"任务 {task.name} GPU利用率过低",
                        message=f"GPU利用率 {avg_util:.1f}% 低于阈值 {threshold}%，已持续 {duration} 分钟",
                        details={'avg_utilization': avg_util, 'threshold': threshold})

    def _check_memory_usage(self, rule: AlertRule, condition: Dict):
        threshold = condition.get('threshold', 90)
        running_tasks = Task.query.filter_by(status='running').all()
        for task in running_tasks:
            metric = TaskMetric.query.filter(
                TaskMetric.task_id == task.id,
                TaskMetric.memory_used.isnot(None)
            ).order_by(TaskMetric.timestamp.desc()).first()
            if metric and metric.memory_used:
                memory_limit = self._parse_memory(task.memory_limit)
                if memory_limit > 0:
                    usage_percent = (metric.memory_used / memory_limit) * 100
                    if usage_percent > threshold:
                        self._create_alert(rule=rule, task_id=task.id,
                            title=f"任务 {task.name} 内存使用率过高",
                            message=f"内存使用率 {usage_percent:.1f}% 超过阈值 {threshold}%",
                            details={'usage_percent': usage_percent, 'threshold': threshold})

    def _parse_memory(self, memory_str: str) -> int:
        if not memory_str:
            return 0
        units = {'Ki': 1/1024, 'Mi': 1, 'Gi': 1024, 'Ti': 1024*1024}
        for unit, mult in units.items():
            if memory_str.endswith(unit):
                return int(float(memory_str[:-len(unit)]) * mult)
        return int(memory_str) if memory_str.isdigit() else 0

    def _check_loss_trend(self, rule: AlertRule, condition: Dict):
        epochs_to_check = condition.get('epochs', 10)
        running_tasks = Task.query.filter_by(status='running').all()
        for task in running_tasks:
            metrics = TaskMetric.query.filter(
                TaskMetric.task_id == task.id,
                TaskMetric.loss.isnot(None),
                TaskMetric.epoch.isnot(None)
            ).order_by(TaskMetric.epoch.desc()).limit(epochs_to_check).all()
            if len(metrics) >= epochs_to_check:
                losses = [m.loss for m in reversed(metrics)]
                is_decreasing = any(losses[i] < losses[i-1] for i in range(1, len(losses)))
                if not is_decreasing:
                    self._create_alert(rule=rule, task_id=task.id,
                        title=f"任务 {task.name} 训练损失停滞",
                        message=f"训练损失连续 {epochs_to_check} 轮未下降",
                        details={'losses': losses})

    def _check_training_timeout(self, rule: AlertRule, condition: Dict):
        multiplier = condition.get('multiplier', 2)
        timeout = current_app.config.get('TRAINING_TIMEOUT', 86400)
        running_tasks = Task.query.filter_by(status='running').all()
        for task in running_tasks:
            if task.started_at:
                actual_duration = (datetime.utcnow() - task.started_at).total_seconds()
                if actual_duration > timeout * multiplier:
                    self._create_alert(rule=rule, task_id=task.id,
                        title=f"任务 {task.name} 训练超时",
                        message=f"训练已运行 {actual_duration/3600:.1f} 小时，超过预期时间 {multiplier} 倍",
                        details={'actual_hours': actual_duration / 3600, 'expected_hours': timeout / 3600})

    def _check_node_status(self, rule: AlertRule, condition: Dict):
        offline_nodes = ResourceNode.query.filter_by(status='offline').all()
        for node in offline_nodes:
            self._create_alert(rule=rule, node_id=node.id,
                title=f"节点 {node.name} 离线",
                message=f"检测到节点 {node.name} ({node.ip_address}) 已离线",
                details={'node_name': node.name, 'last_heartbeat': node.last_heartbeat.isoformat() if node.last_heartbeat else None})

    def _create_alert(self, rule: AlertRule, title: str, message: str,
                     task_id: str = None, node_id: str = None,
                     pod_name: str = None, details: Dict = None):
        try:
            existing = Alert.query.filter(Alert.rule_id == rule.id, Alert.status == AlertStatus.ACTIVE)
            if task_id:
                existing = existing.filter(Alert.task_id == task_id)
            if node_id:
                existing = existing.filter(Alert.node_id == node_id)
            if existing.first():
                return

            alert = Alert(
                alert_type=rule.alert_type, level=rule.level, status=AlertStatus.ACTIVE,
                task_id=task_id, node_id=node_id, pod_name=pod_name,
                title=title, message=message, details=details,
                rule_id=rule.id, created_at=datetime.utcnow()
            )
            db.session.add(alert)
            rule.last_triggered_at = datetime.utcnow()
            db.session.commit()
            self._broadcast_alert(alert)
            logger.warning(f"TE Alert created: [{rule.level.value}] {title}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"TE: Failed to create alert: {e}")

    def _broadcast_alert(self, alert: Alert):
        try:
            from app.websocket.handlers import broadcast_alert
            broadcast_alert(alert.to_dict())
        except Exception as e:
            logger.debug(f"TE: Failed to broadcast alert: {e}")

    def create_manual_alert(self, alert_type: AlertType, level: AlertLevel,
                           title: str, message: str, task_id: str = None,
                           details: Dict = None) -> Optional[Alert]:
        try:
            alert = Alert(
                alert_type=alert_type, level=level, status=AlertStatus.ACTIVE,
                task_id=task_id, title=title, message=message,
                details=details, created_at=datetime.utcnow()
            )
            db.session.add(alert)
            db.session.commit()
            self._broadcast_alert(alert)
            return alert
        except Exception as e:
            db.session.rollback()
            logger.error(f"TE: Failed to create manual alert: {e}")
            return None

    def acknowledge_alert(self, alert_id: int, user: str):
        try:
            alert = Alert.query.get(alert_id)
            if alert and alert.status == AlertStatus.ACTIVE:
                alert.status = AlertStatus.ACKNOWLEDGED
                alert.acknowledged_by = user
                alert.acknowledged_at = datetime.utcnow()
                db.session.commit()
                return True, "Alert acknowledged"
            return False, "Alert not found or not active"
        except Exception as e:
            db.session.rollback()
            return False, str(e)

    def resolve_alert(self, alert_id: int, user: str, note: str = None):
        try:
            alert = Alert.query.get(alert_id)
            if alert and alert.status != AlertStatus.RESOLVED:
                alert.status = AlertStatus.RESOLVED
                alert.resolved_by = user
                alert.resolved_at = datetime.utcnow()
                alert.resolution_note = note
                db.session.commit()
                return True, "Alert resolved"
            return False, "Alert not found or already resolved"
        except Exception as e:
            db.session.rollback()
            return False, str(e)

    def get_alerts(self, status=None, level=None, limit=50):
        query = Alert.query
        if status:
            try:
                query = query.filter(Alert.status == AlertStatus(status))
            except ValueError:
                pass
        if level:
            try:
                query = query.filter(Alert.level == AlertLevel(level))
            except ValueError:
                pass
        return query.order_by(Alert.created_at.desc()).limit(limit).all()

    def get_active_alerts(self, task_id: str = None) -> List[Alert]:
        query = Alert.query.filter(Alert.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]))
        if task_id:
            query = query.filter_by(task_id=task_id)
        return query.order_by(Alert.created_at.desc()).all()


# 全局实例
alert_service = AlertService()
