"""操作日志 API"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from app import db
from app.models.operation_log import OperationLog
from datetime import datetime

operation_logs_bp = Blueprint('operation_logs', __name__)


@operation_logs_bp.route('', methods=['GET'])
@jwt_required()
def list_logs():
    """获取操作日志列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    module = request.args.get('module', '').strip()
    operation_type = request.args.get('operation_type', '').strip()
    user_id = request.args.get('user_id', type=int)
    username = request.args.get('username', '').strip()
    result = request.args.get('result', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    query = OperationLog.query

    if module:
        query = query.filter_by(module=module)
    if operation_type:
        query = query.filter_by(operation_type=operation_type)
    if user_id:
        query = query.filter_by(user_id=user_id)
    if username:
        query = query.filter(OperationLog.username.ilike(f'%{username}%'))
    if result:
        query = query.filter_by(result=result)
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(OperationLog.created_at >= start_dt)
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
            query = query.filter(OperationLog.created_at <= end_dt)
        except ValueError:
            pass

    pagination = query.order_by(OperationLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'code': 200,
        'data': {
            'items': [log.to_dict() for log in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages,
        }
    })


@operation_logs_bp.route('/export', methods=['GET'])
@jwt_required()
def export_logs():
    """导出操作日志（合规报告）"""
    module = request.args.get('module', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    query = OperationLog.query

    if module:
        query = query.filter_by(module=module)
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(OperationLog.created_at >= start_dt)
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
            query = query.filter(OperationLog.created_at <= end_dt)
        except ValueError:
            pass

    logs = query.order_by(OperationLog.created_at.desc()).limit(10000).all()

    # 统计汇总
    summary = {
        'by_module': {},
        'by_type': {},
        'by_result': {'success': 0, 'failure': 0},
    }
    for log in logs:
        summary['by_module'][log.module] = summary['by_module'].get(log.module, 0) + 1
        summary['by_type'][log.operation_type] = summary['by_type'].get(log.operation_type, 0) + 1
        if log.result in summary['by_result']:
            summary['by_result'][log.result] += 1

    report = {
        'title': 'KubeTrain2 操作日志报告',
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'filter': {
            'module': module or '全部',
            'start_date': start_date or '不限',
            'end_date': end_date or '不限',
        },
        'total_operations': len(logs),
        'summary': summary,
        'operations': [log.to_dict() for log in logs],
    }

    return jsonify({'code': 200, 'data': report})


@operation_logs_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_stats():
    """获取日志统计信息"""
    from sqlalchemy import func

    # 模块统计
    module_stats = db.session.query(
        OperationLog.module,
        func.count(OperationLog.id)
    ).group_by(OperationLog.module).all()

    # 操作类型统计
    type_stats = db.session.query(
        OperationLog.operation_type,
        func.count(OperationLog.id)
    ).group_by(OperationLog.operation_type).all()

    # 结果统计
    result_stats = db.session.query(
        OperationLog.result,
        func.count(OperationLog.id)
    ).group_by(OperationLog.result).all()

    return jsonify({
        'code': 200,
        'data': {
            'by_module': {m: c for m, c in module_stats},
            'by_type': {t: c for t, c in type_stats},
            'by_result': {r: c for r, c in result_stats},
        }
    })


@operation_logs_bp.route('/batch-delete', methods=['POST'])
@jwt_required()
def batch_delete():
    """批量删除操作日志（仅管理员）"""
    if get_jwt().get('role') != 'admin':
        return jsonify({'code': 403, 'message': '需要管理员权限'}), 403

    data = request.get_json() or {}
    ids = data.get('ids', [])
    start_date = data.get('start_date', '').strip()
    end_date = data.get('end_date', '').strip()

    deleted = 0
    if ids:
        deleted = OperationLog.query.filter(OperationLog.id.in_(ids)).delete(synchronize_session=False)
    elif start_date and end_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
            deleted = OperationLog.query.filter(
                OperationLog.created_at >= start_dt,
                OperationLog.created_at <= end_dt
            ).delete(synchronize_session=False)
        except ValueError:
            return jsonify({'code': 400, 'message': '日期格式错误'}), 400
    else:
        return jsonify({'code': 400, 'message': '请指定日志ID列表或时间段'}), 400

    db.session.commit()
    return jsonify({'code': 200, 'message': f'已删除 {deleted} 条日志'})
