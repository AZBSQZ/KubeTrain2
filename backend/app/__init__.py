"""
KubeTrain2 - Flask 应用工厂
基于容器的分布式AI训练平台
"""
import os
import logging

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from config import config

db = SQLAlchemy()
socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')
jwt = JWTManager()

logger = logging.getLogger(__name__)


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config['default']))

    # 创建上传目录
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)

    db.init_app(app)
    socketio.init_app(app)
    CORS(app, resources={
        r"/api/*": {
            "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
        }
    })
    jwt.init_app(app)

    @jwt.user_identity_loader
    def user_identity_lookup(user_id):
        return str(user_id)

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({'code': 401, 'message': 'Token已过期'}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({'code': 401, 'message': f'Token无效: {error}'}), 401

    @jwt.unauthorized_loader
    def unauthorized_callback(error):
        return jsonify({'code': 401, 'message': '缺少Token'}), 401

    _register_blueprints(app)

    from app.websocket.handlers import register_handlers
    register_handlers(socketio)

    @app.route('/api/health')
    def health_check():
        return jsonify({'status': 'ok', 'service': 'kubetrain2', 'version': '2.0.0'})

    @app.route('/api/health/dashboard')
    def health_dashboard():
        from app.models.task import Task
        from app.models.alert import Alert
        from sqlalchemy import func
        try:
            task_counts = dict(
                db.session.query(Task.status, func.count(Task.id))
                .group_by(Task.status).all()
            )
            total = sum(task_counts.values())
            tasks = {
                'total': total,
                'running': task_counts.get('running', 0),
                'queued': task_counts.get('queued', 0),
                'completed': task_counts.get('completed', 0),
                'failed': task_counts.get('failed', 0),
                'pending': task_counts.get('pending', 0),
            }
            resources = {}
            try:
                from app.services.worker_registry import worker_registry
                stats = worker_registry.get_worker_stats()
                resources = {
                    'total_nodes': stats.get('total_workers', 0),
                    'online_nodes': stats.get('online_workers', 0),
                    'total_gpus': stats.get('total_gpu', 0),
                    'available_gpus': stats.get('available_gpu', 0),
                }
            except Exception:
                pass
            active_alerts = 0
            try:
                active_alerts = Alert.query.filter_by(status='active').count()
            except Exception:
                pass
            recent = Task.query.order_by(Task.created_at.desc()).limit(10).all()
            return jsonify({
                'code': 200,
                'data': {
                    'tasks': tasks,
                    'resources': resources,
                    'active_alerts': active_alerts,
                    'recent_tasks': [t.to_dict() for t in recent],
                }
            })
        except Exception as e:
            return jsonify({'code': 500, 'message': str(e)}), 500

    with app.app_context():
        from app.models import (
            user, tag, dataset, algorithm, model, model_group,
            task, log, metric, resource, alert, node_pool, k8s_cluster,
            operation_log
        )
        db.create_all()
        _auto_migrate(app)
        _seed_defaults()

    _start_services(app)
    logger.info("KubeTrain2: App initialized successfully")
    return app


def _register_blueprints(app):
    from app.api.auth import auth_bp
    from app.api.dashboard import dashboard_bp
    from app.api.users import users_bp
    from app.api.datasets import datasets_bp
    from app.api.algorithms import algorithms_bp
    from app.api.models import models_bp
    from app.api.model_groups import model_groups_bp
    from app.api.tasks import tasks_bp
    from app.api.logs import logs_bp
    from app.api.metrics import metrics_bp
    from app.api.resources import resources_bp
    from app.api.alerts import alerts_bp
    from app.api.node_pools import node_pools_bp
    from app.api.workers import workers_bp
    from app.api.clusters import clusters_bp
    from app.api.tags import tags_bp
    from app.api.operation_logs import operation_logs_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(datasets_bp, url_prefix='/api/datasets')
    app.register_blueprint(algorithms_bp, url_prefix='/api/algorithms')
    app.register_blueprint(models_bp, url_prefix='/api/models')
    app.register_blueprint(model_groups_bp, url_prefix='/api/model-groups')
    app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
    app.register_blueprint(logs_bp, url_prefix='/api/logs')
    app.register_blueprint(metrics_bp, url_prefix='/api/metrics')
    app.register_blueprint(resources_bp, url_prefix='/api/resources')
    app.register_blueprint(alerts_bp, url_prefix='/api/alerts')
    app.register_blueprint(node_pools_bp, url_prefix='/api/node-pools')
    app.register_blueprint(workers_bp, url_prefix='/api/workers')
    app.register_blueprint(clusters_bp, url_prefix='/api/clusters')
    app.register_blueprint(tags_bp, url_prefix='/api/tags')
    app.register_blueprint(operation_logs_bp, url_prefix='/api/operation-logs')
    logger.info("KubeTrain2: Registered API blueprints")


def _start_services(app):
    for service_name, module_path, instance_name in [
        ('task_scheduler', 'app.services.task_scheduler', 'task_scheduler'),
        ('task_watcher', 'app.services.task_watcher', 'task_watcher'),
        ('log_collector', 'app.services.log_collector', 'log_collector'),
        ('resource_manager', 'app.services.resource_manager', 'resource_manager'),
        ('alert_service', 'app.services.alert_service', 'alert_service'),
        ('worker_registry', 'app.services.worker_registry', 'worker_registry'),
    ]:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            getattr(mod, instance_name).start(app)
            logger.info(f"KubeTrain2: {service_name} started")
        except Exception as e:
            logger.warning(f"KubeTrain2: Failed to start {service_name}: {e}")


def _seed_defaults():
    from app.models.user import User
    try:
        if User.query.count() == 0:
            admin = User(username='admin', email='admin@kubetrain.local', role='admin', is_active=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            logger.info("KubeTrain2: Default admin user created (admin/admin123)")
    except Exception as e:
        logger.warning(f"KubeTrain2: Seed defaults failed (non-fatal): {e}")
        try:
            db.session.rollback()
        except Exception:
            pass


def _auto_migrate(app):
    from sqlalchemy import text
    migrations = [
        ('users', 'avatar', 'ALTER TABLE users ADD COLUMN avatar VARCHAR(255) NULL'),
        ('users', 'last_login', 'ALTER TABLE users ADD COLUMN last_login DATETIME NULL'),
        ('tasks', 'execution_mode', "ALTER TABLE tasks ADD COLUMN execution_mode VARCHAR(20) DEFAULT 'auto' NOT NULL"),
        ('tasks', 'assigned_worker_id', 'ALTER TABLE tasks ADD COLUMN assigned_worker_id VARCHAR(64) NULL'),
        ('tasks', 'nproc_per_node', 'ALTER TABLE tasks ADD COLUMN nproc_per_node INT NOT NULL DEFAULT 1'),
        ('tasks', 'duration', 'ALTER TABLE tasks ADD COLUMN duration INTEGER NULL'),
        ('pool_nodes', 'node_type', "ALTER TABLE pool_nodes ADD COLUMN node_type VARCHAR(20) DEFAULT 'standalone' NOT NULL"),
        ('pool_nodes', 'cluster_id', 'ALTER TABLE pool_nodes ADD COLUMN cluster_id VARCHAR(64) NULL'),
        ('model_versions', 'task_id', 'ALTER TABLE model_versions ADD COLUMN task_id VARCHAR(64) NULL'),
        ('model_versions', 'dataset_id', 'ALTER TABLE model_versions ADD COLUMN dataset_id INT NULL'),
        ('model_versions', 'algorithm_version_id', 'ALTER TABLE model_versions ADD COLUMN algorithm_version_id INT NULL'),
        # K8s cluster auth fields
        ('k8s_clusters', 'auth_type', "ALTER TABLE k8s_clusters ADD COLUMN auth_type VARCHAR(20) DEFAULT 'kubeconfig'"),
        ('k8s_clusters', 'token', 'ALTER TABLE k8s_clusters ADD COLUMN token TEXT NULL'),
        ('k8s_clusters', 'ca_cert', 'ALTER TABLE k8s_clusters ADD COLUMN ca_cert TEXT NULL'),
        # Pipeline task fields
        ('tasks', 'parent_task_id', 'ALTER TABLE tasks ADD COLUMN parent_task_id VARCHAR(64) NULL'),
        ('tasks', 'stage_index', 'ALTER TABLE tasks ADD COLUMN stage_index INT NULL'),
        ('tasks', 'pipeline_config', 'ALTER TABLE tasks ADD COLUMN pipeline_config JSON NULL'),
        ('tasks', 'pipeline_progress', 'ALTER TABLE tasks ADD COLUMN pipeline_progress JSON NULL'),
        ('resource_allocations', 'quota_id', 'ALTER TABLE resource_allocations ADD COLUMN quota_id INT NULL'),
    ]
    try:
        dialect = db.engine.dialect.name
        for table_name, col_name, sql in migrations:
            try:
                if dialect == 'sqlite':
                    rows = db.session.execute(text(f'PRAGMA table_info({table_name})')).fetchall()
                    exists = any(row[1] == col_name for row in rows)
                else:
                    rows = db.session.execute(text(f"SHOW COLUMNS FROM {table_name} LIKE '{col_name}'")).fetchall()
                    exists = bool(rows)
                if not exists:
                    db.session.execute(text(sql))
                    db.session.commit()
                    logger.info(f"Auto-migrate: added {table_name}.{col_name}")
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Auto-migrate error (non-fatal): {e}")
