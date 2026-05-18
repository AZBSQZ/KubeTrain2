from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func
from app import db
from app.models.metric import TaskMetric

metrics_bp = Blueprint('metrics', __name__)


@metrics_bp.route('/tasks/<task_id>', methods=['GET'])
@jwt_required()
def get_task_metrics(task_id):
    limit = request.args.get('limit', 500, type=int)
    metrics = TaskMetric.query.filter_by(task_id=task_id).order_by(TaskMetric.timestamp.asc()).limit(limit).all()
    return jsonify({'code': 200, 'data': [m.to_dict() for m in metrics]})


@metrics_bp.route('/tasks/<task_id>/summary', methods=['GET'])
@jwt_required()
def get_task_metrics_summary(task_id):
    rows = (
        db.session.query(
            TaskMetric.epoch,
            func.avg(TaskMetric.loss).label('loss'),
            func.avg(TaskMetric.accuracy).label('accuracy'),
            func.avg(TaskMetric.val_loss).label('val_loss'),
            func.avg(TaskMetric.val_accuracy).label('val_accuracy'),
            func.avg(TaskMetric.learning_rate).label('learning_rate'),
            func.avg(TaskMetric.gpu_utilization).label('gpu_utilization'),
            func.avg(TaskMetric.gpu_memory_used).label('gpu_memory_used'),
        )
        .filter(TaskMetric.task_id == task_id, TaskMetric.epoch.isnot(None))
        .group_by(TaskMetric.epoch)
        .order_by(TaskMetric.epoch.asc())
        .all()
    )
    summary = []
    for row in rows:
        summary.append({
            'epoch': row.epoch,
            'loss': round(row.loss, 6) if row.loss is not None else None,
            'accuracy': round(row.accuracy, 6) if row.accuracy is not None else None,
            'val_loss': round(row.val_loss, 6) if row.val_loss is not None else None,
            'val_accuracy': round(row.val_accuracy, 6) if row.val_accuracy is not None else None,
            'learning_rate': row.learning_rate,
            'gpu_utilization': round(row.gpu_utilization, 2) if row.gpu_utilization is not None else None,
            'gpu_memory_used': round(row.gpu_memory_used, 2) if row.gpu_memory_used is not None else None,
        })
    return jsonify({'code': 200, 'data': summary})
