-- KubeTrain 2.0 数据库初始化脚本
-- 此文件与 backend/app/models/ 下的 SQLAlchemy 模型定义完全对齐
-- 编码: UTF-8, 引擎: InnoDB, 时区: UTC
-- 执行前请先创建数据库: CREATE DATABASE IF NOT EXISTS kubetrain2 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================
-- 资源配额（前置，users 表依赖 FK）
-- ============================================================
CREATE TABLE IF NOT EXISTS `resource_quotas` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(255) NOT NULL UNIQUE,
  `description` TEXT,
  `pool_id` VARCHAR(64),
  `max_gpus` INT DEFAULT 0,
  `max_cpus` INT DEFAULT 0,
  `max_memory` INT DEFAULT 0,
  `max_tasks` INT DEFAULT 10,
  `used_gpus` INT DEFAULT 0,
  `used_cpus` INT DEFAULT 0,
  `used_memory` INT DEFAULT 0,
  `used_tasks` INT DEFAULT 0,
  `is_enabled` TINYINT(1) DEFAULT 1,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 用户表
-- ============================================================
CREATE TABLE IF NOT EXISTS `users` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `username` VARCHAR(50) NOT NULL UNIQUE,
  `password_hash` VARCHAR(255) NOT NULL,
  `email` VARCHAR(100),
  `role` ENUM('admin','user','guest') DEFAULT 'user',
  `avatar` VARCHAR(255),
  `is_active` TINYINT(1) DEFAULT 1,
  `quota_id` INT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `last_login` DATETIME,
  PRIMARY KEY (`id`),
  CONSTRAINT `fk_user_quota` FOREIGN KEY (`quota_id`) REFERENCES `resource_quotas` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 标签表
-- ============================================================
CREATE TABLE IF NOT EXISTS `tags` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(50) NOT NULL UNIQUE,
  `color` VARCHAR(20) DEFAULT '#409eff',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 数据集  (models: Dataset, DatasetVersion, DatasetTag)
