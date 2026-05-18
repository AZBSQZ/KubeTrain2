"""
KubeTrain2 - 配置文件
基于容器的分布式AI训练平台
"""
import os
from datetime import timedelta
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'kubetrain2-secret-2024')

    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '3306')
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '123456')
    DB_NAME = os.environ.get('DB_NAME', 'kubetrain2')

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{os.environ.get('DB_USER','root')}:{quote_plus(os.environ.get('DB_PASSWORD','123456'))}"
        f"@{os.environ.get('DB_HOST','localhost')}:{os.environ.get('DB_PORT','3306')}/{os.environ.get('DB_NAME','kubetrain2')}?charset=utf8mb4"
    )

    @classmethod
    def validate_secrets(cls):
        """生产环境启动时调用，确保敏感配置来自环境变量而非默认值"""
        import sys
        defaults = {
            'SECRET_KEY': 'kubetrain2-secret-2024',
            'JWT_SECRET_KEY': 'kubetrain2-jwt-secret-2024',
            'DB_PASSWORD': '123456',
        }
        env = os.environ.get('FLASK_ENV', 'development')
        if env == 'production':
            for key, default in defaults.items():
                if os.environ.get(key, default) == default:
                    print(f"[FATAL] Production requires {key} to be set via environment variable.", file=sys.stderr)
                    sys.exit(1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'kubetrain2-jwt-secret-2024')
    # 注意：生产环境必须通过环境变量覆盖以上所有默认密钥，调用 Config.validate_secrets() 检查
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    JWT_TOKEN_LOCATION = ['headers']
    JWT_HEADER_NAME = 'Authorization'
    JWT_HEADER_TYPE = 'Bearer'

    # 文件上传
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(os.path.dirname(__file__), 'uploads'))
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', str(2 * 1024 * 1024 * 1024)))  # 2GB

    # Kubernetes
    K8S_NAMESPACE = os.environ.get('K8S_NAMESPACE', 'kubetrain')
    K8S_CONFIG_PATH = os.environ.get('K8S_CONFIG_PATH', '')
    K8S_IN_CLUSTER = os.environ.get('K8S_IN_CLUSTER', 'false').lower() == 'true'
    K8S_API_TIMEOUT = int(os.environ.get('K8S_API_TIMEOUT', '5'))
    # 仅在使用自签名证书的 K3s/测试集群时设为 true，生产环境应配置正确的 CA 证书
    K8S_SKIP_TLS_VERIFY = os.environ.get('K8S_SKIP_TLS_VERIFY', 'false').lower() == 'true'

    # NFS / 存储
    NFS_MOUNT_PATH = os.environ.get('NFS_MOUNT_PATH', '/data')
    NFS_PVC_NAME = os.environ.get('NFS_PVC_NAME', 'kubetrain-data-pvc')
    NFS_REMOTE_BASE = os.environ.get('NFS_REMOTE_BASE', '/data/kubetrain')

    # SSH
    SSH_HOST = os.environ.get('SSH_HOST', '192.168.171.3')
    SSH_PORT = int(os.environ.get('SSH_PORT', '22'))
    SSH_USER = os.environ.get('SSH_USER', 'root')
    SSH_PASSWORD = os.environ.get('SSH_PASSWORD', '')
    SSH_KEY_FILE = os.environ.get('SSH_KEY_FILE', '')

    # 训练镜像
    TRAINING_IMAGE = os.environ.get('TRAINING_IMAGE', 'kubetrain/pytorch-ddp:latest')
    IMAGE_PULL_POLICY = os.environ.get('IMAGE_PULL_POLICY', 'IfNotPresent')

    # DDP
    DDP_BACKEND = os.environ.get('DDP_BACKEND', 'gloo')
    DDP_MASTER_PORT = int(os.environ.get('DDP_MASTER_PORT', '29500'))

    # 调度器
    SCHEDULER_INTERVAL = int(os.environ.get('SCHEDULER_INTERVAL', '5'))
    MAX_CONCURRENT_TASKS = int(os.environ.get('MAX_CONCURRENT_TASKS', '5'))
    WATCHER_INTERVAL = int(os.environ.get('WATCHER_INTERVAL', '10'))

    # 日志
    LOG_COLLECT_INTERVAL = int(os.environ.get('LOG_COLLECT_INTERVAL', '10'))
    LOG_TAIL_LINES = int(os.environ.get('LOG_TAIL_LINES', '500'))

    # 告警
    ALERT_CHECK_INTERVAL = int(os.environ.get('ALERT_CHECK_INTERVAL', '30'))
    TRAINING_TIMEOUT = int(os.environ.get('TRAINING_TIMEOUT', '86400'))

    # Worker
    WORKER_HEALTH_INTERVAL = int(os.environ.get('WORKER_HEALTH_INTERVAL', '30'))
    LOCAL_SCRIPT_DIR = os.environ.get('LOCAL_SCRIPT_DIR', '')


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
