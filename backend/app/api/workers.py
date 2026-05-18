import logging
import socket
import subprocess
import threading
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt
from app import db
from app.models.node_pool import PoolNode, NodePool, WorkerTaskSlot
from app.utils.audit import log_operation, get_current_user_info

logger = logging.getLogger(__name__)
workers_bp = Blueprint('workers', __name__)


def _require_admin():
    if get_jwt().get('role') != 'admin':
        return jsonify({'code': 403, 'message': '需要管理员权限'}), 403
    return None


def _probe_node_reachable(ip_address, port=None, timeout=2):
    """检测节点是否网络可达
    - standalone 节点：优先检测 Agent 端口，确认 Agent 服务真正可用
    - k8s 节点：检测 SSH 端口22
    - 回退到 ICMP ping
    """
    if not ip_address:
        return False
    probe_port = port or 22
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip_address, probe_port))
        sock.close()
        if result == 0:
            return True
    except Exception:
        pass
    if port:
        return False
    try:
        import platform
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
        timeout_val = str(timeout * 1000) if platform.system().lower() == 'windows' else str(timeout)
        ret = subprocess.run(
            ['ping', param, '1', timeout_param, timeout_val, ip_address],
            capture_output=True, timeout=timeout + 1
        )
        return ret.returncode == 0
    except Exception:
        return False


def _check_stale_inline():
    """内联心跳超时检查：每次查询前确保过期节点被标记为离线
    注意：只检查 standalone 节点，K8s 节点状态由集群同步管理"""
    try:
        timeout_seconds = current_app.config.get('WORKER_TIMEOUT', 90)
        cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)
        stale = PoolNode.query.filter(
            PoolNode.status.in_(['idle', 'busy']),
            PoolNode.node_type != 'k8s_node',
            PoolNode.last_heartbeat < cutoff
        ).all()
        if stale:
            for w in stale:
                w.status = 'offline'
                w.status_message = f'心跳超时 (>{timeout_seconds}s)'
                logger.warning(f"Inline stale check: {w.name} ({w.ip_address}) marked offline")
            db.session.commit()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.error(f"Inline stale check error: {e}")


def _probe_and_update_workers(workers):
    """双向并行探活：离线→在线 + 在线→离线
    注意：跳过 k8s_node 类型节点"""
    to_probe = [w for w in workers if w.ip_address and getattr(w, 'node_type', 'standalone') != 'k8s_node']
    if not to_probe:
        return

    results = {}
    def probe(w):
        agent_port = w.port if getattr(w, 'node_type', 'standalone') != 'k8s_node' and w.port else None
        results[w.id] = _probe_node_reachable(w.ip_address, port=agent_port)

    threads = [threading.Thread(target=probe, args=(w,)) for w in to_probe]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    changed = False
    for w in to_probe:
        reachable = results.get(w.id, False)
        if w.status == 'offline' and reachable:
            w.status = 'idle'
            w.status_message = '网络探活恢复在线'
            w.last_heartbeat = datetime.utcnow()
            changed = True
            logger.info(f"Node {w.name} ({w.ip_address}) probed online")
        elif w.status in ('idle', 'busy') and not reachable:
            w.status = 'offline'
            w.status_message = '网络探活不可达'
            changed = True
            logger.warning(f"Node {w.name} ({w.ip_address}) probed offline")

    if changed:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to commit probe results: {e}")


@workers_bp.route('/ping', methods=['POST'])
@jwt_required()
def ping_worker():
    """测试 Agent 节点连通性"""
    err = _require_admin()
    if err:
        return err
    data = request.get_json() or {}
    ip_address = (data.get('ip_address') or '').strip()
    port = data.get('port', 5000)
    
    if not ip_address:
        return jsonify({'code': 400, 'message': 'IP 地址不能为空'}), 400
    
    import socket
    import requests
    result = {'ip': ip_address, 'port': port, 'reachable': False, 'agent_ok': False, 'message': ''}
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((ip_address, int(port)))
        sock.close()
        result['reachable'] = True
    except Exception as e:
        result['message'] = f'端口不可达: {e}'
        return jsonify({'code': 200, 'data': result})
    
    try:
        resp = requests.get(f'http://{ip_address}:{port}/health', timeout=5)
        if resp.status_code == 200:
            result['agent_ok'] = True
            result['message'] = 'Agent 运行正常'
            agent_info = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
            result['agent_info'] = agent_info
        else:
            result['message'] = f'Agent 响应异常: {resp.status_code}'
    except Exception as e:
        result['message'] = f'Agent 连接失败: {e}'
    
    return jsonify({'code': 200, 'data': result})


