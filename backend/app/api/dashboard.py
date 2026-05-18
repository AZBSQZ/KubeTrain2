"""
Dashboard API - 角色感知的概览统计端点
参考 FT_local/taitp/flask/app/api/dashboard.py 移植
"""
import os
import subprocess
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy import func, cast, Date as SADate
from app import db
from app.models.task import Task
from app.models.dataset import Dataset
from app.models.algorithm import Algorithm
from app.models.model import Model
from app.models.user import User
from app.models.alert import Alert
from app.utils.datetime_helper import format_datetime

dashboard_bp = Blueprint('dashboard', __name__)


def _get_system_resources():
    """获取系统资源使用率（CPU/内存/磁盘/GPU）"""
    try:
        import psutil
        disk_path = 'C:\\' if os.name == 'nt' else '/'
        result = {
            'cpu_percent': psutil.cpu_percent(interval=None),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage(disk_path).percent,
        }
    except Exception:
        result = {'cpu_percent': 0, 'memory_percent': 0, 'disk_percent': 0}

    try:
        proc = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=2
        )
        if proc.returncode == 0:
            lines = [l.strip() for l in proc.stdout.strip().split('\n') if l.strip()]
            if lines:
                result['gpu_percent'] = float(lines[0])
            else:
                result['gpu_percent'] = 0
        else:
            result['gpu_percent'] = 0
    except Exception:
        result['gpu_percent'] = 0

    return result


def _daily_task_counts(week_ago, user_id, is_admin, extra_filter=None):
    """获取最近 7 天每日任务数量（一条聚合查询）"""
    q = db.session.query(
        cast(Task.created_at, SADate).label('day'),
        func.count(Task.id)
    ).filter(Task.created_at >= week_ago)
    if not is_admin and user_id:
        q = q.filter(Task.created_by == user_id)
    if extra_filter is not None:
        q = q.filter(extra_filter)
    return {str(day): cnt for day, cnt in q.group_by('day').all()}


