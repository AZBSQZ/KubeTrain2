"""
WebSocket 事件处理器
使用 /training 命名空间
"""
import logging
from flask_socketio import emit, join_room, leave_room

logger = logging.getLogger(__name__)


def register_handlers(socketio):
    """注册训练执行模块的 WebSocket 事件处理器"""

    @socketio.on('connect', namespace='/training')
    def handle_connect():
        logger.debug("Client connected to /training")
        emit('connected', {'status': 'connected'})

    @socketio.on('disconnect', namespace='/training')
    def handle_disconnect():
        logger.debug("Client disconnected from /training")

    @socketio.on('subscribe', namespace='/training')
    def handle_subscribe(data):
        task_id = data.get('task_id')
        if task_id:
            room = f'task_{task_id}'
            join_room(room)
            logger.debug(f"Client subscribed to {room}")
            emit('subscribed', {'task_id': task_id, 'status': 'subscribed'})

    @socketio.on('unsubscribe', namespace='/training')
    def handle_unsubscribe(data):
        task_id = data.get('task_id')
        if task_id:
            room = f'task_{task_id}'
            leave_room(room)
            logger.debug(f"Client unsubscribed from {room}")
            emit('unsubscribed', {'task_id': task_id, 'status': 'unsubscribed'})


def broadcast_log(task_id: str, log_data: dict):
    from app import socketio
    try:
        socketio.emit('log', log_data, room=f'task_{task_id}', namespace='/training')
    except Exception as e:
        logger.debug(f"Failed to broadcast log: {e}")


def broadcast_metric(task_id: str, metric_data: dict):
    from app import socketio
    try:
        socketio.emit('metric', metric_data, room=f'task_{task_id}', namespace='/training')
    except Exception as e:
        logger.debug(f"Failed to broadcast metric: {e}")


def broadcast_status(task_id: str, status: str, message: str = None):
    from app import socketio
    from datetime import datetime
    try:
        socketio.emit('status', {
            'task_id': task_id, 'status': status, 'message': message,
            'timestamp': datetime.utcnow().isoformat()
        }, room=f'task_{task_id}', namespace='/training')
    except Exception as e:
        logger.debug(f"Failed to broadcast status: {e}")


def broadcast_progress(task_id: str, progress: float, current_epoch: int, total_epochs: int = None):
    from app import socketio
    try:
        socketio.emit('progress', {
            'task_id': task_id, 'progress': progress,
            'current_epoch': current_epoch, 'total_epochs': total_epochs
        }, room=f'task_{task_id}', namespace='/training')
    except Exception as e:
        logger.debug(f"Failed to broadcast progress: {e}")


def broadcast_alert(alert_data: dict):
    from app import socketio
    from datetime import datetime
    try:
        socketio.emit('alert', {
            'alert': alert_data, 'timestamp': datetime.utcnow().isoformat()
        }, room='alerts', namespace='/training')
        if alert_data.get('task_id'):
            socketio.emit('alert', {
                'alert': alert_data, 'timestamp': datetime.utcnow().isoformat()
            }, room=f"task_{alert_data['task_id']}", namespace='/training')
    except Exception as e:
        logger.debug(f"Failed to broadcast alert: {e}")