@workers_bp.route('/agent-download', methods=['GET'])
def download_agent():
    """下载 te_agent.py 脚本文件"""
    from flask import send_file
    import os
    agent_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'agent', 'te_agent.py')
    if os.path.exists(agent_path):
        return send_file(agent_path, as_attachment=True, download_name='te_agent.py')
    return jsonify({'code': 404, 'message': 'Agent 脚本未找到'}), 404


@workers_bp.route('/install-script', methods=['GET'])
@jwt_required()
def get_install_script():
    """获取 Agent 安装脚本"""
    from flask import current_app
    server_host = request.host.split(':')[0]
    server_port = current_app.config.get('SERVER_PORT', 8010)
    
    script = f'''#!/bin/bash
# KubeTrain2 Agent 安装脚本
# 用法: curl -sSL http://{server_host}:{server_port}/api/workers/install-script | bash

set -e

echo "=== KubeTrain2 Agent 安装程序 ==="

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 Python3，请先安装 Python 3.8+"
    exit 1
fi

# 创建目录
INSTALL_DIR="${{HOME}}/kubetrain-agent"
mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install flask requests psutil

# 创建 Agent 脚本
cat > agent.py << 'AGENT_EOF'
import os
import sys
import json
import time
import socket
import psutil
import requests
import subprocess
from flask import Flask, request, jsonify
from threading import Thread

app = Flask(__name__)
SERVER_URL = os.environ.get('KUBETRAIN_SERVER', 'http://{server_host}:{server_port}')
WORKER_ID = None

def get_gpu_info():
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=gpu_name,memory.total,memory.used,utilization.gpu',
                                 '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\\n')
            gpus = []
            for line in lines:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 4:
                    gpus.append({{'name': parts[0], 'memory_total': int(parts[1]), 'memory_used': int(parts[2]), 'utilization': int(parts[3])}})
            return gpus
    except: pass
    return []

@app.route('/health', methods=['GET'])
def health():
    return jsonify({{'status': 'ok', 'worker_id': WORKER_ID, 'hostname': socket.gethostname()}})

@app.route('/info', methods=['GET'])
def info():
    gpus = get_gpu_info()
    return jsonify({{
        'hostname': socket.gethostname(),
        'cpu_count': psutil.cpu_count(),
        'memory_total': psutil.virtual_memory().total,
        'gpu_count': len(gpus),
        'gpus': gpus
    }})

@app.route('/execute', methods=['POST'])
def execute():
    data = request.get_json() or {{}}
    # 执行训练任务逻辑
    return jsonify({{'status': 'accepted'}})

def register():
    global WORKER_ID
    gpus = get_gpu_info()
    data = {{
        'name': socket.gethostname(),
        'ip_address': socket.gethostbyname(socket.gethostname()),
        'port': 5000,
        'gpu_total': len(gpus),
        'gpu_model': gpus[0]['name'] if gpus else 'N/A',
        'cpu_total': psutil.cpu_count(),
        'memory_total': psutil.virtual_memory().total // (1024**3),
        'max_tasks': max(1, len(gpus))
    }}
    try:
        resp = requests.post(f'{{SERVER_URL}}/api/workers/register', json=data, timeout=10)
        if resp.status_code == 200:
            result = resp.json().get('data', {{}})
            WORKER_ID = result.get('worker_id') or result.get('id')
            print(f'注册成功: {{WORKER_ID}}')
    except Exception as e:
        print(f'注册失败: {{e}}')

def heartbeat_loop():
    while True:
        time.sleep(30)
        if WORKER_ID:
            try:
                gpus = get_gpu_info()
                requests.post(f'{{SERVER_URL}}/api/workers/{{WORKER_ID}}/heartbeat', json={{
                    'cpu_percent': psutil.cpu_percent(),
                    'memory_percent': psutil.virtual_memory().percent,
                    'gpu_info': gpus
                }}, timeout=5)
            except: pass

if __name__ == '__main__':
    register()
    Thread(target=heartbeat_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
AGENT_EOF

# 创建 systemd 服务
cat > kubetrain-agent.service << 'SERVICE_EOF'
[Unit]
Description=KubeTrain2 Agent
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
Environment=KUBETRAIN_SERVER=http://{server_host}:{server_port}
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE_EOF

echo "=== 安装完成 ==="
echo "启动 Agent: source $INSTALL_DIR/venv/bin/activate && python $INSTALL_DIR/agent.py"
echo "或安装为服务: sudo cp $INSTALL_DIR/kubetrain-agent.service /etc/systemd/system/ && sudo systemctl enable --now kubetrain-agent"
'''
    return script, 200, {'Content-Type': 'text/plain; charset=utf-8'}