@dashboard_bp.route('', methods=['GET'])
@jwt_required()
def get_dashboard():
    """
    综合 Dashboard 数据：
    - stats: 各模块总数
    - statusDistribution: 任务状态分布
    - trainingStats: 最近 7 天趋势
    - recentTasks: 最近 8 条任务
    - systemResources: CPU/内存/磁盘/GPU
    - todayStats / weekStats: 今日/本周统计
    - workerStats: Agent 节点资源（仅 admin）
    """
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    role = claims.get('role', 'user')
    is_admin = (role == 'admin')

    # --- 基础统计（角色隔离）---
    if is_admin:
        total_tasks = Task.query.count()
        total_datasets = Dataset.query.filter_by(is_deleted=False).count()
        total_algorithms = Algorithm.query.filter_by(is_deleted=False).count()
        total_models = Model.query.filter_by(is_deleted=False).count()
        total_users = User.query.filter_by(is_active=True).count()
    else:
        total_tasks = Task.query.filter_by(created_by=user_id).count()
        total_datasets = Dataset.query.filter_by(is_deleted=False, created_by=user_id).count()
        total_algorithms = Algorithm.query.filter_by(is_deleted=False, created_by=user_id).count()
        total_models = Model.query.filter_by(is_deleted=False, created_by=user_id).count()
        total_users = 1

    # --- 任务状态分布（单条 GROUP BY）---
    status_q = db.session.query(Task.status, func.count(Task.id))
    if not is_admin:
        status_q = status_q.filter(Task.created_by == user_id)
    status_rows = status_q.group_by(Task.status).all()
    status_dist = {s: 0 for s in ('pending', 'queued', 'running', 'completed', 'failed', 'cancelled')}
    for s, cnt in status_rows:
        if s in status_dist:
            status_dist[s] = cnt

    # --- 今日 / 本周统计 ---
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

    if is_admin:
        today_tasks = Task.query.filter(Task.created_at >= today_start).count()
        today_completed = Task.query.filter(
            Task.completed_at >= today_start, Task.status == 'completed'
        ).count()
        week_tasks = Task.query.filter(Task.created_at >= week_start).count()
    else:
        today_tasks = Task.query.filter(Task.created_at >= today_start, Task.created_by == user_id).count()
        today_completed = Task.query.filter(
            Task.completed_at >= today_start, Task.status == 'completed', Task.created_by == user_id
        ).count()
        week_tasks = Task.query.filter(Task.created_at >= week_start, Task.created_by == user_id).count()

    # --- 最近 7 天趋势 ---
    week_ago = (datetime.now() - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    all_counts = _daily_task_counts(week_ago, user_id, is_admin)
    completed_counts = _daily_task_counts(week_ago, user_id, is_admin, Task.status == 'completed')
    failed_counts = _daily_task_counts(week_ago, user_id, is_admin, Task.status == 'failed')

    training_stats = []
    for i in range(7):
        d = datetime.now() - timedelta(days=6 - i)
        d = d.replace(hour=0, minute=0, second=0, microsecond=0)
        dk = d.strftime('%Y-%m-%d')
        training_stats.append({
            'date': d.strftime('%m-%d'),
            'total': all_counts.get(dk, 0),
            'completed': completed_counts.get(dk, 0),
            'failed': failed_counts.get(dk, 0),
        })

    # --- 最近 8 条任务 ---
    recent_q = Task.query
    if not is_admin:
        recent_q = recent_q.filter(Task.created_by == user_id)
    recent_tasks_rows = recent_q.order_by(Task.created_at.desc()).limit(8).all()

    # Batch-load creators
    creator_ids = list({t.created_by for t in recent_tasks_rows if t.created_by})
    creators_map = {}
    if creator_ids:
        for u in User.query.filter(User.id.in_(creator_ids)).all():
            creators_map[u.id] = u.username

    recent_tasks = []
    for t in recent_tasks_rows:
        recent_tasks.append({
            'id': t.id,
            'name': t.name,
            'status': t.status,
            'parallel_mode': t.parallel_mode,
            'num_nodes': t.num_nodes,
            'creator': creators_map.get(t.created_by, ''),
            'created_at': format_datetime(t.created_at),
            'completed_at': format_datetime(t.completed_at) if hasattr(t, 'completed_at') else None,
        })

    # --- 活跃告警（最近 5 条）---
    active_alerts_rows = Alert.query.filter_by(status='active').order_by(Alert.created_at.desc()).limit(5).all()
    active_alerts = [{'id': a.id, 'level': a.level, 'message': a.message, 'created_at': format_datetime(a.created_at)} for a in active_alerts_rows]

    # --- Worker / 资源统计 ---
    worker_stats = {}
    try:
        from app.services.worker_registry import worker_registry
        ws = worker_registry.get_worker_stats()
        worker_stats = {
            'total': ws.get('total_workers', 0),
            'online': ws.get('online_workers', 0),
            'total_gpus': ws.get('total_gpu', 0),
            'available_gpus': ws.get('available_gpu', 0),
            'total_cpu': ws.get('total_cpu', 0),
            'total_memory_gb': round(ws.get('total_memory', 0) / 1024, 1) if ws.get('total_memory') else 0,
        }
    except Exception:
        pass

    # --- 系统资源（psutil + nvidia-smi）---
    system_resources = _get_system_resources()

    return jsonify({
        'code': 200,
        'data': {
            'stats': {
                'tasks': total_tasks,
                'datasets': total_datasets,
                'algorithms': total_algorithms,
                'models': total_models,
                'users': total_users,
                'running': status_dist.get('running', 0),
            },
            'todayStats': {
                'tasks': today_tasks,
                'completed': today_completed,
            },
            'weekStats': {
                'tasks': week_tasks,
            },
            'statusDistribution': status_dist,
            'trainingStats': training_stats,
            'recentTasks': recent_tasks,
            'activeAlerts': active_alerts,
            'workerStats': worker_stats,
            'systemResources': system_resources,
        }
    })
