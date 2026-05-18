"""
Kubernetes Job 执行器 - 从KubeTrain迁入并适配FT-taitp
支持 PyTorch DDP/FSDP 分布式训练
配置项统一使用 TE_ 前缀
"""
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from flask import current_app
from kubernetes import client
from kubernetes.client.rest import ApiException

from app import db
from app.models.task import Task, TaskStatus, ParallelMode
from app.services.k8s_client import (
    get_batch_api, get_core_api,
    get_batch_api_for_cluster, get_core_api_for_cluster,
    get_first_connected_cluster, is_k8s_available
)

logger = logging.getLogger(__name__)


def _normalize_api_server(api_server: str) -> str:
    """将用户输入的 api_server 标准化为 https://<host>:<port> 格式
    K8s API Server 均使用 HTTPS，默认端口 6443"""
    s = api_server.strip().rstrip('/')
    # 去掉 http:// 前缀（K8s API 必须 HTTPS）
    if s.startswith('http://'):
        s = s[len('http://'):]
    if s.startswith('https://'):
        s = s[len('https://'):]
    # 补默认端口
    if ':' not in s:
        s = f'{s}:6443'
    return f'https://{s}'


class TEK8sJobExecutor:
    """K8s Job 执行器 - 创建和管理分布式训练 Job"""

    def __init__(self):
        self.namespace = None
        self.nfs_pvc_name = None
        self.training_image = None

    def _load_config(self):
        self.namespace = current_app.config.get('K8S_NAMESPACE', 'kubetrain')
        self.nfs_pvc_name = current_app.config.get('NFS_PVC_NAME', 'kubetrain-data-pvc')
        self.training_image = current_app.config.get('TRAINING_IMAGE', 'kubetrain/pytorch-ddp:latest')
        self.image_pull_policy = current_app.config.get('IMAGE_PULL_POLICY', 'IfNotPresent')
        self.ddp_backend = current_app.config.get('DDP_BACKEND', 'gloo')
        self.ddp_master_port = current_app.config.get('DDP_MASTER_PORT', 29500)

    def _ensure_cluster_namespace(self):
        """确保 self.namespace 与注册集群的 namespace 一致"""
        cluster = get_first_connected_cluster()
        if cluster and cluster.namespace:
            self.namespace = cluster.namespace

    def _get_batch_api(self, task=None):
        """获取 batch API，优先使用任务关联的集群，其次默认配置，最后动态注册的集群"""
        # 1. 如果任务指定了集群
        if task and hasattr(task, 'execution_mode'):
            from app.models.k8s_cluster import K8sCluster
            if hasattr(task, 'assigned_worker_id') and task.assigned_worker_id:
                from app.models.node_pool import PoolNode
                node = PoolNode.query.get(task.assigned_worker_id)
                if node and node.cluster_id:
                    cluster = K8sCluster.query.get(node.cluster_id)
                    if cluster:
                        self.namespace = cluster.namespace or self.namespace
                        return get_batch_api_for_cluster(cluster)

        # 2. 尝试默认配置
        try:
            api = get_batch_api()
            # get_batch_api() 可能使用注册集群的 kubeconfig，同步其 namespace
            self._ensure_cluster_namespace()
            return api
        except Exception:
            pass

        # 3. 尝试动态注册的集群
        cluster = get_first_connected_cluster()
        if cluster:
            self.namespace = cluster.namespace or self.namespace
            return get_batch_api_for_cluster(cluster)

        raise RuntimeError("No K8s cluster available")

    def _get_core_api(self, task=None):
        """获取 core API，逻辑同 _get_batch_api"""
        if task and hasattr(task, 'assigned_worker_id') and task.assigned_worker_id:
            from app.models.k8s_cluster import K8sCluster
            from app.models.node_pool import PoolNode
            node = PoolNode.query.get(task.assigned_worker_id)
            if node and node.cluster_id:
                cluster = K8sCluster.query.get(node.cluster_id)
                if cluster:
                    self.namespace = cluster.namespace or self.namespace
                    return get_core_api_for_cluster(cluster)
        try:
            api = get_core_api()
            self._ensure_cluster_namespace()
            return api
        except Exception:
            pass
        cluster = get_first_connected_cluster()
        if cluster:
            self.namespace = cluster.namespace or self.namespace
            return get_core_api_for_cluster(cluster)
        raise RuntimeError("No K8s cluster available")

    def _ensure_nfs_pvc(self, task=None):
        """确保 NFS PV 和 PVC 存在，不存在时自动创建"""
        try:
            core_api = self._get_core_api(task)
            # 检查 PVC 是否已存在
            try:
                core_api.read_namespaced_persistent_volume_claim(
                    name=self.nfs_pvc_name, namespace=self.namespace
                )
                return  # PVC 已存在
            except ApiException as e:
                if e.status != 404:
                    raise

            logger.info(f"TE: PVC '{self.nfs_pvc_name}' not found in ns '{self.namespace}', auto-creating...")

            # 从配置或数据库获取 NFS 服务器信息
            nfs_server = current_app.config.get('NFS_SERVER', '192.168.171.3')
            nfs_path = current_app.config.get('NFS_PATH', '/data/kubetrain')
            storage_size = current_app.config.get('NFS_STORAGE_SIZE', '100Gi')

            pv_name = self.nfs_pvc_name.replace('-pvc', '-pv')

            # 创建 PV（集群级资源）
            try:
                core_api.read_persistent_volume(name=pv_name)
                logger.info(f"TE: PV '{pv_name}' already exists")
            except ApiException as pv_e:
                if pv_e.status == 404:
                    pv = client.V1PersistentVolume(
                        api_version='v1',
                        kind='PersistentVolume',
                        metadata=client.V1ObjectMeta(
                            name=pv_name,
                            labels={'app': 'kubetrain', 'type': 'nfs'}
                        ),
                        spec=client.V1PersistentVolumeSpec(
                            capacity={'storage': storage_size},
                            access_modes=['ReadWriteMany'],
                            persistent_volume_reclaim_policy='Retain',
                            storage_class_name='',
                            nfs=client.V1NFSVolumeSource(
                                server=nfs_server,
                                path=nfs_path
                            )
                        )
                    )
                    core_api.create_persistent_volume(body=pv)
                    logger.info(f"TE: Created PV '{pv_name}' -> {nfs_server}:{nfs_path}")
                else:
                    raise

            # 创建 PVC
            pvc = client.V1PersistentVolumeClaim(
                api_version='v1',
                kind='PersistentVolumeClaim',
                metadata=client.V1ObjectMeta(
                    name=self.nfs_pvc_name,
                    namespace=self.namespace
                ),
                spec=client.V1PersistentVolumeClaimSpec(
                    access_modes=['ReadWriteMany'],
                    storage_class_name='',
                    resources=client.V1ResourceRequirements(
                        requests={'storage': storage_size}
                    ),
                    volume_name=pv_name
                )
            )
            core_api.create_namespaced_persistent_volume_claim(
                namespace=self.namespace, body=pvc
            )
            logger.info(f"TE: Created PVC '{self.nfs_pvc_name}' in ns '{self.namespace}'")

        except Exception as e:
            logger.error(f"TE: Failed to ensure NFS PVC: {e}")
            raise RuntimeError(f"NFS PVC setup failed: {e}")

    def create_training_job(self, task: Task) -> Tuple[bool, str]:
        self._load_config()

        # 单机模式 + 无GPU：优先尝试 K8s，失败则回退到本地进程执行
        is_single_no_gpu = (task.parallel_mode == 'single' and (task.gpu_limit or 0) == 0)

        try:
            batch_api = self._get_batch_api(task)

            # 确保 NFS PV/PVC 存在
            self._ensure_nfs_pvc(task)

            job_name = f"train-{task.id[:8]}-{uuid.uuid4().hex[:6]}"
            task.job_name = job_name

            if task.num_nodes > 1:
                self.create_headless_service(task, job_name)

            job = self._build_job_spec(task, job_name)
            batch_api.create_namespaced_job(namespace=self.namespace, body=job)
            logger.info(f"TE: Created Job {job_name} for task {task.id}")

            task.status = 'starting'
            task.started_at = datetime.utcnow()
            db.session.commit()
            return True, job_name

        except (ApiException, Exception) as e:
            error_msg = str(getattr(e, 'reason', e))
            if is_single_no_gpu:
                logger.warning(f"TE: K8s unavailable for task {task.id}, falling back to local execution: {error_msg}")
                return self._run_local_process(task)
            logger.error(f"TE: Failed to create Job for task {task.id}: {error_msg}")
            task.status = 'failed'
            task.error_message = error_msg
            db.session.commit()
            return False, error_msg

    def _run_local_process(self, task: Task) -> Tuple[bool, str]:
        """本地进程执行单机训练任务（K8s 不可用时的回退方案）"""
        import subprocess
        import threading
        import os

        job_name = f"local-{task.id[:8]}-{uuid.uuid4().hex[:6]}"
        task.job_name = job_name

        # 确定脚本内容或路径
        script_path = task.training_script or ''
        nfs_base = current_app.config.get('NFS_MOUNT_PATH', '/data')

        # Windows 本地执行时，/data 路径不可用，回退到临时目录
        import tempfile as _tf
        if os.name == 'nt' or not os.path.isdir(nfs_base):
            local_base = os.path.join(_tf.gettempdir(), 'kubetrain2_local')
            output_path = task.output_path or os.path.join(local_base, 'outputs', task.id)
            checkpoint_path = task.checkpoint_path or os.path.join(local_base, 'checkpoints', task.id)
        else:
            output_path = task.output_path or os.path.join(nfs_base, 'outputs', task.id)
            checkpoint_path = task.checkpoint_path or os.path.join(nfs_base, 'checkpoints', task.id)
        os.makedirs(output_path, exist_ok=True)
        os.makedirs(checkpoint_path, exist_ok=True)

        # FIX-1: 提前持久化 output_path/checkpoint_path，确保即使后台线程异常也不丢失
        if not task.output_path:
            task.output_path = output_path
        if not task.checkpoint_path:
            task.checkpoint_path = checkpoint_path

        # 解析数据集路径：本地执行时直接用原始路径（不转为容器路径）
        dataset_path = task.dataset_path or ''
        # 本地执行时也需解压压缩包数据集（与Agent/K8s容器对齐）
        if dataset_path and os.path.isfile(dataset_path):
            dataset_path = self._prepare_dataset_path(dataset_path, task.id)
            logger.info(f"TE local: dataset prepared -> {dataset_path}")

        # 构建环境变量
        env = os.environ.copy()
        parallel_mode = getattr(task, 'parallel_mode', 'single') or 'single'
        nproc = getattr(task, 'nproc_per_node', 1) or 1
        num_nodes = getattr(task, 'num_nodes', 1) or 1
        world_size = nproc if parallel_mode == 'ddp' and num_nodes == 1 else 1
        env.update({
            'PYTHONUNBUFFERED': '1',
            'TASK_ID': task.id,
            'JOB_NAME': job_name,
            'WORLD_SIZE': str(world_size),
            'MASTER_ADDR': 'localhost',
            'MASTER_PORT': str(self.ddp_master_port),
            'NODE_RANK': '0',
            'LOCAL_RANK': '0',
            'RANK': '0',
            'DATA_PATH': dataset_path,
            'DATASET_PATH': dataset_path,
            'OUTPUT_PATH': output_path,
            'CHECKPOINT_PATH': checkpoint_path,
        })
        if task.environment:
            for key, value in task.environment.items():
                if key not in ('DATA_PATH', 'DATASET_PATH', 'OUTPUT_PATH', 'CHECKPOINT_PATH'):
                    env[key] = str(value)

        # 构建训练命令
        if parallel_mode == 'ddp' and num_nodes == 1 and nproc > 1:
            cmd = ['torchrun', '--standalone', f'--nproc_per_node={nproc}', script_path]
            logger.info(f"TE local: using torchrun --standalone --nproc_per_node={nproc}")
        else:
            cmd = ['python', script_path]
        if task.training_args:
            for key, value in task.training_args.items():
                cmd.append(f'--{key}')
                cmd.append(str(value))

        try:
            task.status = 'starting'
            task.started_at = datetime.utcnow()
            db.session.commit()

            logger.info(f"TE: Starting local process for task {task.id}: {' '.join(cmd)}")

            # 在后台线程中运行训练进程
            app = current_app._get_current_object()

            def _run_in_background():
                _task_id = task.id
                log_path = os.path.join(output_path, 'logs')
                os.makedirs(log_path, exist_ok=True)
                log_file = os.path.join(log_path, 'training.log')
                try:
                    with open(log_file, 'w') as lf:
                        proc = subprocess.Popen(
                            cmd, env=env, stdout=lf, stderr=subprocess.STDOUT,
                            cwd=os.path.dirname(script_path) if os.path.dirname(script_path) else None
                        )
                        proc.wait()

                    with app.app_context():
                        t = Task.query.get(_task_id)
                        if not t:
                            logger.warning(f"TE: Local task {_task_id} not found in DB after process exit")
                            return
                        if proc.returncode == 0:
                            t.status = 'completed'
                            t.progress_percent = 100.0
                            t.completed_at = datetime.utcnow()
                            if t.started_at:
                                t.duration = int((t.completed_at - t.started_at).total_seconds())
                            # 解析训练输出提取指标和模型路径
                            self._extract_local_results(t, output_path, log_file)
                            logger.info(f"TE: Local task {_task_id} completed successfully "
                                        f"(loss={t.final_loss}, acc={t.final_accuracy}, model={t.model_path})")
                        else:
                            t.status = 'failed'
                            t.error_message = f'Training process exited with code {proc.returncode}'
                            t.completed_at = datetime.utcnow()
                            if t.started_at:
                                t.duration = int((t.completed_at - t.started_at).total_seconds())
                            logger.error(f"TE: Local task {_task_id} failed with exit code {proc.returncode}")
                        db.session.commit()

                        # BUG-A fix: 本地进程完成/失败后广播WebSocket状态，通知前端
                        from app.websocket.handlers import broadcast_status
                        if t.status == 'completed':
                            broadcast_status(t.id, 'completed', 'Training completed successfully')
                        else:
                            broadcast_status(t.id, 'failed', t.error_message or 'Training failed')

                        from app.services.task_scheduler import task_scheduler
                        task_scheduler._remove_from_running(t.id)
                        from app.services.resource_manager import resource_manager
                        resource_manager.release_resources(t.id)
                        task_scheduler._notify_taitp_status(t, t.status)

                except Exception as ex:
                    import traceback
                    logger.error(f"TE: Local task {_task_id} execution error: {ex}\n{traceback.format_exc()}")
                    with app.app_context():
                        t = Task.query.get(task.id)
                        if t:
                            t.status = 'failed'
                            t.error_message = str(ex)
                            t.completed_at = datetime.utcnow()
                            if t.started_at:
                                t.duration = int((t.completed_at - t.started_at).total_seconds())
                            db.session.commit()
                            from app.websocket.handlers import broadcast_status
                            broadcast_status(t.id, 'failed', str(ex))
                            from app.services.task_scheduler import task_scheduler
                            task_scheduler._remove_from_running(t.id)
                            from app.services.resource_manager import resource_manager
                            resource_manager.release_resources(t.id)
                            task_scheduler._notify_taitp_status(t, 'failed')

            thread = threading.Thread(target=_run_in_background, daemon=True)
            thread.start()

            task.status = 'running'
            db.session.commit()
            return True, job_name

        except Exception as e:
            error_msg = f"Local execution failed: {e}"
            logger.error(f"TE: {error_msg}")
            task.status = 'failed'
            task.error_message = error_msg
            db.session.commit()
            return False, error_msg

    def _extract_local_results(self, task, output_path: str, log_file: str):
        """解析本地训练输出，提取 final_loss / final_accuracy / model_path"""
        import re, glob

        # 1. 解析训练日志提取指标
        try:
            if os.path.isfile(log_file):
                with open(log_file, 'r', errors='ignore') as f:
                    content = f.read()

                # 匹配常见的 loss/accuracy 输出格式
                loss_values = []
                acc_values = []
                epoch_count = 0

                for line in content.split('\n'):
                    # Epoch N: loss=X.XXXX or Loss: X.XXXX
                    m = re.search(r'(?:loss|train_loss|training_loss)[=:\s]+([0-9]+\.?[0-9]*)', line, re.IGNORECASE)
                    if m:
                        try:
                            loss_values.append(float(m.group(1)))
                        except ValueError:
                            pass

                    # accuracy=X.XX or Accuracy: XX.XX% or acc=0.95
                    m = re.search(r'(?:accuracy|acc|test_acc|val_acc)[=:\s]+([0-9]+\.?[0-9]*)%?', line, re.IGNORECASE)
                    if m:
                        try:
                            val = float(m.group(1))
                            if val > 1.0:
                                val = val / 100.0
                            acc_values.append(val)
                        except ValueError:
                            pass

                    # Epoch count
                    m = re.search(r'[Ee]poch\s*[:\[]?\s*(\d+)', line)
                    if m:
                        try:
                            epoch_count = max(epoch_count, int(m.group(1)))
                        except ValueError:
                            pass

                if loss_values:
                    task.final_loss = loss_values[-1]
                if acc_values:
                    task.final_accuracy = acc_values[-1]
                if epoch_count > 0 and (not task.current_epoch or task.current_epoch < epoch_count):
                    task.current_epoch = epoch_count
                if epoch_count > 0 and not task.total_epochs:
                    task.total_epochs = epoch_count

                # best_metric
                task.best_metric = {
                    'final_loss': task.final_loss,
                    'final_accuracy': task.final_accuracy,
                }

        except Exception as e:
            logger.warning(f"TE: Failed to parse training log for task {task.id}: {e}")

        # FIX-2: 无条件设置 output_path（不依赖模型扫描是否成功）
        if not task.output_path:
            task.output_path = output_path
        logger.info(f"TE: _extract_local_results task={task.id} output_path={output_path}")

        # 2. 扫描输出目录查找模型文件
        try:
            model_extensions = ('.pt', '.pth', '.pkl', '.bin', '.onnx', '.safetensors', '.h5', '.pb')
            model_files = []
            for ext in model_extensions:
                pattern = os.path.join(output_path, '**', f'*{ext}')
                model_files.extend(glob.glob(pattern, recursive=True))
            # BUG-D fix: 检测文件名含 'model' 关键词的 .json 文件
            for jf in glob.glob(os.path.join(output_path, '**', '*model*.json'), recursive=True):
                if jf not in model_files:
                    model_files.append(jf)

            if model_files:
                # 优先选择最大的模型文件（通常是最终模型）
                best = max(model_files, key=lambda f: os.path.getsize(f))
                task.model_path = best
                logger.info(f"TE: Found model file for task {task.id}: {best}")
            else:
                # 没找到模型文件，设置 output_path 作为 model_path 以触发模型注册
                if task.final_loss is not None or task.final_accuracy is not None:
                    task.model_path = output_path
                    logger.info(f"TE: No model file found, using output_path as model_path: {output_path}")

        except Exception as e:
            logger.warning(f"TE: Failed to scan model files for task {task.id}: {e}")

    def _parse_cpu(self, cpu_str: str) -> int:
        if not cpu_str:
            return 1
        if str(cpu_str).endswith('m'):
            millis = int(cpu_str[:-1])
            return max(1, -(-millis // 1000))
        return int(cpu_str)

    def _parse_memory(self, memory_str: str) -> int:
        if not memory_str:
            return 2048
        memory_str = str(memory_str)
        if memory_str.endswith('Gi'):
            return int(float(memory_str[:-2]) * 1024)
        if memory_str.endswith('Mi'):
            return int(memory_str[:-2])
        return 2048

    def _build_job_spec(self, task: Task, job_name: str) -> client.V1Job:
        world_size = task.num_nodes * task.gpus_per_node
        if world_size < 1:
            world_size = task.num_nodes

        container = self._build_container(task, job_name, world_size)
        pod_template = self._build_pod_template(task, job_name, container)

        job_spec = client.V1JobSpec(
            parallelism=task.num_nodes,
            completions=task.num_nodes,
            completion_mode='Indexed',
            backoff_limit=0,
            ttl_seconds_after_finished=3600,
            template=pod_template
        )

        job = client.V1Job(
            api_version='batch/v1',
            kind='Job',
            metadata=client.V1ObjectMeta(
                name=job_name,
                namespace=self.namespace,
                labels={
                    'app': 'kubetrain',
                    'task_id': task.id,
                    'parallel_mode': task.parallel_mode
                }
            ),
            spec=job_spec
        )
        return job

    def _build_container(self, task: Task, job_name: str, world_size: int) -> client.V1Container:
        command, args = self._build_training_command(task, job_name, world_size)
        env_vars = self._build_env_vars(task, job_name, world_size)
        resources = self._build_resources(task)

        volume_mounts = [
            client.V1VolumeMount(name='nfs-data', mount_path='/data'),
            client.V1VolumeMount(name='shm', mount_path='/dev/shm')
        ]

        return client.V1Container(
            name='trainer',
            image=self.training_image,
            image_pull_policy=self.image_pull_policy,
            command=command,
            args=args,
            env=env_vars,
            resources=resources,
            volume_mounts=volume_mounts
        )

    def _to_container_path(self, path: str) -> str:
        if not path:
            return path
        if path.startswith('/data'):
            return path
        match = re.search(r'[/\\]data[/\\]', path)
        if match:
            rel = path[match.start():]
            return rel.replace('\\', '/')
        return path.replace('\\', '/')

    def _build_training_command(self, task: Task, job_name: str, world_size: int) -> Tuple[List[str], List[str]]:
        master_port = self.ddp_master_port
        nproc = task.gpus_per_node if task.gpus_per_node > 0 else 1
        master_addr = f'{job_name}-0.{job_name}.{self.namespace}.svc.cluster.local'

        training_script = self._to_container_path(task.training_script)

        mkdir_prefix = 'mkdir -p $OUTPUT_PATH $CHECKPOINT_PATH && chmod 777 $OUTPUT_PATH $CHECKPOINT_PATH && '

        # 自动解压数据集：支持 .zip/.tar.gz/.tgz/.tar，单子目录自动进入（与Agent对齐）
        mkdir_prefix += (
            '_DS_EXTRACTED=0; '
            'if echo "$DATASET_PATH" | grep -qE "\\.(zip|tar\\.gz|tgz|tar)$"; then '
            '_DS_DIR="${DATASET_PATH%.*}"; '
            'echo "$DATASET_PATH" | grep -q "\\.tar\\.gz$" && _DS_DIR="${DATASET_PATH%.tar.gz}"; '
            'if [ ! -d "$_DS_DIR" ] || [ -z "$(ls -A $_DS_DIR 2>/dev/null)" ]; then '
            'echo "[TE] Extracting dataset: $DATASET_PATH -> $_DS_DIR" && mkdir -p "$_DS_DIR" && '
            'if echo "$DATASET_PATH" | grep -q "\\.zip$"; then '
            'python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$DATASET_PATH" "$_DS_DIR"; '
            'elif echo "$DATASET_PATH" | grep -qE "\\.(tar\\.gz|tgz)$"; then '
            'tar xzf "$DATASET_PATH" -C "$_DS_DIR"; '
            'elif echo "$DATASET_PATH" | grep -q "\\.tar$"; then '
            'tar xf "$DATASET_PATH" -C "$_DS_DIR"; '
            'fi && _DS_EXTRACTED=1; '
            'fi; '
            # 单子目录自动进入
            '_DS_ITEMS=$(ls -1 "$_DS_DIR" 2>/dev/null | wc -l); '
            'if [ "$_DS_ITEMS" -eq 1 ]; then '
            '_DS_SINGLE=$(ls -1 "$_DS_DIR"); '
            'if [ -d "$_DS_DIR/$_DS_SINGLE" ]; then '
            '_DS_DIR="$_DS_DIR/$_DS_SINGLE"; '
            'echo "[TE] Single subdirectory detected, entering: $_DS_DIR"; '
            'fi; fi; '
            'export DATASET_PATH="$_DS_DIR"; export DATA_PATH="$_DS_DIR"; '
            'echo "[TE] DATASET_PATH updated to $DATASET_PATH"; '
            'fi && '
        )

        if task.pip_packages and task.pip_packages.strip():
            packages = task.pip_packages.strip()
            mkdir_prefix += f'echo "[TE] Installing pip packages: {packages}" && pip install --no-cache-dir {packages} && '

        wrapper_inject = self._build_wrapper_inject(training_script)
        l2_prefix = f'export _KT_SCRIPT={training_script} && {wrapper_inject}'
        full_prefix = mkdir_prefix + l2_prefix

        if task.parallel_mode == 'single':
            command = ['sh', '-c']
            train_cmd = f'python /tmp/_kubetrain_wrapper.py'
            if task.training_args:
                for key, value in task.training_args.items():
                    train_cmd += f' --{key} {value}'
            args = [full_prefix + train_cmd]

        elif task.parallel_mode == 'ddp':
            command = ['sh', '-c']
            torchrun_cmd = (
                f'torchrun '
                f'--nnodes={task.num_nodes} '
                f'--nproc_per_node={nproc} '
                f'--node_rank=$JOB_COMPLETION_INDEX '
                f'--master_addr={master_addr} '
                f'--master_port={master_port} '
                f'--rdzv_backend=static '
                f'--rdzv_endpoint={master_addr}:{master_port} '
                f'/tmp/_kubetrain_wrapper.py'
            )
            if task.training_args:
                for key, value in task.training_args.items():
                    torchrun_cmd += f' --{key}={value}'
            args = [full_prefix + torchrun_cmd]

        elif task.parallel_mode == 'fsdp':
            command = ['sh', '-c']
            torchrun_cmd = (
                f'torchrun '
                f'--nnodes={task.num_nodes} '
                f'--nproc_per_node={nproc} '
                f'--node_rank=$JOB_COMPLETION_INDEX '
                f'--master_addr={master_addr} '
                f'--master_port={master_port} '
                f'--rdzv_backend=static '
                f'--rdzv_endpoint={master_addr}:{master_port} '
                f'/tmp/_kubetrain_wrapper.py --use_fsdp'
            )
            if task.training_args:
                for key, value in task.training_args.items():
                    torchrun_cmd += f' --{key}={value}'
            args = [full_prefix + torchrun_cmd]

        else:
            command = ['sh', '-c']
            train_cmd = f'python /tmp/_kubetrain_wrapper.py'
            if task.training_args:
                for key, value in task.training_args.items():
                    train_cmd += f' --{key} {value}'
            args = [full_prefix + train_cmd]

        return command, args

    def _build_wrapper_inject(self, training_script: str) -> str:
        wrapper_cmd = (
            "cat > /tmp/_kubetrain_wrapper.py << 'WRAPPER_EOF'\n"
            "import os, sys, json, atexit, logging\n"
            "from pathlib import Path\n"
            "from datetime import datetime\n"
            "\n"
            "class _KTTee:\n"
            "    def __init__(self, orig, logf):\n"
            "        self.orig = orig\n"
            "        self.logf = logf\n"
            "    def write(self, data):\n"
            "        self.orig.write(data)\n"
            "        try:\n"
            "            self.logf.write(data)\n"
            "            self.logf.flush()\n"
            "        except OSError:\n"
            "            pass\n"
            "    def flush(self):\n"
            "        self.orig.flush()\n"
            "        try:\n"
            "            self.logf.flush()\n"
            "        except OSError:\n"
            "            pass\n"
            "    def __getattr__(self, name):\n"
            "        return getattr(self.orig, name)\n"
            "\n"
            "_kt_out = os.environ.get('OUTPUT_PATH', '/data/output')\n"
            "_kt_log_dir = os.path.join(_kt_out, 'logs')\n"
            "os.makedirs(_kt_log_dir, exist_ok=True)\n"
            "_kt_logf = open(os.path.join(_kt_log_dir, 'training.log'), 'w')\n"
            "sys.stdout = _KTTee(sys.stdout, _kt_logf)\n"
            "sys.stderr = _KTTee(sys.stderr, _kt_logf)\n"
            "\n"
            "logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)\n"
            "_kt_logger = logging.getLogger('te_wrapper')\n"
            "_kt_logger.info('[TE] Wrapper activated, script: ' + os.environ.get('_KT_SCRIPT','?'))\n"
            "\n"
            "import torch, torch.nn as _kt_nn\n"
            "_kt_tracked_models = []\n"
            "_kt_orig_init = _kt_nn.Module.__init__\n"
            "def _kt_patched_init(self, *a, **kw):\n"
            "    _kt_orig_init(self, *a, **kw)\n"
            "    _kt_tracked_models.append(self)\n"
            "_kt_nn.Module.__init__ = _kt_patched_init\n"
            "\n"
            "def _kt_model_fallback():\n"
            "    out = os.environ.get('OUTPUT_PATH', '/data/output')\n"
            "    os.makedirs(out, exist_ok=True)\n"
            "    existing = list(Path(out).glob('**/*.pt')) + list(Path(out).glob('**/*.pth'))\n"
            "    if existing:\n"
            "        _kt_logger.info(f'[TE] {len(existing)} model file(s) found, skip fallback.')\n"
            "        return\n"
            "    _kt_logger.warning('[TE] No model files found, attempting fallback save...')\n"
            "    best, best_size, best_name = None, 0, ''\n"
            "    for m in _kt_tracked_models:\n"
            "        try:\n"
            "            sd = m.module.state_dict() if hasattr(m,'module') else m.state_dict()\n"
            "            size = sum(p.numel() for p in sd.values())\n"
            "            if size > best_size:\n"
            "                best, best_size, best_name = m, size, m.__class__.__name__\n"
            "        except (AttributeError, RuntimeError) as _e:\n"
            "            _kt_logger.debug(f'[TE] Skipping model in fallback scan: {_e}')\n"
            "    if not best:\n"
            "        _kt_logger.warning('[TE] No nn.Module tracked, cannot fallback save.')\n"
            "        return\n"
            "    try:\n"
            "        sd = best.module.state_dict() if hasattr(best,'module') else best.state_dict()\n"
            "        p = os.path.join(out, 'te_fallback_model.pt')\n"
            "        torch.save(sd, p)\n"
            "        _kt_logger.info(f'[TE] Fallback model saved: {p} ({best_name}, {best_size} params)')\n"
            "        meta = {'source':'te_wrapper','class':best_name,'params':best_size,'saved_at':datetime.utcnow().isoformat()}\n"
            "        with open(os.path.join(out,'te_fallback_meta.json'),'w') as f:\n"
            "            json.dump(meta,f,indent=2)\n"
            "    except Exception as e:\n"
            "        _kt_logger.error(f'[TE] Fallback save failed: {e}')\n"
            "\n"
            "atexit.register(_kt_model_fallback)\n"
            "\n"
            "def _kt_emit_metric_summary():\n"
            "    out = os.environ.get('OUTPUT_PATH', '/data/output')\n"
            "    for root, dirs, files in os.walk(out):\n"
            "        for fname in files:\n"
            "            if not fname.endswith('.json'):\n"
            "                continue\n"
            "            if 'metric' not in fname.lower() and fname != 'metrics.json':\n"
            "                continue\n"
            "            try:\n"
            "                with open(os.path.join(root, fname)) as fh:\n"
            "                    data = json.load(fh)\n"
            "                if not isinstance(data, dict):\n"
            "                    continue\n"
            "                tl = data.get('train_loss', [])\n"
            "                ta = data.get('train_accuracy', [])\n"
            "                vl = data.get('test_loss', data.get('val_loss', []))\n"
            "                va = data.get('test_accuracy', data.get('val_accuracy', []))\n"
            "                if not any([tl, ta, vl, va]):\n"
            "                    continue\n"
            "                if not isinstance(tl, list): tl = []\n"
            "                if not isinstance(ta, list): ta = []\n"
            "                if not isinstance(vl, list): vl = []\n"
            "                if not isinstance(va, list): va = []\n"
            "                n = max(len(tl), len(ta), len(vl), len(va))\n"
            "                epochs = data.get('epochs', list(range(1, n+1)))\n"
            "                if not isinstance(epochs, list): epochs = list(range(1, n+1))\n"
            "                total = len(epochs)\n"
            "                if total == 0:\n"
            "                    continue\n"
            "                _kt_logger.info(f'[TE] Emitting {total} epoch metrics from {fname}')\n"
            "                for i, ep in enumerate(epochs):\n"
            "                    parts = [f'Epoch {ep}/{total}']\n"
            "                    if i < len(tl): parts.append(f'Train Loss: {tl[i]:.4f}')\n"
            "                    if i < len(ta): parts.append(f'Train Acc: {ta[i]:.2f}%')\n"
            "                    if i < len(vl): parts.append(f'Test Loss: {vl[i]:.4f}')\n"
            "                    if i < len(va): parts.append(f'Test Acc: {va[i]:.2f}%')\n"
            "                    _kt_logger.info(' - '.join(parts))\n"
            "            except: pass\n"
            "\n"
            "import runpy\n"
            "script = os.environ['_KT_SCRIPT']\n"
            "sys.argv[0] = script\n"
            "_kt_script_failed = False\n"
            "_kt_exit_code = 0\n"
            "try:\n"
            "    runpy.run_path(script, run_name='__main__')\n"
            "    _kt_logger.info('[TE] Training completed successfully.')\n"
            "except SystemExit as e:\n"
            "    _kt_exit_code = e.code if isinstance(e.code, int) else (1 if e.code else 0)\n"
            "    if _kt_exit_code != 0:\n"
            "        _kt_script_failed = True\n"
            "        _kt_logger.error(f'[TE] Script exited with code {_kt_exit_code}')\n"
            "except Exception as e:\n"
            "    _kt_script_failed = True\n"
            "    _kt_exit_code = 1\n"
            "    _kt_logger.error(f'[TE] Script error: {e}')\n"
            "    import traceback\n"
            "    _kt_logger.error(traceback.format_exc())\n"
            "\n"
            "if not _kt_script_failed:\n"
            "    _kt_emit_metric_summary()\n"
            "\n"
            "if _kt_script_failed:\n"
            "    _kt_logger.error(f'[TE] Task failed with exit code {_kt_exit_code}')\n"
            "    sys.exit(_kt_exit_code)\n"
            "WRAPPER_EOF\n"
        )
        return wrapper_cmd

    @staticmethod
    def _prepare_dataset_path(dataset_path: str, task_id: str = '') -> str:
        """准备数据集目录：压缩包自动解压，单文件wrap到目录，单子目录自动进入。
        与Agent的_prepare_dataset_for_docker()逻辑对齐，确保脚本收到的是可用目录。"""
        import tempfile as _tf, zipfile, tarfile, shutil

        if not dataset_path or not os.path.exists(dataset_path):
            return dataset_path or ''

        extract_dir = os.path.join(_tf.gettempdir(), 'te_datasets', task_id or 'default')

        if os.path.isfile(dataset_path):
            lower = dataset_path.lower()

            # 压缩包：解压到临时目录
            if lower.endswith('.zip') or lower.endswith('.tar.gz') or lower.endswith('.tgz') or lower.endswith('.tar'):
                if os.path.isdir(extract_dir):
                    shutil.rmtree(extract_dir, ignore_errors=True)
                os.makedirs(extract_dir, exist_ok=True)
                try:
                    if lower.endswith('.zip'):
                        with zipfile.ZipFile(dataset_path, 'r') as zf:
                            zf.extractall(extract_dir)
                    elif lower.endswith('.tar.gz') or lower.endswith('.tgz'):
                        with tarfile.open(dataset_path, 'r:gz') as tf:
                            tf.extractall(extract_dir)
                    elif lower.endswith('.tar'):
                        with tarfile.open(dataset_path, 'r') as tf:
                            tf.extractall(extract_dir)
                    logger.info(f"Dataset extracted: {dataset_path} -> {extract_dir}")
                except Exception as e:
                    logger.error(f"Failed to extract dataset: {e}")
                    return dataset_path

                # 单子目录自动进入
                items = os.listdir(extract_dir)
                if len(items) == 1 and os.path.isdir(os.path.join(extract_dir, items[0])):
                    extract_dir = os.path.join(extract_dir, items[0])
                    logger.info(f"Dataset single subdirectory, using: {extract_dir}")
                return extract_dir

            # 普通文件（非压缩包）：wrap到临时目录
            os.makedirs(extract_dir, exist_ok=True)
            dest = os.path.join(extract_dir, os.path.basename(dataset_path))
            if not os.path.exists(dest):
                shutil.copy2(dataset_path, dest)
            return extract_dir

        # 已经是目录
        return dataset_path

    def _resolve_dataset_path(self, task: Task) -> str:
        if task.dataset_path:
            dp = task.dataset_path.replace('\\', '/')
            if not dp.startswith('/data/'):
                match = re.search(r'datasets/([^/]+.*)', dp)
                if match:
                    dp = f'/data/datasets/{match.group(1)}'
            # 单文件数据集（csv/json/txt/npy等）返回父目录，
            # 让训练脚本自行搜索文件，兼容目录型和文件型数据集
            _, ext = os.path.splitext(dp)
            if ext and ext.lower() in ('.csv', '.json', '.txt', '.npy', '.tsv', '.parquet', '.h5', '.hdf5'):
                dp = os.path.dirname(dp)
            return dp
        if task.dataset_id:
            return f'/data/datasets/{task.dataset_id}'
        return '/data/datasets'

    def _build_env_vars(self, task: Task, job_name: str, world_size: int) -> List[client.V1EnvVar]:
        resolved_dataset_path = self._resolve_dataset_path(task)

        env_vars = [
            client.V1EnvVar(name='PYTHONUNBUFFERED', value='1'),
            client.V1EnvVar(name='TASK_ID', value=task.id),
            client.V1EnvVar(name='JOB_NAME', value=job_name),

            client.V1EnvVar(name='WORLD_SIZE', value=str(world_size)),
            client.V1EnvVar(name='MASTER_ADDR', value=f'{job_name}-0.{job_name}.{self.namespace}.svc.cluster.local'),
            client.V1EnvVar(name='MASTER_PORT', value=str(self.ddp_master_port)),

            client.V1EnvVar(name='DIST_BACKEND', value=self.ddp_backend),
            client.V1EnvVar(name='NCCL_DEBUG', value='INFO'),
            client.V1EnvVar(name='NCCL_IB_DISABLE', value='1'),

            client.V1EnvVar(
                name='NODE_RANK',
                value_from=client.V1EnvVarSource(
                    field_ref=client.V1ObjectFieldSelector(
                        field_path='metadata.annotations[\'batch.kubernetes.io/job-completion-index\']'
                    )
                )
            ),

            client.V1EnvVar(name='DATA_PATH', value=resolved_dataset_path),
            client.V1EnvVar(name='DATASET_PATH', value=resolved_dataset_path),
            client.V1EnvVar(name='OUTPUT_PATH', value=task.output_path or f'/data/outputs/{task.id}'),
            client.V1EnvVar(name='CHECKPOINT_PATH', value=task.checkpoint_path or f'/data/checkpoints/{task.id}'),
        ]

        # 系统已解析的路径变量不允许被 task.environment 覆盖
        _resolved_keys = {'DATA_PATH', 'DATASET_PATH', 'OUTPUT_PATH', 'CHECKPOINT_PATH'}
        if task.environment:
            for key, value in task.environment.items():
                if key in _resolved_keys:
                    continue
                env_vars.append(client.V1EnvVar(name=key, value=str(value)))

        return env_vars

    def _cluster_has_gpu(self) -> bool:
        """检查集群是否真正有 GPU 节点（已上报 nvidia.com/gpu）"""
        try:
            from app.models.resource import ClusterResource
            summary = ClusterResource.query.first()
            if summary and summary.total_gpus > 0:
                return True
            from app.models.node_pool import PoolNode
            gpu_nodes = PoolNode.query.filter(
                PoolNode.gpu_total > 0,
                PoolNode.status.in_(['idle', 'busy', 'online'])
            ).count()
            return gpu_nodes > 0
        except Exception:
            return False

    def _build_resources(self, task: Task) -> client.V1ResourceRequirements:
        requests = {'cpu': task.cpu_request, 'memory': task.memory_request}
        limits = {'cpu': task.cpu_limit, 'memory': task.memory_limit}
        if task.gpu_limit > 0 and self._cluster_has_gpu():
            limits['nvidia.com/gpu'] = str(task.gpu_limit)
        elif task.gpu_limit > 0:
            logger.warning(f"TE Task: gpu_limit={task.gpu_limit} but cluster has no GPU nodes, "
                          f"skipping nvidia.com/gpu resource to avoid Pending")
        return client.V1ResourceRequirements(requests=requests, limits=limits)

    def _build_pod_template(self, task: Task, job_name: str, container: client.V1Container) -> client.V1PodTemplateSpec:
        volumes = [
            client.V1Volume(
                name='nfs-data',
                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(claim_name=self.nfs_pvc_name)
            ),
            client.V1Volume(
                name='shm',
                empty_dir=client.V1EmptyDirVolumeSource(medium='Memory', size_limit='8Gi')
            )
        ]

        pod_spec = client.V1PodSpec(
            containers=[container],
            volumes=volumes,
            restart_policy='Never',
            subdomain=job_name,
            set_hostname_as_fqdn=False
        )

        if task.gpu_limit > 0 and self._cluster_has_gpu():
            pod_spec.node_selector = {'nvidia.com/gpu': 'true'}

        pod_template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels={
                    'app': 'kubetrain',
                    'task_id': task.id,
                    'job_name': job_name
                }
            ),
            spec=pod_spec
        )
        return pod_template

    def create_headless_service(self, task: Task, job_name: str) -> bool:
        self._load_config()
        if task.num_nodes <= 1:
            return True
        try:
            core_api = self._get_core_api(task)
            service = client.V1Service(
                api_version='v1',
                kind='Service',
                metadata=client.V1ObjectMeta(
                    name=job_name,
                    namespace=self.namespace,
                    labels={'app': 'kubetrain', 'task_id': task.id}
                ),
                spec=client.V1ServiceSpec(
                    cluster_ip='None',
                    selector={'job_name': job_name},
                    ports=[client.V1ServicePort(name='ddp', port=self.ddp_master_port, target_port=self.ddp_master_port)]
                )
            )
            core_api.create_namespaced_service(namespace=self.namespace, body=service)
            logger.info(f"TE: Created Headless Service {job_name} for DDP")
            return True
        except ApiException as e:
            if e.status == 409:
                return True
            logger.error(f"TE: Failed to create Headless Service: {e}")
            return False
        except Exception as e:
            logger.error(f"TE: Failed to create Headless Service: {e}")
            return False

    def delete_job(self, task: Task) -> bool:
        self._load_config()
        if not task.job_name:
            return True
        try:
            batch_api = self._get_batch_api(task)
            core_api = self._get_core_api(task)
            try:
                batch_api.delete_namespaced_job(
                    name=task.job_name, namespace=self.namespace,
                    body=client.V1DeleteOptions(propagation_policy='Foreground')
                )
                logger.info(f"TE: Deleted Job {task.job_name}")
            except ApiException as e:
                if e.status != 404:
                    raise
            try:
                core_api.delete_namespaced_service(name=task.job_name, namespace=self.namespace)
                logger.info(f"TE: Deleted Service {task.job_name}")
            except ApiException as e:
                if e.status != 404:
                    raise
            return True
        except Exception as e:
            logger.error(f"TE: Failed to delete Job resources: {e}")
            return False

    def get_job_status(self, job_name: str, task=None) -> Optional[Dict]:
        self._load_config()
        try:
            batch_api = self._get_batch_api(task)
            job = batch_api.read_namespaced_job_status(name=job_name, namespace=self.namespace)
            status = job.status
            return {
                'active': status.active or 0,
                'succeeded': status.succeeded or 0,
                'failed': status.failed or 0,
                'ready': getattr(status, 'ready', None) or 0,
                'start_time': status.start_time.isoformat() if status.start_time else None,
                'completion_time': status.completion_time.isoformat() if status.completion_time else None,
                'conditions': [
                    {'type': c.type, 'status': c.status, 'reason': c.reason, 'message': c.message}
                    for c in (status.conditions or [])
                ]
            }
        except ApiException as e:
            if e.status == 404:
                return None
            raise
        except Exception as e:
            logger.error(f"TE: Error getting job status for {job_name}: {e}")
            return None

    def get_pod_names(self, job_name: str, task=None) -> List[str]:
        self._load_config()
        try:
            core_api = self._get_core_api(task)
            pods = core_api.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f'job_name={job_name}'
            )
            return [pod.metadata.name for pod in pods.items]
        except Exception as e:
            logger.error(f"TE: Failed to get pod names: {e}")
            return []

    def test_connection(self, cluster):
        """测试 K8s 集群连接，返回 (ok: bool, message: str)

        支持三种认证方式（优先级从高到低）：
        1. kubeconfig_path — 读取 kubeconfig 文件
        2. kubeconfig_content — 内容写入临时文件后加载（自动替换 127.0.0.1 为 api_server）
        3. api_server + token — 合成 kubeconfig dict 直连
        4. api_server only — 无认证直连（仅用于测试连通性）
        """
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        tmp_path = None
        try:
            from kubernetes import client as k8s_client, config as k8s_config

            api_client = None

            # ---------- 方式1: kubeconfig 文件路径 ----------
            if cluster.kubeconfig_path and os.path.exists(cluster.kubeconfig_path):
                api_client = k8s_config.new_client_from_config(
                    config_file=cluster.kubeconfig_path
                )
                logger.info(f"test_connection: using kubeconfig_path={cluster.kubeconfig_path}")

            # ---------- 方式2: kubeconfig 文本内容 ----------
            elif getattr(cluster, 'kubeconfig_content', None):
                import tempfile
                content = cluster.kubeconfig_content
                # K3s 的 kubeconfig 默认 server: https://127.0.0.1:6443
                # 如果用户填了 api_server，自动替换为实际 IP
                if cluster.api_server:
                    api_host = _normalize_api_server(cluster.api_server)
                    content = content.replace('https://127.0.0.1:6443', api_host)
                    content = content.replace('https://localhost:6443', api_host)
                tmp = tempfile.NamedTemporaryFile(
                    delete=False, suffix='.yaml', mode='w', encoding='utf-8'
                )
                tmp.write(content)
                tmp.close()
                tmp_path = tmp.name
                api_client = k8s_config.new_client_from_config(config_file=tmp_path)
                logger.info(f"test_connection: using kubeconfig_content (temp={tmp_path})")

            # ---------- 方式3/4: api_server 直连（合成 kubeconfig dict） ----------
            elif cluster.api_server:
                api_host = _normalize_api_server(cluster.api_server)

                user_info = {}
                token = getattr(cluster, 'token', None)
                if token:
                    user_info = {'token': token}

                config_dict = {
                    'apiVersion': 'v1',
                    'kind': 'Config',
                    'clusters': [{
                        'cluster': {'server': api_host, 'insecure-skip-tls-verify': True},
                        'name': 'target'
                    }],
                    'contexts': [{
                        'context': {'cluster': 'target', 'user': 'target-user'},
                        'name': 'target-ctx'
                    }],
                    'current-context': 'target-ctx',
                    'users': [{'name': 'target-user', 'user': user_info}],
                }
                api_client = k8s_config.new_client_from_config_dict(config_dict)
                logger.info(f"test_connection: using api_server={api_host}, token={'yes' if token else 'no'}")

            else:
                return False, '集群未配置 kubeconfig 或 API Server'

            # 禁用 SSL 验证（K3s 自签名证书）
            api_client.configuration.verify_ssl = False
            api_client.configuration.ssl_ca_cert = None

            core = k8s_client.CoreV1Api(api_client)
            nodes = core.list_node(timeout_seconds=10)
            count = len(nodes.items)
            node_names = [n.metadata.name for n in nodes.items]
            cluster.node_count = count

            return True, f'连接成功，{count} 个节点: {", ".join(node_names)}'

        except Exception as e:
            logger.error(f"TE: Cluster connection test failed: {e}")
            err_str = str(e)
            hint = ''
            if '127.0.0.1' in err_str or 'localhost' in err_str:
                hint = '\n提示: 请检查 API Server 地址是否正确（K3s 默认为 https://<IP>:6443），或粘贴 kubeconfig 内容'
            elif 'Unauthorized' in err_str or '401' in err_str or '403' in err_str:
                hint = '\n提示: 认证失败，请提供 kubeconfig 内容或 Bearer Token'
            elif 'timed out' in err_str.lower() or 'timeout' in err_str.lower():
                hint = '\n提示: 连接超时，请确认 VM 已启动且 K3s 服务正在运行'
            return False, f'连接失败: {e}{hint}'
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


# 全局实例
k8s_job_executor = TEK8sJobExecutor()
