from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app.models.log import TaskLog
from app.models.task import Task

logs_bp = Blueprint('logs', __name__)


@logs_bp.route('/tasks/<task_id>', methods=['GET'])
@jwt_required()
def get_task_logs(task_id):
    task = Task.query.get_or_404(task_id)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 200, type=int)
    level = request.args.get('level')
    since_id = request.args.get('since_id', 0, type=int)

    query = TaskLog.query.filter_by(task_id=task_id)
    if level:
        query = query.filter_by(level=level)
    if since_id:
        query = query.filter(TaskLog.id > since_id)

    query = query.order_by(TaskLog.timestamp.asc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'code': 200,
        'data': {
            'items': [log.to_dict() for log in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'last_id': pagination.items[-1].id if pagination.items else since_id,
        }
    })