@workers_bp.route('', methods=['GET'])
@jwt_required()
def list_workers():
    try:
        from app.services.worker_registry import worker_registry
        stats = worker_registry.get_worker_stats()
    except Exception:
        stats = {}
    nodes = PoolNode.query.order_by(PoolNode.created_at.desc()).all()
    return jsonify({'code': 200, 'data': {'workers': [n.to_dict() for n in nodes], 'stats': stats}})


@workers_bp.route('/status', methods=['GET'])
@jwt_required()
def workers_status():
    """获取 Worker 状态列表，支持探活"""
    pool_id = request.args.get('pool_id')
    status = request.args.get('status')
    probe = request.args.get('probe', 'false').lower() in ('true', '1', 'yes')

    # 每次查询前先内联检查心跳超时
    _check_stale_inline()

    query = PoolNode.query
    if pool_id:
        query = query.filter_by(pool_id=pool_id)
    if status and not probe:
        query = query.filter_by(status=status)
    workers = query.order_by(PoolNode.name).all()

    # 主动探活
    if probe:
        _probe_and_update_workers(workers)
        query = PoolNode.query
        if pool_id:
            query = query.filter_by(pool_id=pool_id)
        if status:
            query = query.filter_by(status=status)
        workers = query.order_by(PoolNode.name).all()

    return jsonify({'code': 200, 'data': [w.to_dict() for w in workers]})


@workers_bp.route('/stats', methods=['GET'])
@jwt_required()
def worker_stats():
    """获取 Worker 统计信息"""
    from app.services.worker_registry import worker_registry
    stats = worker_registry.get_worker_stats()
    return jsonify({'code': 200, 'data': stats})


@workers_bp.route('/discover', methods=['GET'])
@jwt_required()
def discover_workers():
    """发现在线 Worker，支持按能力过滤"""
    pool_id = request.args.get('pool_id')
    caps = request.args.get('capabilities')
    capabilities = caps.split(',') if caps else None
    from app.services.worker_registry import worker_registry
    workers = worker_registry.get_online_workers(pool_id=pool_id, capabilities=capabilities)
    return jsonify({'code': 200, 'data': [w.to_dict() for w in workers]})


@workers_bp.route('/find-best', methods=['POST'])
@jwt_required()
def find_best_worker():
    """为任务找到最佳 Worker"""
    data = request.get_json() or {}
    from app.services.worker_registry import worker_registry
    worker = worker_registry.find_best_worker(
        cpu_req=data.get('cpu', 0), mem_req=data.get('memory', 0),
        gpu_req=data.get('gpu', 0), required_caps=data.get('capabilities'),
        pool_id=data.get('pool_id')
    )
    if worker:
        return jsonify({'code': 200, 'data': worker.to_dict()})
    return jsonify({'code': 404, 'message': '没有符合条件的 Worker'}), 404


@workers_bp.route('/register', methods=['POST'])
def register_worker():
    """Agent 自注册端点（无需 JWT）"""
    data = request.get_json() or {}
    try:
        from app.services.worker_registry import worker_registry
        ok, msg, result = worker_registry.register(data)
        if ok:
            return jsonify({'code': 200, 'message': msg, 'data': result})
        return jsonify({'code': 400, 'message': msg}), 400
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500


