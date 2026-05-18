import os
import re
import logging
import tempfile
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app import db
from app.models.task import Task
from app.utils.audit import log_operation, get_current_user_info

tasks_bp = Blueprint('tasks', __name__)
logger = logging.getLogger(__name__)


def _get_current_user_id():
    try:
        user_id, _ = get_current_user_info()
        return int(user_id) if user_id else None
    except Exception:
        return None


def _get_current_user_role():
    try:
        return get_jwt().get('role', 'user')
    except Exception:
        return 'user'


def _can_access_task(task):
    role = _get_current_user_role()
    if role == 'admin':
        return True
    user_id = _get_current_user_id()
    if not user_id:
        return True
    return str(task.created_by or '') == str(user_id)


def _write_script_to_nfs(script_path, script_content):
    try:
        import paramiko
        nfs_host = current_app.config.get('SSH_HOST', '192.168.171.3')
        nfs_user = current_app.config.get('SSH_USER', 'root')
        nfs_port = int(current_app.config.get('SSH_PORT', 22))
        nfs_remote_base = current_app.config.get('NFS_REMOTE_BASE', '/data/kubetrain')
        norm = script_path.replace('\\', '/').strip('/')
        match = re.search(r'scripts/(.*)', norm)
        rel = match.group(1) if match else os.path.basename(norm)
        remote_path = f'{nfs_remote_base}/scripts/{rel}'
        remote_parent = os.path.dirname(remote_path)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(nfs_host, port=nfs_port, username=nfs_user, timeout=10)
            client.exec_command(f'mkdir -p {remote_parent}')
            sftp = client.open_sftp()
            try:
                with sftp.file(remote_path, 'w') as f:
                    f.write(script_content.encode('utf-8'))
            finally:
                sftp.close()
        finally:
            client.close()
        nfs_mount = current_app.config.get('NFS_MOUNT_PATH', '/data')
        return f'{nfs_mount}/kubetrain/scripts/{rel}'
    except Exception as e:
        logger.warning(f"Script write to NFS failed: {e}")
        return script_path


def _upload_dataset_to_nfs(local_path):
    if not local_path or local_path.startswith('/data'):
        return local_path
    norm = local_path.replace('\\', '/')
    match = re.search(r'datasets/([^/]+.*)', norm)
    if not match:
        return local_path
    rel_path = match.group(1)
    is_zip = rel_path.lower().endswith('.zip')
    if os.path.isabs(local_path) and (os.path.isfile(local_path) or os.path.isdir(local_path)):
        resolved_local = local_path
    else:
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
        candidate = os.path.join(upload_folder, 'datasets', rel_path)
        resolved_local = candidate if (os.path.isfile(candidate) or os.path.isdir(candidate)) else None
    if not resolved_local:
        return local_path
    try:
        import paramiko
        nfs_host = current_app.config.get('SSH_HOST', '192.168.171.3')
        nfs_user = current_app.config.get('SSH_USER', 'root')
        nfs_port = int(current_app.config.get('SSH_PORT', 22))
        nfs_remote_base = current_app.config.get('NFS_REMOTE_BASE', '/data/kubetrain')
        remote_path = f'{nfs_remote_base}/datasets/{rel_path}'
        remote_parent = os.path.dirname(remote_path)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(nfs_host, port=nfs_port, username=nfs_user, timeout=10)
            client.exec_command(f'mkdir -p {remote_parent}')
            sftp = client.open_sftp()
            try:
                if os.path.isfile(resolved_local):
                    sftp.put(resolved_local, remote_path)
                    if is_zip:
                        extract_dir = remote_path[:-4]
                        cmd = f'rm -rf {extract_dir} && mkdir -p {extract_dir} && unzip -o -q {remote_path} -d {extract_dir}'
                        _, stdout, _ = client.exec_command(cmd)
                        stdout.channel.recv_exit_status()
                        _, stdout_ls, _ = client.exec_command(f'ls -1 {extract_dir} 2>/dev/null')
                        items = [x for x in stdout_ls.read().decode().strip().split('\n') if x]
                        container_rel = rel_path[:-4]
                        if len(items) == 1:
                            _, stdout_chk, _ = client.exec_command(f'test -d {extract_dir}/{items[0]} && echo yes')
                            if stdout_chk.read().decode().strip() == 'yes':
                                container_rel = f'{container_rel}/{items[0]}'
                        container_path = f'/data/datasets/{container_rel}'
                    else:
                        container_path = f'/data/datasets/{rel_path}'
                else:
                    container_path = f'/data/datasets/{rel_path}'
            finally:
                sftp.close()
        finally:
            client.close()
        return container_path
    except Exception as e:
        logger.error(f"SFTP dataset upload failed: {e}")
        return local_path


