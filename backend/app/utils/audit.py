"""审计日志工具函数"""
from flask import request, current_app
from app import db


def log_operation(user_id=None, username=None, operation_type='', module='',
                  action='', target_type=None, target_id=None, target_name=None,
                  detail=None, result='success', error_message=None):
    """
    记录操作日志
    
    Args:
        user_id: 用户ID
        username: 用户名
        operation_type: 操作类型 (create/update/delete/login/logout/submit/cancel/register/deregister)
        module: 模块名 (auth/users/datasets/algorithms/models/tasks/workers/alerts/clusters/node_pools)
        action: 操作描述
        target_type: 目标类型 (dataset/algorithm/model/task/user/worker/cluster/node_pool/alert)
        target_id: 目标ID
        target_name: 目标名称
        detail: 详细信息（字典）
        result: 结果 (success/failure)
        error_message: 错误信息
    """
    try:
        from app.models.operation_log import OperationLog
        
        ip_address = None
        user_agent = None
        
        # 尝试从请求上下文获取IP和UA
        try:
            ip_address = request.remote_addr
            user_agent = request.headers.get('User-Agent', '')[:500]
        except RuntimeError:
            # 不在请求上下文中
            pass
        
        log = OperationLog(
            user_id=user_id,
            username=username,
            operation_type=operation_type,
            module=module,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            target_name=target_name,
            detail=detail,
            ip_address=ip_address,
            user_agent=user_agent,
            result=result,
            error_message=error_message,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        # 日志记录失败不应影响主业务
        try:
            current_app.logger.error(f"Failed to log operation: {e}")
        except:
            pass


def get_current_user_info():
    """从JWT获取当前用户信息"""
    try:
        from flask_jwt_extended import get_jwt_identity, get_jwt
        user_id = get_jwt_identity()
        claims = get_jwt()
        username = claims.get('username', str(user_id))
        return int(user_id) if user_id else None, username
    except:
        return None, None
