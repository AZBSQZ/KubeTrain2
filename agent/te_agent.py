#!/usr/bin/env python3
"""训练执行子系统 - Worker Agent
部署到计算节点，自动注册到 TE 注册中心并定期发送心跳。

用法:
  python3 te_agent.py --server http://192.168.171.1:8004
  python3 te_agent.py --server http://192.168.171.1:8004 --pool-id <pool_id>
  python3 te_agent.py --server http://192.168.171.1:8004 --token <service_token>

依赖: Python 3.6+, requests (pip3 install requests)
"""
import argparse
import json
import logging
import os
import platform
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: pip install requests")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [te-agent] %(message)s'
)
logger = logging.getLogger('te-agent')

AGENT_VERSION = '1.0.0'


class TEWorkerAgent:
    """Worker Agent - 在计算节点上运行，自动注册并发送心跳"""

    DEFAULT_SERVICE_TOKEN = 'taitp-internal-service-2024'

    def __init__(self, server_url: str, pool_id: str = None,
                 heartbeat_interval: int = 30, max_tasks: int = 2,
                 capabilities: list = None, labels: dict = None,
                 worker_id: str = None, service_token: str = None,
                 proxy_mode: bool = False):
        self.server_url = server_url.rstrip('/')
        self.proxy_mode = proxy_mode
        if proxy_mode:
            self.api_base = f"{self.server_url}/api/proxy/te/workers"
        else:
            self.api_base = f"{self.server_url}/api/workers"
        self.pool_id = pool_id
        self.heartbeat_interval = heartbeat_interval
        self.max_tasks = max_tasks
        self.capabilities = capabilities or []
        self.labels = labels or {}
        # 使用稳定的 worker_id：基于 hostname 生成确定性 UUID，避免重启后重复注册
        if worker_id:
            self.worker_id = worker_id
        else:
            stable_seed = f"te-agent-{socket.gethostname()}"
            self.worker_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, stable_seed))
        self.service_token = service_token or self.DEFAULT_SERVICE_TOKEN
        self.running = False
        self.registered = False
        self.node_id = None

    def start(self, agent_port: int = 8005):
        """启动 Agent"""
        self.agent_port = agent_port
        logger.info(f"TE Agent v{AGENT_VERSION} starting...")
        logger.info(f"  Server: {self.server_url}")
        logger.info(f"  API Base: {self.api_base}")
        if self.proxy_mode:
            logger.info(f"  Mode: PROXY (via taitp frontend)")
        logger.info(f"  Worker ID: {self.worker_id}")
        logger.info(f"  Heartbeat: {self.heartbeat_interval}s")
        logger.info(f"  Agent HTTP port: {agent_port}")

        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
        except (OSError, AttributeError):
            pass  # SIGTERM not available on Windows

        self.running = True

        # 启动 HTTP 服务器（接收任务分发）
        http_thread = threading.Thread(
            target=self.start_http_server, args=(agent_port,), daemon=True
        )
        http_thread.start()

        # 注册
        if not self._register():
            logger.error("Registration failed. Retrying in 10s...")
            time.sleep(10)
            if not self._register():
                logger.error("Registration failed twice. Exiting.")
                return

        # 心跳循环
        logger.info("Agent running. Press Ctrl+C to stop.")
        while self.running:
            try:
                self._heartbeat()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                # 如果心跳返回 404，尝试重新注册
                if '404' in str(e):
                    logger.info("Re-registering...")
                    self._register()
            time.sleep(self.heartbeat_interval)

        # 注销
        self._deregister()
        logger.info("Agent stopped.")

    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    # ==================== 系统信息采集 ====================

    def _collect_system_info(self) -> dict:
        """采集本机硬件和环境信息"""
        info = {
            'worker_id': self.worker_id,
            'hostname': socket.gethostname(),
            'ip_address': self._get_ip(),
            'port': getattr(self, 'agent_port', 8005),
            'name': socket.gethostname(),
            'agent_version': AGENT_VERSION,
            'heartbeat_interval': self.heartbeat_interval,
            'max_tasks': self.max_tasks,
            'capabilities': self.capabilities,
            'labels': self.labels,
        }

        if self.pool_id:
            info['pool_id'] = self.pool_id

        # CPU
        try:
            info['cpu_total'] = os.cpu_count() or 1
        except Exception:
            info['cpu_total'] = 1

        # Memory (MB)
        try:
            if platform.system() == 'Linux':
                with open('/proc/meminfo') as f:
                    for line in f:
                        if line.startswith('MemTotal'):
                            info['memory_total'] = int(line.split()[1]) // 1024
                            break
            elif platform.system() == 'Windows':
                import ctypes
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ('dwLength', ctypes.c_ulong),
                        ('dwMemoryLoad', ctypes.c_ulong),
                        ('ullTotalPhys', ctypes.c_ulonglong),
                        ('ullAvailPhys', ctypes.c_ulonglong),
                        ('ullTotalPageFile', ctypes.c_ulonglong),
                        ('ullAvailPageFile', ctypes.c_ulonglong),
                        ('ullTotalVirtual', ctypes.c_ulonglong),
                        ('ullAvailVirtual', ctypes.c_ulonglong),
                        ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
                    ]
                ms = MEMORYSTATUSEX()
                ms.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
                info['memory_total'] = ms.ullTotalPhys // (1024 * 1024)
        except Exception:
            info['memory_total'] = 0

        # Python
        info['python_version'] = platform.python_version()

        # OS
        info['os_info'] = {
            'system': platform.system(),
            'release': platform.release(),
            'machine': platform.machine(),
        }

        # GPU
        gpu_info = self._detect_gpu()
        info.update(gpu_info)

        # Docker
        info['docker_available'] = self._check_docker()
        info['container_runtime'] = self._detect_container_runtime()

        # NCCL
        info['nccl_available'] = self._check_nccl()

        # CUDA
        info['cuda_version'] = self._detect_cuda_version()

        # 自动添加能力标签
        auto_caps = list(self.capabilities)
        if info.get('gpu_total', 0) > 0:
            auto_caps.append('gpu')
        if info.get('docker_available'):
            auto_caps.append('docker')
        if info.get('nccl_available'):
            auto_caps.append('nccl')
        if info.get('cuda_version'):
            auto_caps.append('cuda')
        info['capabilities'] = list(set(auto_caps))

        return info

    def _collect_runtime_metrics(self) -> dict:
        """采集运行时利用率指标"""
        metrics = {
            'worker_id': self.worker_id,
            'tasks_running': self.get_running_task_count(),
        }

        # CPU 利用率
        try:
            if platform.system() == 'Linux':
                load1, _, _ = os.getloadavg()
                cpu_count = os.cpu_count() or 1
                metrics['cpu_utilization'] = round(min(100.0, load1 / cpu_count * 100), 1)
            else:
                metrics['cpu_utilization'] = 0.0
        except Exception:
            metrics['cpu_utilization'] = 0.0

        # Memory 利用率
        try:
            if platform.system() == 'Linux':
                with open('/proc/meminfo') as f:
                    mem = {}
                    for line in f:
                        parts = line.split()
                        mem[parts[0].rstrip(':')] = int(parts[1])
                    total = mem.get('MemTotal', 1)
                    available = mem.get('MemAvailable', mem.get('MemFree', 0))
                    metrics['memory_utilization'] = round((1 - available / total) * 100, 1)
        except Exception:
            metrics['memory_utilization'] = 0.0

        # GPU 利用率
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                utils = [float(x.strip()) for x in result.stdout.strip().split('\n') if x.strip()]
                metrics['gpu_utilization'] = round(sum(utils) / len(utils), 1) if utils else 0.0
        except Exception:
            metrics['gpu_utilization'] = 0.0

        metrics['docker_available'] = self._check_docker()

        return metrics

    # ==================== GPU 检测 ====================

    def _detect_gpu(self) -> dict:
        info = {'gpu_total': 0, 'gpu_model': None, 'gpu_details': []}
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,memory.total,uuid', '--format=csv,noheader'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
                info['gpu_total'] = len(lines)
                gpus = []
                for i, line in enumerate(lines):
                    parts = [p.strip() for p in line.split(',')]
                    gpu = {'index': i, 'name': parts[0] if len(parts) > 0 else 'Unknown'}
                    if len(parts) > 1:
                        gpu['memory_mb'] = int(parts[1].replace('MiB', '').strip())
                    if len(parts) > 2:
                        gpu['uuid'] = parts[2]
                    gpus.append(gpu)
                info['gpu_details'] = gpus
                if gpus:
                    info['gpu_model'] = gpus[0]['name']
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug(f"GPU detection error: {e}")
        return info

    def _detect_cuda_version(self) -> str:
        try:
            result = subprocess.run(
                ['nvcc', '--version'], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'release' in line.lower():
                        parts = line.split('release')
                        if len(parts) > 1:
                            return parts[1].split(',')[0].strip()
        except Exception:
            pass
        return None

    def _check_nccl(self) -> bool:
        try:
            result = subprocess.run(
                [sys.executable, '-c', 'import torch; print(torch.cuda.nccl.version())'],
                capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False

    def _check_docker(self) -> bool:
        try:
            result = subprocess.run(
                ['docker', 'info'], capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _detect_container_runtime(self) -> str:
        for rt in ['docker', 'podman', 'containerd']:
            try:
                result = subprocess.run(
                    [rt, '--version'], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return result.stdout.strip().split('\n')[0]
            except Exception:
                continue
        return None

    def _get_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return '127.0.0.1'

    # ==================== 协议通信 ====================

    def _auth_headers(self) -> dict:
        """构建认证请求头"""
        return {
            'X-Service-Token': self.service_token,
            'Content-Type': 'application/json',
        }

    def _register(self) -> bool:
        try:
            data = self._collect_system_info()
            logger.info(f"Registering: {data.get('hostname')} ({data.get('ip_address')})")
            logger.info(f"  CPU: {data.get('cpu_total')} cores, Memory: {data.get('memory_total')}MB")
            logger.info(f"  GPU: {data.get('gpu_total')}x {data.get('gpu_model', 'N/A')}")
            logger.info(f"  Capabilities: {data.get('capabilities')}")

            resp = requests.post(
                f"{self.api_base}/register",
                json=data, headers=self._auth_headers(), timeout=10
            )
            result = resp.json()

            if result.get('code') == 200:
                self.registered = True
                self.node_id = result.get('data', {}).get('id')
                logger.info(f"Registered successfully. Node ID: {self.node_id}")
                return True
            elif result.get('code') == 401:
                logger.error(f"Authentication failed: {result.get('message')}")
                logger.error("  Hint: use --token <service_token> or check INTERNAL_SERVICE_TOKEN on server")
                return False
            elif result.get('code') == 403:
                logger.error(f"Permission denied: {result.get('message')}")
                return False
            else:
                logger.error(f"Registration failed: {result.get('message')}")
                return False
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection refused: {self.api_base}")
            logger.error(f"  Hint: check that TE server is running and accessible from this node")
            return False
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return False

    def _heartbeat(self):
        metrics = self._collect_runtime_metrics()
        resp = requests.post(f"{self.api_base}/{self.worker_id}/heartbeat", json=metrics, timeout=10)
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")
        result = resp.json()

        if result.get('code') == 200:
            commands = result.get('data', {}).get('commands', [])
            if commands:
                logger.info(f"Received commands: {commands}")
                self._handle_commands(commands)
        elif result.get('code') == 404:
            raise Exception('404: Worker not registered')
        else:
            logger.warning(f"Heartbeat response: {result.get('message')}")

    def _deregister(self):
        if not self.registered:
            return
        try:
            resp = requests.post(
                f"{self.api_base}/{self.worker_id}/deregister",
                json={'worker_id': self.worker_id},
                headers=self._auth_headers(),
                timeout=10
            )
            result = resp.json()
            if result.get('code') == 200:
                logger.info("Deregistered successfully.")
            else:
                logger.warning(f"Deregister response: {result.get('message')}")
        except Exception as e:
            logger.error(f"Deregister error: {e}")

    def _handle_commands(self, commands: list):
        """处理来自注册中心的指令"""
        for cmd in commands:
            action = cmd.get('action')
            logger.info(f"Processing command: {action}")
            if action == 'execute_task':
                task_payload = cmd.get('payload', {})
                threading.Thread(
                    target=self._execute_task, args=(task_payload,), daemon=True
                ).start()
            elif action == 'cancel_task':
                task_id = cmd.get('task_id')
                self._cancel_task(task_id)

    # ==================== 任务执行引擎 ====================

    def __init_task_state(self):
        """Lazy init for task tracking"""
        if not hasattr(self, '_running_tasks'):
            self._running_tasks = {}  # task_id -> subprocess.Popen
            self._task_lock = threading.Lock()

    def _check_nvidia_docker(self) -> bool:
        """检测 nvidia-docker / NVIDIA Container Toolkit 是否可用"""
        try:
            result = subprocess.run(
                ['docker', 'info', '--format', '{{json .Runtimes}}'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and 'nvidia' in result.stdout.lower():
                return True
        except Exception:
            pass
        # fallback: 直接尝试 --gpus
        try:
            result = subprocess.run(
                ['docker', 'run', '--rm', '--gpus', 'all', 'nvidia/cuda:11.0-base', 'nvidia-smi'],
                capture_output=True, text=True, timeout=30
            )
            return result.returncode == 0
        except Exception:
            return False

    # 默认训练镜像（当TE后端未指定时使用）
    DEFAULT_TRAINING_IMAGE = 'kubetrain/pytorch-ddp:latest'

    def _execute_task(self, payload: dict):
        """在Docker容器中执行训练任务（统一执行模式，不支持裸机subprocess）"""
        self.__init_task_state()
        task_id = payload.get('task_id', 'unknown')
        logger.info(f"Executing task {task_id}")

        # 检查 Docker 可用性（必须条件）
        if not self._check_docker():
            error_msg = 'Docker is not available on this node. All training tasks require Docker.'
            logger.error(f"Task {task_id}: {error_msg}")
            self._callback_status(task_id, 'failed', error=error_msg)
            return

        # 训练镜像：payload指定 > 默认镜像
        training_image = payload.get('training_image', '') or self.DEFAULT_TRAINING_IMAGE
        logger.info(f"Task {task_id}: Docker execution, image={training_image}")

        # 委托给Docker执行方法
        payload['training_image'] = training_image
        return self._execute_task_docker(payload)

    @staticmethod
    def _prepare_dataset_for_docker(dataset_path: str, task_id: str) -> str:
        """准备数据集目录用于 Docker 挂载：压缩包自动解压，文件转目录，单子目录自动进入"""
        import tempfile as _tf, zipfile, tarfile, shutil
        if not dataset_path or not os.path.exists(dataset_path):
            return ''

        extract_dir = os.path.join(_tf.gettempdir(), 'te_agent', 'datasets', task_id)

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
                    logger.info(f"Dataset contents: {os.listdir(extract_dir)}")
                except Exception as e:
                    logger.error(f"Failed to extract dataset: {e}")
                    return ''

                # 如果解压后只有一个子目录，自动进入
                items = os.listdir(extract_dir)
                if len(items) == 1 and os.path.isdir(os.path.join(extract_dir, items[0])):
                    extract_dir = os.path.join(extract_dir, items[0])
                    logger.info(f"Dataset has single subdirectory, using: {extract_dir}")
                return extract_dir

            # 普通文件（非压缩包）：wrap到临时目录
            os.makedirs(extract_dir, exist_ok=True)
            dest = os.path.join(extract_dir, os.path.basename(dataset_path))
            if not os.path.exists(dest):
                shutil.copy2(dataset_path, dest)
            return extract_dir

        # 已经是目录
        return dataset_path

    def _execute_task_docker(self, payload: dict):
        """在 Docker 容器中执行训练任务"""
        import tempfile as _tempfile
        task_id = payload.get('task_id', 'unknown')

        script_path = payload.get('training_script', '')
        script_content = payload.get('script_content')
        training_args = payload.get('training_args') or {}
        environment = payload.get('environment') or {}
        dataset_path = payload.get('dataset_path', '')
        output_path = payload.get('output_path', '')
        checkpoint_path = payload.get('checkpoint_path', '')
        pip_packages = payload.get('pip_packages', '')
        training_image = payload.get('training_image', 'kubetrain/pytorch-ddp:latest')
        gpu_limit = payload.get('gpu_limit', 0)
        parallel_mode = payload.get('parallel_mode', 'single')
        nproc_per_node = max(1, int(payload.get('nproc_per_node', 1) or 1))

        logger.info(f"Docker task {task_id}: image={training_image}, script={script_path}, "
                     f"dataset={dataset_path}, output={output_path}, gpu={gpu_limit}, "
                     f"parallel_mode={parallel_mode}, nproc_per_node={nproc_per_node}")

        # 写脚本到本地临时文件（使用 newline='\n' 确保 Linux 换行符）
        local_script_dir = os.path.join(_tempfile.gettempdir(), 'te_agent_scripts', task_id)
        os.makedirs(local_script_dir, exist_ok=True)
        script_filename = os.path.basename(script_path) if script_path else 'train.py'
        if script_content:
            local_script_path = os.path.join(local_script_dir, script_filename)
            with open(local_script_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(script_content)
            logger.info(f"Docker task {task_id}: script written to {local_script_path}")
        elif script_path and os.path.isfile(script_path):
            import shutil
            local_script_path = os.path.join(local_script_dir, script_filename)
            shutil.copy2(script_path, local_script_path)
            logger.info(f"Docker task {task_id}: script copied to {local_script_path}")
        else:
            error_msg = f'Training script not available: {script_path}'
            logger.error(f"Docker task {task_id}: {error_msg}")
            self._callback_status(task_id, 'failed', error=error_msg)
            return

        # 准备本地输出目录
        local_output = os.path.join(_tempfile.gettempdir(), 'te_agent', 'outputs', task_id)
        local_checkpoint = os.path.join(_tempfile.gettempdir(), 'te_agent', 'checkpoints', task_id)
        os.makedirs(local_output, exist_ok=True)
        os.makedirs(local_checkpoint, exist_ok=True)

        # 如果原始 output_path 是可写的本地路径，使用它；否则使用临时目录
        if output_path:
            try:
                os.makedirs(output_path, exist_ok=True)
                local_output = output_path
            except (OSError, PermissionError):
                logger.info(f"Docker task {task_id}: output_path {output_path} not writable, using {local_output}")
        if checkpoint_path:
            try:
                os.makedirs(checkpoint_path, exist_ok=True)
                local_checkpoint = checkpoint_path
            except (OSError, PermissionError):
                pass

        # 准备数据集：zip解压、文件转目录，确保Docker可挂载
        local_dataset_dir = self._prepare_dataset_for_docker(dataset_path, task_id)

        # 构建 docker run 命令
        # DDP多进程模式需要更大的共享内存（PyTorch DataLoader多worker + 进程间通信）
        shm_size = '2g' if parallel_mode == 'ddp' and nproc_per_node > 1 else '256m'
        cmd = ['docker', 'run', '--rm', f'--shm-size={shm_size}']

        # GPU 支持
        if gpu_limit and gpu_limit > 0:
            if self._check_nvidia_docker():
                cmd.extend(['--gpus', 'all'])
                logger.info(f"Docker task {task_id}: GPU enabled (--gpus all)")
            else:
                logger.warning(f"Docker task {task_id}: gpu_limit={gpu_limit} but nvidia-docker not available")

        # Volume mounts
        container_script_dir = '/workspace/scripts'
        container_output = '/data/output'
        container_checkpoint = '/data/checkpoints'
        container_dataset = '/data/dataset'

        cmd.extend(['-v', f'{os.path.abspath(local_script_dir)}:{container_script_dir}'])
        cmd.extend(['-v', f'{os.path.abspath(local_output)}:{container_output}'])
        cmd.extend(['-v', f'{os.path.abspath(local_checkpoint)}:{container_checkpoint}'])

        if local_dataset_dir and os.path.isdir(local_dataset_dir):
            cmd.extend(['-v', f'{os.path.abspath(local_dataset_dir)}:{container_dataset}'])
            env_dataset = container_dataset
            logger.info(f"Docker task {task_id}: dataset mounted {local_dataset_dir} -> {container_dataset}")
        else:
            env_dataset = dataset_path or ''
            if dataset_path:
                logger.warning(f"Docker task {task_id}: dataset not mountable: {dataset_path}")

        # 环境变量：先注入用户自定义环境变量，再用容器路径覆盖（确保容器路径优先）
        docker_env = {k: str(v) for k, v in environment.items()}
        # 容器内固定路径（覆盖taitp传入的宿主机路径）
        world_size = nproc_per_node if parallel_mode == 'ddp' else 1
        docker_env.update({
            'PYTHONUNBUFFERED': '1',
            'TASK_ID': task_id,
            'WORLD_SIZE': str(world_size),
            'MASTER_ADDR': 'localhost',
            'MASTER_PORT': '29500',
            'NODE_RANK': '0',
            'LOCAL_RANK': '0',
            'RANK': '0',
            'DATA_PATH': env_dataset,
            'DATASET_PATH': env_dataset,
            'OUTPUT_PATH': container_output,
            'CHECKPOINT_PATH': container_checkpoint,
        })

        for k, v in docker_env.items():
            cmd.extend(['-e', f'{k}={v}'])

        # pip install 预装依赖
        if pip_packages and pip_packages.strip():
            pip_cmd = f'pip install --no-cache-dir {pip_packages.strip()} && '
        else:
            pip_cmd = ''

        # 训练命令参数（含常见别名映射，覆盖argparse命名差异）
        _PARAM_ALIASES = {
            'num_epochs': 'epochs',
            'learning_rate': 'lr',
        }
        # 过滤掉系统级/内部参数，只传递用户级超参数给训练脚本
        _SYSTEM_KEYS = {
            'weight_decay', 'warmup_steps', 'gradient_accumulation_steps',
            'max_grad_norm', 'seed', 'fp16', 'bf16', 'deepspeed',
            'save_steps', 'logging_steps', 'eval_steps', 'max_steps',
        }
        args_dict = {k: v for k, v in training_args.items() if k not in _SYSTEM_KEYS}
        for src, alias in _PARAM_ALIASES.items():
            if src in args_dict and alias not in args_dict:
                args_dict[alias] = args_dict[src]
        # 添加数据目录和输出目录参数，方便脚本通过argparse获取
        args_dict['data-dir'] = container_dataset
        args_dict['output-dir'] = container_output

        # 检测脚本参数接收方式：argparse (--key value) vs JSON配置文件
        # 读取脚本内容判断：如果使用 argparse/parse_args/parse_known_args 则用命令行参数
        # 如果使用 sys.argv[1] + open/json.load 则生成JSON配置文件
        _script_src = ''
        try:
            with open(local_script_path, 'r', encoding='utf-8') as _sf:
                _script_src = _sf.read()
        except Exception:
            pass

        _uses_argparse = ('argparse' in _script_src or 'parse_args' in _script_src
                          or 'parse_known_args' in _script_src)

        container_script = f'{container_script_dir}/{script_filename}'

        # DDP模式：用torchrun --standalone启动多进程；single模式：用python启动
        if parallel_mode == 'ddp' and nproc_per_node > 1:
            launcher = f'torchrun --standalone --nproc_per_node={nproc_per_node}'
        else:
            launcher = 'python'

        if _uses_argparse:
            # argparse风格：传 --key value 命令行参数
            train_args_str = ' '.join(f'--{k} {v}' for k, v in args_dict.items())
            full_cmd = f'{pip_cmd}{launcher} {container_script} {train_args_str}'.strip()
            logger.info(f"Docker task {task_id}: argparse mode, launcher={launcher}, args={train_args_str[:200]}")
        else:
            # JSON配置文件风格：生成config.json，传文件路径作为第一个参数
            import json as _json
            config_dict = {}
            # 反向映射：argparse别名 → 脚本常用的JSON键名
            _REVERSE_ALIASES = {'lr': 'learning_rate', 'num_epochs': 'epochs'}
            # 排除仅用于argparse的键
            _ARGPARSE_ONLY_KEYS = {'data-dir', 'output-dir'}
            for k, v in args_dict.items():
                if k in _ARGPARSE_ONLY_KEYS:
                    continue
                json_key = _REVERSE_ALIASES.get(k, k)
                # 尝试转换数值类型
                try:
                    v = int(v)
                except (ValueError, TypeError):
                    try:
                        v = float(v)
                    except (ValueError, TypeError):
                        pass
                config_dict[json_key] = v
            config_dict['dataset_path'] = container_dataset
            config_dict['output_path'] = container_output
            config_dict['model_save_path'] = f'{container_output}/model.pth'
            config_json_path = os.path.join(local_script_dir, 'config.json')
            with open(config_json_path, 'w', encoding='utf-8', newline='\n') as _cf:
                _json.dump(config_dict, _cf, indent=2, ensure_ascii=False)
            container_config = f'{container_script_dir}/config.json'
            full_cmd = f'{pip_cmd}{launcher} {container_script} {container_config}'.strip()
            logger.info(f"Docker task {task_id}: JSON config mode, launcher={launcher}, config={config_dict}")

        # 兼容性兜底：将 /data/dataset 软链到工作目录 data/，
        # 使硬编码 root='data' 或 root='./data' 的 torchvision 脚本也能使用已上传的数据集
        compat_link = (
            f'if [ -d "{container_dataset}" ] && [ "$(ls -A {container_dataset} 2>/dev/null)" ]; then '
            f'mkdir -p data && ln -sf {container_dataset}/* data/ 2>/dev/null; '
            f'echo "[agent] dataset symlinked: {container_dataset} -> data/"; '
            f'fi; '
        )
        full_cmd = compat_link + full_cmd

        # 使用 sh -c 兼容更多镜像（部分精简镜像无 bash）
        cmd.extend([training_image, 'sh', '-c', full_cmd])

        log_dir = os.path.join(local_output, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'training.log')

        logger.info(f"Docker task {task_id} full command: {' '.join(cmd)}")

        # 回调: running
        self._callback_status(task_id, 'running')

        try:
            import re
            logger.info(f"Docker task {task_id}: {' '.join(cmd[:10])}...")
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )

            with self._task_lock:
                self._running_tasks[task_id] = proc

            # 实时读取 stdout，解析进度并写入日志
            current_epoch = 0
            prev_epoch = -1
            # 从 training_args 获取 total_epochs 初始值（日志解析会覆盖）
            total_epochs = None
            docker_training_args = payload.get('training_args') or {}
            for _ek in ('epochs', 'num_epochs', 'total_epochs'):
                if docker_training_args.get(_ek):
                    try:
                        total_epochs = int(docker_training_args[_ek])
                    except (ValueError, TypeError):
                        pass
                    break
            last_loss = None
            last_acc = None
            last_report = time.time()

            with open(log_file, 'w', encoding='utf-8') as lf:
                for raw_line in iter(proc.stdout.readline, b''):
                    text = raw_line.decode('utf-8', errors='replace')
                    lf.write(text)
                    lf.flush()
                    # 实时发送日志给TE
                    stripped = text.strip()
                    if stripped:
                        self._callback_log(task_id, stripped)
                    m = re.search(r'[Ee]poch\s*[:\[（]?\s*(\d+)\s*[/\s]*(\d+)?', text)
                    if m:
                        current_epoch = int(m.group(1))
                        if m.group(2):
                            total_epochs = int(m.group(2))
                    m_loss = re.search(r'[Ll]oss[:\s]+([0-9]+\.?[0-9]*)', text)
                    if m_loss:
                        last_loss = float(m_loss.group(1))
                    m_acc = re.search(r'[Aa]cc(?:uracy)?[:\s]+([0-9]+\.?[0-9]*)', text)
                    if m_acc:
                        last_acc = float(m_acc.group(1))
                    # 每次epoch变化 或 每30秒 上报进度
                    epoch_changed = current_epoch != prev_epoch and current_epoch > 0
                    if epoch_changed or time.time() - last_report > 30:
                        if last_loss is not None or last_acc is not None:
                            self._callback_progress(task_id, current_epoch, total_epochs, last_loss, last_acc)
                            last_report = time.time()
                        if epoch_changed:
                            prev_epoch = current_epoch

            proc.wait()

            with self._task_lock:
                self._running_tasks.pop(task_id, None)

            # 刷新剩余日志缓冲
            self._flush_log_buffer(task_id)

            if proc.returncode == 0:
                logger.info(f"Docker task {task_id} completed successfully")
                # 发送最终进度回调（确保短时间完成的训练也有指标数据）
                if current_epoch > 0 or last_loss is not None or last_acc is not None:
                    self._callback_progress(task_id, current_epoch, total_epochs, last_loss, last_acc)
                # FIX-3: completed 回调携带 output_path 和扫描到的 model_path
                found_model = self._find_best_model(local_output)
                self._callback_status(task_id, 'completed',
                                      output_path=local_output,
                                      model_path=found_model)
            else:
                logger.error(f"Docker task {task_id} failed with exit code {proc.returncode}")
                self._callback_status(task_id, 'failed',
                                      error=f'Container exited with code {proc.returncode}')

        except Exception as e:
            logger.error(f"Docker task {task_id} execution error: {e}")
            with self._task_lock:
                self._running_tasks.pop(task_id, None)
            self._callback_status(task_id, 'failed', error=str(e))

    def _cancel_task(self, task_id: str):
        """取消正在运行的任务"""
        self.__init_task_state()
        with self._task_lock:
            proc = self._running_tasks.get(task_id)
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            logger.info(f"Task {task_id} cancelled")
            self._callback_status(task_id, 'cancelled')
        else:
            logger.warning(f"Task {task_id} not found in running tasks")

    def _build_callback_url(self, task_id: str) -> str:
        """根据 proxy_mode 构建正确的回调 URL"""
        if self.proxy_mode:
            return f"{self.server_url}/api/proxy/te/tasks/{task_id}/agent-callback"
        return f"{self.server_url}/api/tasks/{task_id}/agent-callback"

    def _callback_progress(self, task_id: str, current_epoch: int,
                           total_epochs: int = None, loss: float = None, accuracy: float = None):
        """回调 TE 服务器上报训练进度（非终态）"""
        try:
            url = self._build_callback_url(task_id)
            payload = {
                'status': 'running',
                'current_epoch': current_epoch,
            }
            if total_epochs is not None:
                payload['total_epochs'] = total_epochs
                payload['progress_percent'] = round(current_epoch / total_epochs * 100, 1) if total_epochs > 0 else 0
            metrics = {}
            if loss is not None:
                metrics['loss'] = round(loss, 6)
            if accuracy is not None:
                # 归一化到0-1范围（前端会乘100显示百分比）
                acc_val = accuracy
                if acc_val > 1:
                    acc_val = acc_val / 100.0
                metrics['accuracy'] = round(acc_val, 6)
            if metrics:
                payload['metrics'] = metrics
            requests.post(url, json=payload, headers=self._auth_headers(), timeout=5)
        except Exception as e:
            logger.debug(f"Progress callback failed for task {task_id}: {e}")

    def _init_log_buffer(self):
        """初始化日志缓冲"""
        if not hasattr(self, '_log_buffer'):
            self._log_buffer = {}
            self._log_flush_time = {}

    def _callback_log(self, task_id: str, message: str, level: str = 'info'):
        """缓冲日志行，批量发送给TE后端（每2秒或满20行刷新一次）"""
        self._init_log_buffer()
        if task_id not in self._log_buffer:
            self._log_buffer[task_id] = []
            self._log_flush_time[task_id] = time.time()
        self._log_buffer[task_id].append(message)
        # 满20行或超过2秒则刷新
        if len(self._log_buffer[task_id]) >= 20 or time.time() - self._log_flush_time.get(task_id, 0) > 2:
            self._flush_log_buffer(task_id)

    def _flush_log_buffer(self, task_id: str):
        """将缓冲的日志批量发送给TE"""
        self._init_log_buffer()
        lines = self._log_buffer.pop(task_id, [])
        self._log_flush_time[task_id] = time.time()
        if not lines:
            return
        try:
            url = self._build_callback_url(task_id)
            payload = {
                'status': 'running',
                'logs': [{'message': line, 'level': 'info', 'source': 'training'} for line in lines],
            }
            requests.post(url, json=payload, headers=self._auth_headers(), timeout=5)
        except Exception:
            pass  # 日志发送失败不影响训练

    def _callback_status(self, task_id: str, status: str, error: str = None,
                         output_path: str = None, model_path: str = None):
        """回调 TE 服务器更新任务状态"""
        try:
            url = self._build_callback_url(task_id)
            payload = {'status': status}
            if error:
                payload['error_message'] = error
            if output_path:
                payload['output_path'] = output_path
            if model_path:
                payload['model_path'] = model_path
            resp = requests.post(
                url, json=payload,
                headers=self._auth_headers(), timeout=10
            )
            if resp.status_code != 200:
                logger.warning(f"Callback failed for task {task_id}: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Callback error for task {task_id}: {e}")

    def _find_best_model(self, output_dir: str) -> str:
        """扫描输出目录查找最佳模型文件（与后端 _extract_local_results 逻辑对齐）"""
        import glob as _glob
        model_exts = ('.pt', '.pth', '.pkl', '.bin', '.onnx', '.safetensors', '.h5', '.pb')
        model_files = []
        try:
            for ext in model_exts:
                pattern = os.path.join(output_dir, '**', f'*{ext}')
                model_files.extend(_glob.glob(pattern, recursive=True))
            # 也检测 *model*.json
            for jf in _glob.glob(os.path.join(output_dir, '**', '*model*.json'), recursive=True):
                if jf not in model_files:
                    model_files.append(jf)
            if model_files:
                best = max(model_files, key=lambda f: os.path.getsize(f))
                logger.info(f"Found model file: {best}")
                return best
        except Exception as e:
            logger.warning(f"Model scan error: {e}")
        return ''

    def get_running_task_count(self) -> int:
        self.__init_task_state()
        with self._task_lock:
            return len(self._running_tasks)

    # ==================== HTTP 服务器（接收任务分发） ====================

    def start_http_server(self, port: int = 8005):
        """启动 HTTP 服务器接收任务分发"""
        agent = self

        class AgentHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path == '/api/agent/execute':
                    content_len = int(self.headers.get('Content-Length', 0))
                    body = json.loads(self.rfile.read(content_len)) if content_len else {}
                    threading.Thread(
                        target=agent._execute_task, args=(body,), daemon=True
                    ).start()
                    self._json_response(200, {'code': 200, 'message': 'Task accepted'})

                elif self.path == '/api/agent/cancel':
                    content_len = int(self.headers.get('Content-Length', 0))
                    body = json.loads(self.rfile.read(content_len)) if content_len else {}
                    task_id = body.get('task_id')
                    if task_id:
                        threading.Thread(
                            target=agent._cancel_task, args=(task_id,), daemon=True
                        ).start()
                        self._json_response(200, {'code': 200, 'message': 'Cancel requested'})
                    else:
                        self._json_response(400, {'code': 400, 'message': 'task_id required'})

                elif self.path == '/api/agent/status':
                    self._json_response(200, {
                        'code': 200,
                        'worker_id': agent.worker_id,
                        'running_tasks': agent.get_running_task_count(),
                        'registered': agent.registered,
                    })
                else:
                    self._json_response(404, {'code': 404, 'message': 'Not found'})

            def do_GET(self):
                if self.path == '/api/agent/health':
                    self._json_response(200, {'code': 200, 'status': 'ok'})
                else:
                    self._json_response(404, {'code': 404, 'message': 'Not found'})

            def _json_response(self, status_code, data):
                self.send_response(status_code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def log_message(self, format, *args):
                logger.debug(f"HTTP: {format % args}")

        server = HTTPServer(('0.0.0.0', port), AgentHandler)
        logger.info(f"Agent HTTP server listening on port {port}")
        server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description='TE Worker Agent')
    parser.add_argument('--server', required=True, help='TE API server URL (e.g. http://192.168.171.1:8004)')
    parser.add_argument('--pool-id', default=None, help='Node pool ID (auto-creates default if omitted)')
    parser.add_argument('--worker-id', default=None, help='Worker ID (auto-generated if omitted)')
    parser.add_argument('--heartbeat', type=int, default=30, help='Heartbeat interval in seconds')
    parser.add_argument('--max-tasks', type=int, default=2, help='Max concurrent tasks')
    parser.add_argument('--capabilities', nargs='*', default=[], help='Extra capability labels')
    parser.add_argument('--labels', type=json.loads, default={}, help='Extra labels as JSON')
    parser.add_argument('--token', default=None, help='Internal service token for authentication')
    parser.add_argument('--proxy', action='store_true',
                        help='Use proxy mode: route through taitp frontend (21096) instead of direct TE (8004)')
    parser.add_argument('--agent-port', type=int, default=8005,
                        help='HTTP port for receiving task dispatch (default: 8005)')

    args = parser.parse_args()

    agent = TEWorkerAgent(
        server_url=args.server,
        pool_id=args.pool_id,
        heartbeat_interval=args.heartbeat,
        max_tasks=args.max_tasks,
        capabilities=args.capabilities,
        labels=args.labels,
        worker_id=args.worker_id,
        service_token=args.token,
        proxy_mode=args.proxy,
    )
    agent.start(agent_port=args.agent_port)


if __name__ == '__main__':
    main()