@tasks_bp.route('', methods=['POST'])
@jwt_required()
def create_task():
    data = request.get_json()
    if not data:
        return jsonify({'code': 400, 'message': 'No data provided'}), 400
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '任务名称不能为空'}), 400

    training_script = data.get('training_script', '').strip()
    script_content = data.get('script_content')
    execution_mode = data.get('execution_mode', 'auto')
    algorithm_version_id = data.get('algorithm_version_id')
    algorithm_id = data.get('algorithm_id')
    model_version_id = data.get('model_version_id')
    base_model_path = data.get('base_model_path')

    # 如果提供了 algorithm_version_id，自动从版本中解析脚本路径和内容
    if algorithm_version_id and not training_script:
        from app.models.algorithm import AlgorithmVersion
        algo_ver = AlgorithmVersion.query.get(algorithm_version_id)
        if algo_ver:
            if algo_ver.script_path:
                training_script = algo_ver.script_path
            if algo_ver.script_content:
                script_content = algo_ver.script_content
            if not algorithm_id:
                algorithm_id = algo_ver.algorithm_id

    # 如果提供了 model_version_id，自动解析模型文件路径
    if model_version_id and not base_model_path:
        from app.models.model import ModelVersion
        model_ver = ModelVersion.query.get(model_version_id)
        if model_ver and model_ver.file_path:
            base_model_path = model_ver.file_path

    # 如果提供了 dataset_version_id，解析数据集路径
    dataset_path = data.get('dataset_path')
    dataset_version_id = data.get('dataset_version_id')
    if dataset_version_id and not dataset_path:
        from app.models.dataset import DatasetVersion
        ds_ver = DatasetVersion.query.get(dataset_version_id)
        if ds_ver and ds_ver.file_path:
            dataset_path = ds_ver.file_path

    if not training_script:
        return jsonify({'code': 400, 'message': '训练脚本路径不能为空（请选择算法版本或手动指定脚本）'}), 400

    if script_content:
        if execution_mode != 'agent':
            training_script = _write_script_to_nfs(training_script, script_content)
        else:
            local_base = current_app.config.get('LOCAL_SCRIPT_DIR', '') or os.path.join(tempfile.gettempdir(), 'te_scripts')
            fname = os.path.basename(training_script) or 'train.py'
            local_dir = os.path.join(local_base, 'scripts')
            try:
                os.makedirs(local_dir, exist_ok=True)
                local_file = os.path.join(local_dir, fname)
                with open(local_file, 'w', encoding='utf-8') as f:
                    f.write(script_content)
                training_script = local_file
            except Exception as e:
                logger.warning(f"Agent mode: local script write failed: {e}")

    if execution_mode != 'agent' and dataset_path and not dataset_path.startswith('/data'):
        dataset_path = _upload_dataset_to_nfs(dataset_path)

    try:
        # Bug 2: 前端 'local_ddp' → 后端/Agent 统一识别为 'ddp' + num_nodes=1
        parallel_mode = data.get('parallel_mode', 'single')
        num_nodes = data.get('num_nodes', 1)
        if parallel_mode == 'local_ddp':
            parallel_mode = 'ddp'
            num_nodes = 1
        elif parallel_mode == 'distributed':
            parallel_mode = 'ddp'

        # 如果 training_args 为空但有算法版本，用算法默认参数填充
        training_args = data.get('training_args')
        if (not training_args or not isinstance(training_args, dict) or len(training_args) == 0) and algorithm_version_id:
            from app.models.algorithm import AlgorithmVersion as AV
            _av = AV.query.get(algorithm_version_id)
            if _av and _av.parameters and isinstance(_av.parameters, list):
                training_args = {}
                for p in _av.parameters:
                    if isinstance(p, dict) and p.get('name') and p.get('default_value') not in (None, ''):
                        training_args[p['name']] = p['default_value']
                if not training_args:
                    training_args = None

        # Bug 3: 从 training_args 提取 total_epochs（如果未显式提供）
        total_epochs = data.get('total_epochs')
        if not total_epochs and training_args and isinstance(training_args, dict):
            for key in ('epochs', 'num_epochs', 'total_epochs'):
                val = training_args.get(key)
                if val:
                    try:
                        total_epochs = int(val)
                    except (ValueError, TypeError):
                        pass
                    break

        # ---- Pipeline support ----
        pipeline_stages = data.get('pipeline_stages')
        if pipeline_stages and isinstance(pipeline_stages, list) and len(pipeline_stages) >= 2:
            return _create_pipeline_task(data, name, execution_mode, parallel_mode, num_nodes,
                                         training_script, script_content, training_args,
                                         total_epochs, algorithm_id, algorithm_version_id,
                                         base_model_path, dataset_path, pipeline_stages)

        task = Task(
            id=str(uuid.uuid4()),
            name=name,
            description=data.get('description', ''),
            status='pending',
            priority=data.get('priority', 5),
            execution_mode=execution_mode,
            parallel_mode=parallel_mode,
            num_nodes=num_nodes,
            gpus_per_node=data.get('gpus_per_node', 1),
            nproc_per_node=data.get('nproc_per_node', 1),
            training_script=training_script,
            training_args=training_args,
            environment=data.get('environment'),
            dataset_id=data.get('dataset_id'),
            algorithm_id=algorithm_id,
            algorithm_version_id=algorithm_version_id,
            base_model_id=data.get('base_model_id'),
            base_model_path=base_model_path,
            dataset_path=dataset_path,
            output_path=data.get('output_path'),
            checkpoint_path=data.get('checkpoint_path'),
            pip_packages=data.get('pip_packages'),
            cpu_request=data.get('cpu_request', '1'),
            cpu_limit=data.get('cpu_limit', '2'),
            memory_request=data.get('memory_request', '2Gi'),
            memory_limit=data.get('memory_limit', '4Gi'),
            gpu_limit=data.get('gpu_limit', 0),
            total_epochs=total_epochs,
            max_retries=data.get('max_retries', 3),
            created_by=_get_current_user_id(),
        )
        db.session.add(task)
        db.session.commit()
        
        user_id, username = get_current_user_info()
        log_operation(
            user_id=user_id, username=username,
            operation_type='create', module='tasks',
            action=f'创建训练任务: {name}',
            target_type='task', target_id=task.id, target_name=name
        )
        return jsonify({'code': 200, 'message': '任务创建成功', 'data': task.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create task: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


def _create_pipeline_task(data, name, execution_mode, parallel_mode, num_nodes,
                          training_script, script_content, training_args,
                          total_epochs, algorithm_id, algorithm_version_id,
                          base_model_path, dataset_path, pipeline_stages):
    """Create a parent pipeline task and child stage tasks."""
    from app.models.algorithm import AlgorithmVersion
    from app.models.model import ModelVersion

    parent_id = str(uuid.uuid4())
    user_id_val = _get_current_user_id()

    # Build pipeline_config for parent
    pipeline_config = {'stages': []}
    stage_progress = []
    for idx, stage in enumerate(pipeline_stages):
        stage_name = stage.get('name', f'阶段{idx + 1}')
        pipeline_config['stages'].append({
            'name': stage_name,
            'algorithm_version_id': stage.get('algorithm_version_id'),
            'model_version_id': stage.get('model_version_id'),
            'config': stage.get('config', {}),
        })
        stage_progress.append({
            'task_id': None,  # filled when child is created
            'status': 'pending',
            'model_path': None,
            'name': stage_name,
        })

    # Compute aggregate total_epochs across all stages
    agg_total_epochs = 0
    for st in pipeline_stages:
        cfg = st.get('config') or {}
        for ek in ('epochs', 'num_epochs', 'total_epochs'):
            if cfg.get(ek):
                try:
                    agg_total_epochs += int(cfg[ek])
                except (ValueError, TypeError):
                    pass
                break

    parent = Task(
        id=parent_id,
        name=name,
        description=data.get('description', ''),
        status='pending',
        priority=data.get('priority', 5),
        execution_mode=execution_mode,
        parallel_mode=parallel_mode,
        num_nodes=num_nodes,
        gpus_per_node=data.get('gpus_per_node', 1),
        nproc_per_node=data.get('nproc_per_node', 1),
        training_script=training_script,
        training_args=training_args,
        environment=data.get('environment'),
        dataset_id=data.get('dataset_id'),
        algorithm_id=algorithm_id,
        algorithm_version_id=algorithm_version_id,
        base_model_path=base_model_path,
        dataset_path=dataset_path,
        pip_packages=data.get('pip_packages'),
        cpu_request=data.get('cpu_request', '1'),
        cpu_limit=data.get('cpu_limit', '2'),
        memory_request=data.get('memory_request', '2Gi'),
        memory_limit=data.get('memory_limit', '4Gi'),
        gpu_limit=data.get('gpu_limit', 0),
        total_epochs=agg_total_epochs or None,
        max_retries=data.get('max_retries', 3),
        created_by=user_id_val,
        pipeline_config=pipeline_config,
        pipeline_progress={'current_stage': -1, 'stages': stage_progress},
    )
    db.session.add(parent)

    # Create child tasks for each stage
    for idx, stage in enumerate(pipeline_stages):
        stage_cfg = stage.get('config') or {}
        stage_algo_vid = stage.get('algorithm_version_id')
        stage_model_vid = stage.get('model_version_id')

        # Resolve algorithm version for this stage
        child_script = training_script
        child_script_content = script_content
        child_algo_id = algorithm_id
        if stage_algo_vid:
            algo_ver = AlgorithmVersion.query.get(stage_algo_vid)
            if algo_ver:
                if algo_ver.script_path:
                    child_script = algo_ver.script_path
                if algo_ver.script_content:
                    child_script_content = algo_ver.script_content
                child_algo_id = algo_ver.algorithm_id

        # Resolve model version for this stage (stage 0 uses base_model; later stages inherit from previous)
        child_base_model_path = base_model_path if idx == 0 else None
        if stage_model_vid:
            model_ver = ModelVersion.query.get(stage_model_vid)
            if model_ver and model_ver.file_path:
                child_base_model_path = model_ver.file_path

        # Merge parent training_args with stage-specific config
        child_args = dict(training_args) if training_args else {}
        child_args.update(stage_cfg)

        # Extract total_epochs for this stage
        stage_total = None
        for ek in ('epochs', 'num_epochs', 'total_epochs'):
            if stage_cfg.get(ek):
                try:
                    stage_total = int(stage_cfg[ek])
                except (ValueError, TypeError):
                    pass
                break

        child_id = str(uuid.uuid4())
        child = Task(
            id=child_id,
            name=f"{name} - {stage.get('name', f'阶段{idx + 1}')}",
            description=f"流水线阶段 {idx + 1}/{len(pipeline_stages)}",
            status='pending',
            priority=data.get('priority', 5),
            execution_mode=execution_mode,
            parallel_mode=parallel_mode,
            num_nodes=num_nodes,
            gpus_per_node=data.get('gpus_per_node', 1),
            nproc_per_node=data.get('nproc_per_node', 1),
            training_script=child_script,
            training_args=child_args,
            environment=data.get('environment'),
            dataset_id=data.get('dataset_id'),
            algorithm_id=child_algo_id,
            algorithm_version_id=stage_algo_vid or algorithm_version_id,
            base_model_path=child_base_model_path,
            dataset_path=dataset_path,
            pip_packages=data.get('pip_packages'),
            cpu_request=data.get('cpu_request', '1'),
            cpu_limit=data.get('cpu_limit', '2'),
            memory_request=data.get('memory_request', '2Gi'),
            memory_limit=data.get('memory_limit', '4Gi'),
            gpu_limit=data.get('gpu_limit', 0),
            total_epochs=stage_total,
            max_retries=data.get('max_retries', 3),
            created_by=user_id_val,
            parent_task_id=parent_id,
            stage_index=idx,
        )

        # Write script content for this stage if needed
        if child_script_content and execution_mode == 'agent':
            local_base = current_app.config.get('LOCAL_SCRIPT_DIR', '') or os.path.join(tempfile.gettempdir(), 'te_scripts')
            fname = os.path.basename(child_script) or 'train.py'
            local_dir = os.path.join(local_base, 'scripts', child_id[:8])
            try:
                os.makedirs(local_dir, exist_ok=True)
                local_file = os.path.join(local_dir, fname)
                with open(local_file, 'w', encoding='utf-8') as f:
                    f.write(child_script_content)
                child.training_script = local_file
            except Exception as e:
                logger.warning(f"Pipeline stage {idx}: local script write failed: {e}")

        db.session.add(child)
        stage_progress[idx]['task_id'] = child_id

    # Update pipeline_progress with child task IDs
    parent.pipeline_progress = {'current_stage': -1, 'stages': stage_progress}
    db.session.commit()

    user_id_audit, username_audit = get_current_user_info()
    log_operation(
        user_id=user_id_audit, username=username_audit,
        operation_type='create', module='tasks',
        action=f'创建流水线训练任务: {name} ({len(pipeline_stages)}阶段)',
        target_type='task', target_id=parent.id, target_name=name
    )
    return jsonify({'code': 200, 'message': f'流水线任务创建成功 ({len(pipeline_stages)}阶段)', 'data': parent.to_dict()}), 201


@tasks_bp.route('', methods=['GET'])
@jwt_required()
def list_tasks():
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(100, max(1, request.args.get('per_page', 20, type=int)))
    status = request.args.get('status')
    search = request.args.get('search', '').strip()
    execution_mode = request.args.get('execution_mode')

    query = Task.query.filter(Task.parent_task_id.is_(None))  # Hide child stage tasks from main list
    role = _get_current_user_role()
    user_id = _get_current_user_id()
    if role != 'admin' and user_id:
        query = query.filter(Task.created_by == user_id)
    if status:
        query = query.filter(Task.status == status)
    if execution_mode:
        query = query.filter(Task.execution_mode == execution_mode)
    if search:
        query = query.filter(Task.name.ilike(f'%{search}%'))

    pagination = query.order_by(Task.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'code': 200,
        'data': {
            'items': [t.to_dict() for t in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    })


@tasks_bp.route('/stats', methods=['GET'])
@jwt_required()
def task_stats():
    """获取任务状态统计"""
    from sqlalchemy import func
    query = Task.query
    role = _get_current_user_role()
    user_id = _get_current_user_id()
    if role != 'admin' and user_id:
        query = query.filter(Task.created_by == user_id)

    counts = query.with_entities(Task.status, func.count(Task.id)).group_by(Task.status).all()
    stats = {s: c for s, c in counts}
    total = sum(stats.values())
    return jsonify({
        'code': 200,
        'data': {
            'total': total,
            'running': stats.get('running', 0),
            'pending': stats.get('pending', 0),
            'completed': stats.get('completed', 0),
            'failed': stats.get('failed', 0),
            'cancelled': stats.get('cancelled', 0),
            'queued': stats.get('queued', 0),
        }
    })


@tasks_bp.route('/<task_id>', methods=['GET'])
@jwt_required()
def get_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': '任务不存在'}), 404
    if not _can_access_task(task):
        return jsonify({'code': 403, 'message': '无权访问'}), 403
    return jsonify({'code': 200, 'data': task.to_dict()})


@tasks_bp.route('/<task_id>/stages', methods=['GET'])
@jwt_required()
def get_pipeline_stages(task_id):
    """Get child stage tasks for a pipeline parent task."""
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': '任务不存在'}), 404
    if not _can_access_task(task):
        return jsonify({'code': 403, 'message': '无权访问'}), 403
    children = Task.query.filter_by(parent_task_id=task_id).order_by(Task.stage_index).all()
    return jsonify({
        'code': 200,
        'data': [c.to_dict() for c in children]
    })


@tasks_bp.route('/<task_id>', methods=['PUT'])
@jwt_required()
def update_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': '任务不存在'}), 404
    if not _can_access_task(task):
        return jsonify({'code': 403, 'message': '无权访问'}), 403
    if task.status != 'pending':
        return jsonify({'code': 400, 'message': '只有 pending 状态的任务可以修改'}), 400
    data = request.get_json() or {}
    updatable = ['name', 'description', 'priority', 'parallel_mode', 'num_nodes',
                 'gpus_per_node', 'nproc_per_node', 'training_script', 'training_args',
                 'environment', 'dataset_id', 'algorithm_id', 'algorithm_version_id',
                 'base_model_id', 'base_model_path', 'dataset_path', 'output_path',
                 'checkpoint_path', 'pip_packages', 'cpu_request', 'cpu_limit',
                 'memory_request', 'memory_limit', 'gpu_limit', 'total_epochs', 'max_retries']
    for field in updatable:
        if field in data:
            setattr(task, field, data[field])
    try:
        db.session.commit()
        return jsonify({'code': 200, 'message': '任务更新成功', 'data': task.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'message': str(e)}), 500


@tasks_bp.route('/<task_id>', methods=['DELETE'])
@jwt_required()
def delete_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': '任务不存在'}), 404
    if not _can_access_task(task):
        return jsonify({'code': 403, 'message': '无权访问'}), 403
    if task.status in ('running', 'starting', 'queued', 'assigned'):
        return jsonify({'code': 400, 'message': '不能删除运行中的任务'}), 400
    try:
        task_name = task.name
        db.session.delete(task)
        db.session.commit()
        
        user_id, username = get_current_user_info()
        log_operation(
            user_id=user_id, username=username,
            operation_type='delete', module='tasks',
            action=f'删除训练任务: {task_name}',
            target_type='task', target_id=task_id, target_name=task_name
        )
        return jsonify({'code': 200, 'message': '任务删除成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'message': str(e)}), 500


@tasks_bp.route('/<task_id>/submit', methods=['POST'])
@jwt_required()
def submit_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': '任务不存在'}), 404
    if not _can_access_task(task):
        return jsonify({'code': 403, 'message': '无权访问'}), 403
    try:
        from app.services.task_scheduler import task_scheduler

        # Pipeline task: start the first stage
        if task.pipeline_config and task.pipeline_config.get('stages'):
            success, message = task_scheduler.submit_pipeline(task)
        else:
            success, message = task_scheduler.submit_task(task)
        if success:
            user_id, username = get_current_user_info()
            log_operation(
                user_id=user_id, username=username,
                operation_type='submit', module='tasks',
                action=f'提交训练任务: {task.name}',
                target_type='task', target_id=task_id, target_name=task.name
            )
            return jsonify({'code': 200, 'message': message, 'data': task.to_dict()})
        return jsonify({'code': 400, 'message': message}), 400
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500


@tasks_bp.route('/<task_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': '任务不存在'}), 404
    if not _can_access_task(task):
        return jsonify({'code': 403, 'message': '无权访问'}), 403
    try:
        from app.services.task_scheduler import task_scheduler

        # Pipeline cancellation: cancel all active child tasks too
        if task.pipeline_config and task.pipeline_config.get('stages'):
            children = Task.query.filter_by(parent_task_id=task_id).all()
            for child in children:
                if child.status in ('running', 'queued', 'starting', 'assigned', 'pending'):
                    task_scheduler.cancel_task(child.id)
            # Cancel the parent itself
            task.status = 'cancelled'
            task.error_message = '用户取消流水线'
            task.completed_at = datetime.utcnow()
            if task.started_at:
                task.duration = int((task.completed_at - task.started_at).total_seconds())
            db.session.commit()
            from app.websocket.handlers import broadcast_status
            broadcast_status(task.id, 'cancelled', '流水线已取消')
            success, message = True, '流水线已取消'
        else:
            success, message = task_scheduler.cancel_task(task.id)

        if success:
            user_id, username = get_current_user_info()
            log_operation(
                user_id=user_id, username=username,
                operation_type='cancel', module='tasks',
                action=f'取消训练任务: {task.name}',
                target_type='task', target_id=task_id, target_name=task.name
            )
            return jsonify({'code': 200, 'message': message, 'data': task.to_dict()})
        return jsonify({'code': 400, 'message': message}), 400
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500


@tasks_bp.route('/<task_id>/retry', methods=['POST'])
@jwt_required()
def retry_task(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': '任务不存在'}), 404
    if not _can_access_task(task):
        return jsonify({'code': 403, 'message': '无权访问'}), 403
    try:
        from app.services.task_scheduler import task_scheduler
        success, message = task_scheduler.retry_task(task)
        if success:
            return jsonify({'code': 200, 'message': message, 'data': task.to_dict()})
        return jsonify({'code': 400, 'message': message}), 400
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500


@tasks_bp.route('/<task_id>/collect-logs', methods=['POST'])
@jwt_required()
def collect_logs(task_id):
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': '任务不存在'}), 404
    try:
        from app.services.log_collector import log_collector
        log_collector.final_collect_task_logs(task)
        return jsonify({'code': 200, 'message': '日志采集已触发'})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e)}), 500


@tasks_bp.route('/<task_id>/resource-stats', methods=['GET'])
@jwt_required()
def get_resource_stats(task_id):
    """获取任务资源使用统计"""
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': '任务不存在'}), 404
    if not _can_access_task(task):
        return jsonify({'code': 403, 'message': '无权访问'}), 403
    
    from app.models.metric import TaskMetric
    metrics = TaskMetric.query.filter_by(task_id=task_id).order_by(TaskMetric.timestamp.desc()).limit(100).all()
    
    gpu_history = []
    for m in reversed(metrics):
        gpu_history.append({
            'time': m.timestamp.strftime('%H:%M:%S') if m.timestamp else '',
            'gpu_util': m.gpu_utilization or 0,
            'memory_percent': m.gpu_memory_used or 0
        })
    
    latest_m = metrics[0] if metrics else None
    return jsonify({
        'code': 200,
        'data': {
            'gpu_used': task.gpus_per_node or 0,
            'gpu_total': task.gpus_per_node or 0,
            'cpu_percent': latest_m.cpu_utilization if latest_m else 0,
            'memory_used': latest_m.memory_used if latest_m else 0,
            'memory_total': 0,
            'gpu_memory_used': latest_m.gpu_memory_used if latest_m else 0,
            'gpu_memory_total': 0,
            'gpu_history': gpu_history
        }
    })


@tasks_bp.route('/<task_id>/clone', methods=['POST'])
@jwt_required()
def clone_task(task_id):
    """克隆任务"""
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': '任务不存在'}), 404
    if not _can_access_task(task):
        return jsonify({'code': 403, 'message': '无权访问'}), 403
    
    try:
        new_task = Task(
            id=str(uuid.uuid4()),
            name=f"{task.name} (副本)",
            description=task.description,
            status='pending',
            priority=task.priority,
            execution_mode=task.execution_mode,
            parallel_mode=task.parallel_mode,
            num_nodes=task.num_nodes,
            gpus_per_node=task.gpus_per_node,
            nproc_per_node=task.nproc_per_node,
            training_script=task.training_script,
            training_args=task.training_args,
            environment=task.environment,
            dataset_id=task.dataset_id,
            algorithm_id=task.algorithm_id,
            algorithm_version_id=task.algorithm_version_id,
            base_model_id=task.base_model_id,
            base_model_path=task.base_model_path,
            dataset_path=task.dataset_path,
            output_path=task.output_path,
            checkpoint_path=task.checkpoint_path,
            pip_packages=task.pip_packages,
            cpu_request=task.cpu_request,
            cpu_limit=task.cpu_limit,
            memory_request=task.memory_request,
            memory_limit=task.memory_limit,
            gpu_limit=task.gpu_limit,
            total_epochs=task.total_epochs,
            max_retries=task.max_retries,
            created_by=_get_current_user_id(),
        )
        db.session.add(new_task)
        db.session.commit()
        
        user_id, username = get_current_user_info()
        log_operation(
            user_id=user_id, username=username,
            operation_type='clone', module='tasks',
            action=f'克隆训练任务: {task.name} -> {new_task.name}',
            target_type='task', target_id=new_task.id, target_name=new_task.name
        )
        return jsonify({'code': 200, 'message': '任务克隆成功', 'data': new_task.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 500, 'message': str(e)}), 500


@tasks_bp.route('/<task_id>/results/files', methods=['GET'])
@jwt_required()
def list_result_files(task_id):
    """列出任务的训练结果文件（模型、检查点、日志、指标等）"""
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': '任务不存在'}), 404
    if not _can_access_task(task):
        return jsonify({'code': 403, 'message': '无权访问'}), 403

    model_only = request.args.get('model_only', '').lower() == 'true'
    output_path = task.output_path
    if not output_path or not os.path.isdir(output_path):
        return jsonify({'code': 200, 'data': {'files': [], 'output_path': output_path}})

    files = []
    model_exts = {'.pt', '.pth', '.pkl', '.bin', '.onnx', '.safetensors', '.h5', '.pb'}
    checkpoint_exts = {'.ckpt'}
    log_exts = {'.log', '.txt'}
    metric_exts = {'.csv', '.json', '.jsonl'}

    for root, dirs, filenames in os.walk(output_path):
        for fname in filenames:
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, output_path).replace('\\', '/')
            ext = os.path.splitext(fname)[1].lower()
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0

            if ext in model_exts:
                ftype = 'model'
            elif ext in checkpoint_exts or 'checkpoint' in rel.lower():
                ftype = 'checkpoint'
            elif ext in log_exts or 'log' in rel.lower():
                ftype = 'log'
            elif ext in metric_exts or 'metric' in rel.lower():
                ftype = 'metric'
            else:
                ftype = 'other'

            if model_only and ftype != 'model':
                continue

            files.append({
                'name': rel,
                'type': ftype,
                'size': size,
                'size_human': _human_size(size),
            })

    files.sort(key=lambda f: ('model', 'checkpoint', 'metric', 'log', 'other').index(f['type']))
    return jsonify({'code': 200, 'data': {'files': files, 'output_path': output_path}})


def _human_size(size):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024:
            return f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} TB'


