-- KubeTrain2 Pipeline Feature Migration
-- Run this on existing databases to add pipeline support columns to the tasks table.
-- Safe to run multiple times (uses IF NOT EXISTS / column existence checks).

-- Add pipeline_config column
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tasks' AND COLUMN_NAME = 'pipeline_config');
SET @sql = IF(@col_exists = 0, 
    'ALTER TABLE `tasks` ADD COLUMN `pipeline_config` JSON COMMENT ''Pipeline definition: {stages: [{name, algorithm_version_id, ...}]}'' AFTER `error_message`',
    'SELECT ''pipeline_config already exists''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add parent_task_id column
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tasks' AND COLUMN_NAME = 'parent_task_id');
SET @sql = IF(@col_exists = 0, 
    'ALTER TABLE `tasks` ADD COLUMN `parent_task_id` VARCHAR(64) COMMENT ''Parent pipeline task ID for child stage tasks'' AFTER `pipeline_config`',
    'SELECT ''parent_task_id already exists''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add stage_index column
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tasks' AND COLUMN_NAME = 'stage_index');
SET @sql = IF(@col_exists = 0, 
    'ALTER TABLE `tasks` ADD COLUMN `stage_index` INT COMMENT ''0-based stage index for child tasks'' AFTER `parent_task_id`',
    'SELECT ''stage_index already exists''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add pipeline_progress column
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tasks' AND COLUMN_NAME = 'pipeline_progress');
SET @sql = IF(@col_exists = 0, 
    'ALTER TABLE `tasks` ADD COLUMN `pipeline_progress` JSON COMMENT ''{current_stage, stages: [{task_id, status, model_path}]}'' AFTER `stage_index`',
    'SELECT ''pipeline_progress already exists''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add index on parent_task_id
SET @idx_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS 
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tasks' AND INDEX_NAME = 'idx_parent_task');
SET @sql = IF(@idx_exists = 0, 
    'ALTER TABLE `tasks` ADD INDEX `idx_parent_task` (`parent_task_id`)',
    'SELECT ''idx_parent_task already exists''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add foreign key (optional, may fail if data integrity issues exist)
-- ALTER TABLE `tasks` ADD CONSTRAINT `fk_task_parent` FOREIGN KEY (`parent_task_id`) REFERENCES `tasks` (`id`) ON DELETE SET NULL;