@workers_bp.route('/admin-register', methods=['POST'])
@jwt_required()
def admin_register_worker():
    """管理员手动注册 Agent 节点"""
    err = _require_admin()
    if err:
        return err
    data = request.get_json() or {}

    ip_address = (data.get('ip_address') or '').strip()
    name = (data.get('name') or '').strip()
    if not ip_address:
        return jsonify({'code': 400, 'message': 'IP 地址不能为空'}), 400
    if not name:
        name = ip_address

    try:
        from app.services.worker_registry import worker_registry
        ok, msg, result = worker_registry.register(data)
        if ok:
            user_id, username = get_current_user_info()
            log_operation(
                user_id=user_id, username=username,
                operation_type='register', module='workers',
                action=f'手动注册 Agent 节点: {name}',
                target_type='worker', target_id=result.get('id'), target_name=name,
                detail={'ip_address': ip_address}
            )
            return jsonify({'code': 200, 'message': '节点注册成功', 'data': result})
        return jsonify({'code': 400, 'message': msg}), 400
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500


@workers_bp.route('/<worker_id>', methods=['PUT'])
@jwt_required()
def update_worker(worker_id):
    """更新 Worker 节点信息（名称/最大任务数/GPU等）"""
    err = _require_admin()
    if err:
        return err
    node = PoolNode.query.filter_by(id=worker_id).first()
    if not node:
        node = PoolNode.query.filter_by(worker_id=worker_id).first()
    if not node:
        return jsonify({'code': 404, 'message': 'Worker not found'}), 404
    data = request.get_json() or {}
    if 'name' in data and data['name']:
        node.name = data['name']
    if 'max_tasks' in data:
        node.max_tasks = int(data['max_tasks'])
    if 'gpu_total' in data:
        node.gpu_total = int(data['gpu_total'])
    if 'cpu_total' in data:
        node.cpu_total = int(data['cpu_total'])
    if 'memory_total' in data:
        node.memory_total = int(data['memory_total'])
    if 'gpu_model' in data:
        node.gpu_model = data['gpu_model']
    if 'ip_address' in data and data['ip_address']:
        node.ip_address = data['ip_address']
    if 'port' in data:
        node.port = int(data['port'])
    if 'pool_id' in data and data['pool_id']:
        pool = NodePool.query.get(data['pool_id'])
        if pool:
            node.pool_id = pool.id
    db.session.commit()
    return jsonify({'code': 200, 'message': '更新成功', 'data': node.to_dict()})


@workers_bp.route('/<worker_id>/heartbeat', methods=['POST'])
def worker_heartbeat(worker_id):
    """Agent 心跳（无需 JWT）"""
    data = request.get_json() or {}
    try:
        from app.services.worker_registry import worker_registry
        ok, msg, result = worker_registry.heartbeat(worker_id, data)
        return jsonify({'code': 200, 'message': msg, 'data': result})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500


@workers_bp.route('/<worker_id>', methods=['GET'])
@jwt_required()
def get_worker(worker_id):
    node = PoolNode.query.filter_by(id=worker_id).first()
    if not node:
        node = PoolNode.query.filter_by(worker_id=worker_id).first()
    if not node:
        return jsonify({'code': 404, 'message': 'Worker not found'}), 404
    return jsonify({'code': 200, 'data': node.to_dict()})


@workers_bp.route('/<worker_id>/deregister', methods=['POST'])
@jwt_required()
def deregister_worker(worker_id):
    err = _require_admin()
    if err:
        return err
    node = PoolNode.query.get(worker_id)
    if not node:
        node = PoolNode.query.filter_by(worker_id=worker_id).first()
    if not node:
        return jsonify({'code': 404, 'message': 'Worker not found'}), 404
    node_name = node.name or node.ip_address
    try:
        from app.services.worker_registry import worker_registry
        ok, msg = worker_registry.deregister(node.worker_id or node.id)
        if ok:
            user_id, username = get_current_user_info()
            log_operation(
                user_id=user_id, username=username,
                operation_type='deregister', module='workers',
                action=f'注销 Agent 节点: {node_name}',
                target_type='worker', target_id=worker_id, target_name=node_name
            )
            return jsonify({'code': 200, 'message': msg})
        return jsonify({'code': 404, 'message': msg}), 404
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500
