"""
Kubernetes 客户端管理
支持多集群动态配置：通过 K8sCluster 模型记录的集群信息创建客户端
同时保留默认客户端（兼容旧逻辑）
"""
import os
import logging
import tempfile
from typing import Optional
from flask import current_app

logger = logging.getLogger(__name__)

_k8s_clients = {}
_cluster_clients_cache = {}
_k8s_clients_created_at = 0
_K8S_CLIENTS_TTL = 300  # 缓存有效期 5 分钟


def get_k8s_clients():
    """获取默认 Kubernetes API 客户端
    
    优先级：
    1. 已缓存且未过期的客户端
    2. 数据库中已注册的第一个 connected 集群（kubeconfig 始终最新）
    3. K8S_IN_CLUSTER 集群内配置
    4. K8S_CONFIG_PATH 或默认 kubeconfig 文件
    """
    global _k8s_clients, _k8s_clients_created_at
    import time as _time

    if _k8s_clients and (_time.time() - _k8s_clients_created_at) < _K8S_CLIENTS_TTL:
        return _k8s_clients
    # 缓存过期，清除后重建
    if _k8s_clients:
        logger.info("TE: K8s client cache expired, rebuilding...")
        _k8s_clients = {}

    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # 优先使用数据库中注册的集群（kubeconfig 由用户主动注册，始终是最新的）
    cluster = get_first_connected_cluster()
    if cluster:
        logger.info(f"TE: Using registered cluster: {cluster.name}")
        clients = get_k8s_clients_for_cluster(cluster)
        _k8s_clients = clients
        _k8s_clients_created_at = _time.time()
        return _k8s_clients

    # fallback: 尝试本地 kubeconfig
    try:
        from kubernetes import client, config

        if current_app.config.get('K8S_IN_CLUSTER'):
            config.load_incluster_config()
            logger.info("TE: Loaded in-cluster Kubernetes config")
            _api_client = client.ApiClient()
        else:
            config_path = current_app.config.get('K8S_CONFIG_PATH') or None
            _api_client = config.new_client_from_config(config_file=config_path)
            logger.info(f"TE: Loaded Kubernetes config from: {config_path or 'default'}")

        # 仅当明确配置 K8S_SKIP_TLS_VERIFY=true 时才跳过 SSL 验证（用于 K3s 自签名证书场景）
        if current_app.config.get('K8S_SKIP_TLS_VERIFY', False):
            _api_client.configuration.verify_ssl = False
            _api_client.configuration.ssl_ca_cert = None
            logger.warning("TE: K8s SSL verification disabled (K8S_SKIP_TLS_VERIFY=true)")

        _k8s_clients = {
            'core': client.CoreV1Api(_api_client),
            'batch': client.BatchV1Api(_api_client),
            'apps': client.AppsV1Api(_api_client)
        }
        _k8s_clients_created_at = _time.time()

        return _k8s_clients

    except Exception as e:
        logger.error(f"TE: Failed to initialize Kubernetes client: {e}")
        raise


def _normalize_api_server(api_server: str) -> str:
    """将用户输入的 api_server 标准化为 https://<host>:<port> 格式"""
    s = api_server.strip().rstrip('/')
    if s.startswith('http://'):
        s = s[len('http://'):]
    if s.startswith('https://'):
        s = s[len('https://'):]
    if ':' not in s:
        s = f'{s}:6443'
    return f'https://{s}'


def get_k8s_clients_for_cluster(cluster):
    """根据 K8sCluster 模型记录动态创建 K8s 客户端

    优先级：kubeconfig_path > kubeconfig_content > api_server+token
    使用 new_client_from_config / new_client_from_config_dict 避免全局 Configuration 污染

    Args:
        cluster: K8sCluster 模型实例
    Returns:
        dict: {'core': CoreV1Api, 'batch': BatchV1Api, 'apps': AppsV1Api}
    """
    from kubernetes import client, config as k8s_config

    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    tmp_path = None
    try:
        api_client = None

        # ---------- 方式1: kubeconfig 文件路径 ----------
        if getattr(cluster, 'kubeconfig_path', None) and os.path.exists(cluster.kubeconfig_path):
            api_client = k8s_config.new_client_from_config(
                config_file=cluster.kubeconfig_path
            )
            logger.info(f"TE: Loaded kubeconfig for cluster {cluster.name}: {cluster.kubeconfig_path}")

        # ---------- 方式2: kubeconfig 文本内容 ----------
        elif getattr(cluster, 'kubeconfig_content', None):
            content = cluster.kubeconfig_content
            # K3s kubeconfig 默认 server: https://127.0.0.1:6443，替换为实际 api_server
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
            logger.info(f"TE: Loaded kubeconfig_content for cluster {cluster.name}")

        # ---------- 方式3: api_server 直连（合成 kubeconfig dict） ----------
        elif getattr(cluster, 'api_server', None):
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
            logger.info(f"TE: Using api_server for cluster {cluster.name}: {api_host}")

        else:
            raise ValueError(f"Cluster {cluster.name}: 未配置 kubeconfig 或 api_server")

        # 仅当集群明确配置了 insecure-skip-tls-verify 或 K8S_SKIP_TLS_VERIFY 时跳过 SSL 验证
        skip_tls = getattr(cluster, 'skip_tls_verify', False)
        if skip_tls:
            api_client.configuration.verify_ssl = False
            api_client.configuration.ssl_ca_cert = None
            logger.warning(f"TE: SSL verification disabled for cluster {cluster.name}")

        clients = {
            'core': client.CoreV1Api(api_client),
            'batch': client.BatchV1Api(api_client),
            'apps': client.AppsV1Api(api_client)
        }
        logger.info(f"TE: Created K8s clients for cluster: {cluster.name}")
        return clients

    except Exception as e:
        logger.error(f"TE: Failed to create K8s clients for cluster {cluster.name}: {e}")
        raise
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def get_first_connected_cluster():
    """获取第一个已连接的 K8sCluster 记录，用于自动模式"""
    try:
        from app.models.k8s_cluster import K8sCluster
        return K8sCluster.query.filter_by(status='connected').first()
    except Exception:
        return None


def get_batch_api_for_cluster(cluster):
    return get_k8s_clients_for_cluster(cluster)['batch']


def get_core_api_for_cluster(cluster):
    return get_k8s_clients_for_cluster(cluster)['core']


def get_core_api():
    return get_k8s_clients()['core']


def get_batch_api():
    return get_k8s_clients()['batch']


def get_apps_api():
    return get_k8s_clients()['apps']


def is_k8s_available():
    """检查是否有任何可用的 K8s 集群"""
    # 方式1：检查数据库中已注册的集群
    cluster = get_first_connected_cluster()
    if cluster:
        return True
    # 方式2：尝试默认配置
    try:
        get_k8s_clients()
        return True
    except Exception:
        return False


def reset_clients():
    global _k8s_clients, _cluster_clients_cache, _k8s_clients_created_at
    _k8s_clients = {}
    _cluster_clients_cache = {}
    _k8s_clients_created_at = 0