@tasks_bp.route('/<task_id>/results/download/<path:filename>', methods=['GET'])
@jwt_required()
def download_result_file(task_id, filename):
    """下载单个结果文件"""
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': '任务不存在'}), 404
    if not _can_access_task(task):
        return jsonify({'code': 403, 'message': '无权访问'}), 403

    output_path = task.output_path
    if not output_path:
        return jsonify({'code': 404, 'message': '无输出路径'}), 404

    file_path = os.path.normpath(os.path.join(output_path, filename))
    # 安全检查：防止路径穿越
    if not file_path.startswith(os.path.normpath(output_path)):
        return jsonify({'code': 403, 'message': '非法路径'}), 403
    if not os.path.isfile(file_path):
        return jsonify({'code': 404, 'message': '文件不存在'}), 404

    from flask import send_file
    return send_file(file_path, as_attachment=True, download_name=os.path.basename(file_path))


@tasks_bp.route('/<task_id>/results/download-all', methods=['GET'])
@jwt_required()
def download_all_results(task_id):
    """打包下载所有结果文件"""
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': '任务不存在'}), 404
    if not _can_access_task(task):
        return jsonify({'code': 403, 'message': '无权访问'}), 403

    output_path = task.output_path
    if not output_path or not os.path.isdir(output_path):
        return jsonify({'code': 404, 'message': '无输出目录'}), 404

    import zipfile, io
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(output_path):
            for fname in files:
                full = os.path.join(root, fname)
                arcname = os.path.relpath(full, output_path)
                try:
                    zf.write(full, arcname)
                except Exception:
                    pass
    mem.seek(0)

    from flask import send_file
    zip_name = f'task_{task_id[:8]}_results.zip'
    return send_file(mem, mimetype='application/zip', as_attachment=True, download_name=zip_name)