-- ============================================================
CREATE TABLE IF NOT EXISTS `datasets` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL,
  `description` TEXT,
  `data_type` VARCHAR(50),
  `source_type` VARCHAR(20) DEFAULT 'upload',
  `original_filename` VARCHAR(255),
  `total_size` BIGINT DEFAULT 0,
  `record_count` INT DEFAULT 0,
  `is_public` TINYINT(1) DEFAULT 0,
  `is_deleted` TINYINT(1) DEFAULT 0,
  `created_by` INT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `fk_ds_user` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `dataset_versions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `dataset_id` INT NOT NULL,
  `version_number` VARCHAR(20) NOT NULL,
  `version_name` VARCHAR(100),
  `file_path` VARCHAR(500),
  `file_size` BIGINT DEFAULT 0,
  `file_hash` VARCHAR(128),
  `description` TEXT,
  `created_by` INT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_dv_dataset` (`dataset_id`),
  CONSTRAINT `fk_dv_dataset` FOREIGN KEY (`dataset_id`) REFERENCES `datasets` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `dataset_tags` (
  `dataset_id` INT NOT NULL,
  `tag_id` INT NOT NULL,
  PRIMARY KEY (`dataset_id`, `tag_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 算法  (models: Algorithm, AlgorithmVersion, AlgorithmTag)
-- ============================================================
CREATE TABLE IF NOT EXISTS `algorithms` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL,
  `description` TEXT,
  `algorithm_type` VARCHAR(50),
  `framework` VARCHAR(50) DEFAULT 'PyTorch',
  `is_public` TINYINT(1) DEFAULT 0,
  `is_deleted` TINYINT(1) DEFAULT 0,
  `created_by` INT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `fk_algo_user` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `algorithm_versions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `algorithm_id` INT NOT NULL,
  `version_number` VARCHAR(20) NOT NULL,
  `version_name` VARCHAR(100),
  `script_path` VARCHAR(500),
  `script_content` LONGTEXT,
  `parameters` JSON,
  `dependencies` JSON,
  `description` TEXT,
  `is_active` TINYINT(1) DEFAULT 1,
  `created_by` INT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_av_algo` (`algorithm_id`),
  CONSTRAINT `fk_av_algo` FOREIGN KEY (`algorithm_id`) REFERENCES `algorithms` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `algorithm_tags` (
  `algorithm_id` INT NOT NULL,
  `tag_id` INT NOT NULL,
  PRIMARY KEY (`algorithm_id`, `tag_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 模型分组  (model: ModelGroup)
-- ============================================================
CREATE TABLE IF NOT EXISTS `model_groups` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL UNIQUE,
  `description` TEXT,
  `created_by` INT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `fk_mg_user` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 模型  (models: Model, ModelVersion, ModelTag)
-- ============================================================
CREATE TABLE IF NOT EXISTS `models` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL,
  `description` TEXT,
  `model_type` VARCHAR(50),
  `framework` VARCHAR(50) DEFAULT 'PyTorch',
  `source` VARCHAR(20) DEFAULT 'training',
  `group_id` INT,
  `is_public` TINYINT(1) DEFAULT 0,
  `is_deleted` TINYINT(1) DEFAULT 0,
  `created_by` INT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `fk_model_group` FOREIGN KEY (`group_id`) REFERENCES `model_groups` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_model_user` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `model_versions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `model_id` INT NOT NULL,
  `version_number` VARCHAR(20) NOT NULL,
  `version_name` VARCHAR(100),
  `file_path` VARCHAR(500),
  `file_size` BIGINT DEFAULT 0,
  `file_format` VARCHAR(20),
  `model_structure` JSON,
  `metrics` JSON,
  `hyperparameters` JSON,
  `parent_version_id` INT,
  `task_id` VARCHAR(64),
  `dataset_id` INT,
  `algorithm_version_id` INT,
  `is_production` TINYINT(1) DEFAULT 0,
  `created_by` INT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `description` TEXT,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_model_version` (`model_id`, `version_number`),
  CONSTRAINT `fk_mv_model` FOREIGN KEY (`model_id`) REFERENCES `models` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_mv_parent` FOREIGN KEY (`parent_version_id`) REFERENCES `model_versions` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_mv_dataset` FOREIGN KEY (`dataset_id`) REFERENCES `datasets` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_mv_algo_ver` FOREIGN KEY (`algorithm_version_id`) REFERENCES `algorithm_versions` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_mv_user` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `model_tags` (
  `model_id` INT NOT NULL,
  `tag_id` INT NOT NULL,
  PRIMARY KEY (`model_id`, `tag_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 资源节点  (model: ResourceNode)
-- ============================================================
CREATE TABLE IF NOT EXISTS `resource_nodes` (
  `id` VARCHAR(64) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `hostname` VARCHAR(255),
  `ip_address` VARCHAR(45),
  `pool_id` VARCHAR(64),
  `status` VARCHAR(20) DEFAULT 'online' NOT NULL,
  `gpu_total` INT DEFAULT 0,
  `gpu_available` INT DEFAULT 0,
  `gpu_model` VARCHAR(100),
  `gpu_memory` INT DEFAULT 0,
  `cpu_total` INT DEFAULT 0,
  `cpu_available` INT DEFAULT 0,
  `memory_total` INT DEFAULT 0,
  `memory_available` INT DEFAULT 0,
  `storage_total` INT DEFAULT 0,
  `storage_available` INT DEFAULT 0,
  `cpu_utilization` FLOAT DEFAULT 0.0,
  `memory_utilization` FLOAT DEFAULT 0.0,
  `gpu_utilization` FLOAT DEFAULT 0.0,
  `docker_available` TINYINT(1) DEFAULT 0,
  `labels` JSON,
  `last_heartbeat` DATETIME,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_rn_pool` (`pool_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 资源分配  (model: ResourceAllocation)
-- ============================================================
CREATE TABLE IF NOT EXISTS `resource_allocations` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `task_id` VARCHAR(64) NOT NULL,
  `node_id` VARCHAR(64),
  `quota_id` INT,
  `gpu_allocated` INT DEFAULT 0,
  `cpu_allocated` INT DEFAULT 0,
  `memory_allocated` INT DEFAULT 0,
  `is_active` TINYINT(1) DEFAULT 1,
  `allocated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `released_at` DATETIME,
  PRIMARY KEY (`id`),
  KEY `idx_ra_task` (`task_id`),
  KEY `idx_ra_quota` (`quota_id`),
  CONSTRAINT `fk_ra_task` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ra_node` FOREIGN KEY (`node_id`) REFERENCES `resource_nodes` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_ra_quota` FOREIGN KEY (`quota_id`) REFERENCES `resource_quotas` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 集群资源汇总  (model: ClusterResource)
-- ============================================================
CREATE TABLE IF NOT EXISTS `cluster_resources` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `total_nodes` INT DEFAULT 0,
  `online_nodes` INT DEFAULT 0,
  `total_gpus` INT DEFAULT 0,
  `available_gpus` INT DEFAULT 0,
  `total_cpus` INT DEFAULT 0,
  `available_cpus` INT DEFAULT 0,
  `total_memory` INT DEFAULT 0,
  `available_memory` INT DEFAULT 0,
  `avg_cpu_utilization` FLOAT DEFAULT 0.0,
  `avg_memory_utilization` FLOAT DEFAULT 0.0,
  `avg_gpu_utilization` FLOAT DEFAULT 0.0,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 节点池  (models: NodePool, PoolNode)
-- ============================================================
CREATE TABLE IF NOT EXISTS `node_pools` (
  `id` VARCHAR(64) NOT NULL,
  `name` VARCHAR(255) NOT NULL UNIQUE,
  `description` TEXT,
  `provider` VARCHAR(20) DEFAULT 'bare_metal' NOT NULL,
  `cpu_per_node` INT DEFAULT 4,
  `memory_per_node` INT DEFAULT 8192,
  `gpu_per_node` INT DEFAULT 0,
  `gpu_type` VARCHAR(100),
  `max_nodes` INT DEFAULT 10,
  `current_nodes` INT DEFAULT 0,
  `status` VARCHAR(20) DEFAULT 'active' NOT NULL,
  `status_message` TEXT,
  `labels` JSON,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `pool_nodes` (
  `id` VARCHAR(64) NOT NULL,
  `pool_id` VARCHAR(64) NOT NULL,
  `node_type` VARCHAR(20) DEFAULT 'standalone' NOT NULL,
  `cluster_id` VARCHAR(64),
  `name` VARCHAR(255) NOT NULL,
  `hostname` VARCHAR(255),
  `ip_address` VARCHAR(45),
  `port` INT DEFAULT 8005,
  `worker_id` VARCHAR(64),
  `status` VARCHAR(20) DEFAULT 'offline' NOT NULL,
  `status_message` TEXT,
  `cpu_total` INT DEFAULT 0,
  `memory_total` INT DEFAULT 0,
  `gpu_total` INT DEFAULT 0,
  `gpu_model` VARCHAR(100),
  `storage_total` INT DEFAULT 0,
  `cpu_allocated` INT DEFAULT 0,
  `memory_allocated` INT DEFAULT 0,
  `gpu_allocated` INT DEFAULT 0,
  `cpu_utilization` FLOAT DEFAULT 0.0,
  `memory_utilization` FLOAT DEFAULT 0.0,
  `gpu_utilization` FLOAT DEFAULT 0.0,
  `docker_available` TINYINT(1) DEFAULT 0,
  `tasks_running` INT DEFAULT 0,
  `max_tasks` INT DEFAULT 2,
  `labels` JSON,
  `capabilities` JSON,
  `gpu_details` JSON,
  `container_runtime` VARCHAR(100),
  `os_info` JSON,
  `agent_version` VARCHAR(50),
  `python_version` VARCHAR(50),
  `cuda_version` VARCHAR(50),
  `nccl_available` TINYINT(1) DEFAULT 0,
  `network_bandwidth_mbps` INT DEFAULT 0,
  `heartbeat_interval` INT DEFAULT 30,
  `registered_at` DATETIME,
  `deregistered_at` DATETIME,
  `last_heartbeat` DATETIME,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `fk_pn_pool` FOREIGN KEY (`pool_id`) REFERENCES `node_pools` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- Worker 任务槽位  (model: WorkerTaskSlot)
-- ============================================================
CREATE TABLE IF NOT EXISTS `worker_task_slots` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `worker_id` VARCHAR(64) NOT NULL,
  `task_id` VARCHAR(64),
  `cpu_allocated` INT DEFAULT 0,
  `memory_allocated` INT DEFAULT 0,
  `gpu_allocated` INT DEFAULT 0,
  `status` VARCHAR(20) DEFAULT 'idle',
  `assigned_at` DATETIME,
  `released_at` DATETIME,
  PRIMARY KEY (`id`),
  KEY `idx_wts_worker` (`worker_id`),
  CONSTRAINT `fk_wts_worker` FOREIGN KEY (`worker_id`) REFERENCES `pool_nodes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- K8s 集群  (model: K8sCluster)
-- ============================================================
CREATE TABLE IF NOT EXISTS `k8s_clusters` (
  `id` VARCHAR(64) NOT NULL,
  `name` VARCHAR(255) NOT NULL UNIQUE,
  `description` TEXT,
  `api_server` VARCHAR(500),
  `kubeconfig_path` VARCHAR(500),
  `kubeconfig_content` TEXT,
  `namespace` VARCHAR(100) DEFAULT 'kubetrain',
  `pvc_name` VARCHAR(255) DEFAULT 'kubetrain-data-pvc',
  `status` VARCHAR(20) DEFAULT 'unknown',
  `status_message` TEXT,
  `node_count` INT DEFAULT 0,
  `is_default` TINYINT(1) DEFAULT 0,
  `labels` JSON,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 告警  (models: AlertRule, Alert)
-- ============================================================
CREATE TABLE IF NOT EXISTS `alert_rules` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(255) NOT NULL,
  `description` TEXT,
  `alert_type` VARCHAR(50) NOT NULL,
  `level` VARCHAR(20) DEFAULT 'warning',
  `is_enabled` TINYINT(1) DEFAULT 1,
  `condition` JSON NOT NULL,
  `actions` JSON,
  `cooldown_seconds` INT DEFAULT 300,
  `last_triggered_at` DATETIME,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `alerts` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `alert_type` VARCHAR(50) NOT NULL,
  `level` VARCHAR(20) DEFAULT 'warning',
  `status` VARCHAR(20) DEFAULT 'active',
  `task_id` VARCHAR(64),
  `node_id` VARCHAR(64),
  `pod_name` VARCHAR(255),
  `title` VARCHAR(255) NOT NULL,
  `message` TEXT NOT NULL,
  `details` JSON,
  `rule_id` INT,
  `acknowledged_by` VARCHAR(100),
  `acknowledged_at` DATETIME,
  `resolved_by` VARCHAR(100),
  `resolved_at` DATETIME,
  `resolution_note` TEXT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_alert_status` (`status`),
  KEY `idx_alert_level` (`level`),
  CONSTRAINT `fk_alert_rule` FOREIGN KEY (`rule_id`) REFERENCES `alert_rules` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 训练任务  (model: Task)
-- ============================================================
CREATE TABLE IF NOT EXISTS `tasks` (
  `id` VARCHAR(64) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `description` TEXT,
  `status` VARCHAR(20) NOT NULL DEFAULT 'pending',
  `priority` INT NOT NULL DEFAULT 5,
  `execution_mode` VARCHAR(20) DEFAULT 'auto' NOT NULL,
  `assigned_worker_id` VARCHAR(64),
  `parallel_mode` VARCHAR(20) DEFAULT 'single',
  `num_nodes` INT DEFAULT 1,
  `gpus_per_node` INT DEFAULT 0,
  `nproc_per_node` INT DEFAULT 1 NOT NULL,
  `training_script` VARCHAR(500),
  `training_args` JSON,
  `environment` JSON,
  `dataset_id` INT,
  `algorithm_id` INT,
  `algorithm_version_id` INT,
  `base_model_id` INT,
  `base_model_path` VARCHAR(500),
  `dataset_path` VARCHAR(500),
  `output_path` VARCHAR(500),
  `checkpoint_path` VARCHAR(500),
  `pip_packages` TEXT,
  `cpu_request` VARCHAR(20) DEFAULT '1',
  `cpu_limit` VARCHAR(20) DEFAULT '4',
  `memory_request` VARCHAR(20) DEFAULT '4Gi',
  `memory_limit` VARCHAR(20) DEFAULT '8Gi',
  `gpu_limit` INT DEFAULT 0,
  `job_name` VARCHAR(255),
  `pod_names` JSON,
  `current_epoch` INT DEFAULT 0,
  `total_epochs` INT,
  `progress_percent` FLOAT DEFAULT 0.0,
  `final_loss` FLOAT,
  `final_accuracy` FLOAT,
  `best_metric` JSON,
  `model_path` VARCHAR(500),
  `retry_count` INT DEFAULT 0,
  `max_retries` INT DEFAULT 3,
  `error_message` TEXT,
  `created_by` INT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `queued_at` DATETIME,
  `started_at` DATETIME,
  `completed_at` DATETIME,
  `duration` INT,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  -- Pipeline fields
  `pipeline_config` JSON COMMENT 'Pipeline definition: {stages: [{name, algorithm_version_id, ...}]}',
  `parent_task_id` VARCHAR(64) COMMENT 'Parent pipeline task ID for child stage tasks',
  `stage_index` INT COMMENT '0-based stage index for child tasks',
  `pipeline_progress` JSON COMMENT '{current_stage, stages: [{task_id, status, model_path}]}',
  PRIMARY KEY (`id`),
  KEY `idx_task_status` (`status`),
  KEY `idx_task_created_by` (`created_by`),
  KEY `idx_task_created_at` (`created_at`),
  KEY `idx_task_parent` (`parent_task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 任务日志  (model: TaskLog)
-- ============================================================
CREATE TABLE IF NOT EXISTS `task_logs` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `task_id` VARCHAR(64) NOT NULL,
  `level` VARCHAR(20) DEFAULT 'info',
  `source` VARCHAR(100),
  `message` TEXT NOT NULL,
  `pod_name` VARCHAR(255),
  `container_name` VARCHAR(100),
  `epoch` INT,
  `extra_data` JSON,
  `timestamp` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_tl_task` (`task_id`),
  KEY `idx_tl_timestamp` (`timestamp`),
  CONSTRAINT `fk_tl_task` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 训练指标  (model: TaskMetric)
-- ============================================================
CREATE TABLE IF NOT EXISTS `task_metrics` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `task_id` VARCHAR(64) NOT NULL,
  `epoch` INT,
  `step` INT,
  `loss` FLOAT,
  `accuracy` FLOAT,
  `learning_rate` FLOAT,
  `val_loss` FLOAT,
  `val_accuracy` FLOAT,
  `cpu_utilization` FLOAT,
  `memory_used` FLOAT,
  `gpu_utilization` FLOAT,
  `gpu_memory_used` FLOAT,
  `node_rank` INT,
  `world_size` INT,
  `throughput` FLOAT,
  `custom_metrics` JSON,
  `timestamp` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_tm_task` (`task_id`),
  KEY `idx_tm_timestamp` (`timestamp`),
  CONSTRAINT `fk_tm_task` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 操作日志  (model: OperationLog)
-- ============================================================
CREATE TABLE IF NOT EXISTS `operation_logs` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `user_id` INT,
  `username` VARCHAR(50),
  `operation_type` VARCHAR(50) NOT NULL,
  `module` VARCHAR(50) NOT NULL,
  `target_type` VARCHAR(50),
  `target_id` VARCHAR(50),
  `target_name` VARCHAR(200),
  `action` VARCHAR(100) NOT NULL,
  `detail` JSON,
  `ip_address` VARCHAR(50),
  `user_agent` VARCHAR(500),
  `result` VARCHAR(20) DEFAULT 'success',
  `error_message` TEXT,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ol_user` (`user_id`),
  KEY `idx_ol_module` (`module`),
  KEY `idx_ol_created` (`created_at`),
  CONSTRAINT `fk_ol_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;
