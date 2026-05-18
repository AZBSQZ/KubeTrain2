from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app import db
from app.models.alert import Alert, AlertRule

alerts_bp = Blueprint('alerts', __name__)


@alerts_bp.route('', methods=['GET'])
@jwt_required()
def list_alerts():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    status = request.args.get('status')
    level = request.args.get('level')
    alert_type = request.args.get('alert_type')

    query = Alert.query
    if status:
        query = query.filter_by(status=status)
    if level:
        query = query.filter_by(level=level)
    if alert_type:
        query = query.filter_by(alert_type=alert_type)

    pagination = query.order_by(Alert.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'code': 200,
        'data': {
            'items': [a.to_dict() for a in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
        }
    })


@alerts_bp.route('/active/count', methods=['GET'])
@jwt_required()
def active_count():
    count = Alert.query.filter_by(status='active').count()
    return jsonify({'code': 200, 'data': {'count': count}})


@alerts_bp.route('/<int:alert_id>/acknowledge', methods=['POST'])
@jwt_required()
def acknowledge(alert_id):
    from datetime import datetime
    alert = Alert.query.get_or_404(alert_id)
    claims = get_jwt()
    alert.status = 'acknowledged'
    alert.acknowledged_by = claims.get('username', str(get_jwt_identity()))
    alert.acknowledged_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'code': 200, 'message': '告警已确认', 'data': alert.to_dict()})


@alerts_bp.route('/<int:alert_id>/resolve', methods=['POST'])
@jwt_required()
def resolve(alert_id):
    from datetime import datetime
    alert = Alert.query.get_or_404(alert_id)
    data = request.get_json() or {}
    claims = get_jwt()
    alert.status = 'resolved'
    alert.resolved_by = claims.get('username', str(get_jwt_identity()))
    alert.resolved_at = datetime.utcnow()
    alert.resolution_note = data.get('note', '')
    db.session.commit()
    return jsonify({'code': 200, 'message': '告警已解决', 'data': alert.to_dict()})


@alerts_bp.route('/rules', methods=['GET'])
@jwt_required()
def list_rules():
    rules = AlertRule.query.order_by(AlertRule.created_at.desc()).all()
    return jsonify({'code': 200, 'data': [r.to_dict() for r in rules]})


@alerts_bp.route('/rules', methods=['POST'])
@jwt_required()
def create_rule():
    if get_jwt().get('role') != 'admin':
        return jsonify({'code': 403, 'message': '需要管理员权限'}), 403
    data = request.get_json() or {}
    rule = AlertRule(
        name=data.get('name', ''),
        description=data.get('description', ''),
        alert_type=data.get('alert_type', ''),
        level=data.get('level', 'warning'),
        is_enabled=data.get('is_enabled', True),
        condition=data.get('condition', {}),
        actions=data.get('actions'),
        cooldown_seconds=data.get('cooldown_seconds', 300),
    )
    db.session.add(rule)
    db.session.commit()
    return jsonify({'code': 200, 'message': '规则创建成功', 'data': rule.to_dict()})


@alerts_bp.route('/rules/<int:rule_id>', methods=['PUT'])
@jwt_required()
def update_rule(rule_id):
    if get_jwt().get('role') != 'admin':
        return jsonify({'code': 403, 'message': '需要管理员权限'}), 403
    rule = AlertRule.query.get_or_404(rule_id)
    data = request.get_json() or {}
    for field in ('name', 'description', 'alert_type', 'level', 'is_enabled', 'condition', 'actions', 'cooldown_seconds'):
        if field in data:
            setattr(rule, field, data[field])
    db.session.commit()
    return jsonify({'code': 200, 'message': '更新成功', 'data': rule.to_dict()})


@alerts_bp.route('/rules/<int:rule_id>', methods=['DELETE'])
@jwt_required()
def delete_rule(rule_id):
    if get_jwt().get('role') != 'admin':
        return jsonify({'code': 403, 'message': '需要管理员权限'}), 403
    rule = AlertRule.query.get_or_404(rule_id)
    db.session.delete(rule)
    db.session.commit()
    return jsonify({'code': 200, 'message': '删除成功'})