@tasks_bp.route('/<task_id>/agent-callback', methods=['POST'])
def agent_callback(task_id):
    """Agent 训练进度回调（无需 JWT）"""
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'code': 404, 'message': 'Task not found'}), 404

    data = request.get_json() or {}
    status = data.get('status')
    # Agent 发送 error_message（非 message），兼容两种字段名
    message_text = data.get('error_message') or data.get('message', '')
    metrics = data.get('metrics') or {}
    logs = data.get('logs') or []
    # Agent _callback_progress 将 epoch 信息放在顶层而非 metrics 内
    current_epoch = data.get('current_epoch')
    total_epochs = data.get('total_epochs')
    progress_percent = data.get('progress_percent')
    # FIX-4: Agent completed 回调携带 output_path/model_path（顶层字段）
    output_path = data.get('output_path')
    model_path = data.get('model_path')

    try:
        from app.services.task_scheduler import task_scheduler
        task_scheduler.handle_agent_callback(
            task, status, message_text, metrics, logs,
            current_epoch=current_epoch, total_epochs=total_epochs,
            progress_percent=progress_percent,
            output_path=output_path, model_path=model_path
        )
        return jsonify({'code': 200, 'message': 'OK'})
    except Exception as e:
        logger.error(f"Agent callback error: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500
