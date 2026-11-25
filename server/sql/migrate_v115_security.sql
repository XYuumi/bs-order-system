-- v1.15 安全与实时能力迁移（MySQL 8.0，可重复执行）
-- 1) sys_user.token_version：JWT 主动吊销
-- 2) orders.deliver_token_version：单订单交付链接撤销
-- 3) chunk_upload：服务端分片上传会话（鉴权/配额/过期清理）
-- 4) 补齐模型声明但历史迁移才有的索引

SET @dbname = DATABASE();

-- ---------- sys_user.token_version ----------
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE sys_user ADD COLUMN token_version INT NOT NULL DEFAULT 0',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'sys_user' AND COLUMN_NAME = 'token_version'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------- orders.deliver_token_version ----------
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE orders ADD COLUMN deliver_token_version INT NOT NULL DEFAULT 0',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'orders' AND COLUMN_NAME = 'deliver_token_version'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------- chunk_upload ----------
CREATE TABLE IF NOT EXISTS chunk_upload (
  id VARCHAR(32) NOT NULL,
  order_id VARCHAR(16) NOT NULL,
  user_id BIGINT NOT NULL,
  original_name VARCHAR(255) NOT NULL,
  category VARCHAR(10) NOT NULL,
  size BIGINT NOT NULL,
  chunk_size INT NOT NULL,
  total_chunks INT NOT NULL,
  received TEXT NULL,
  remark VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  expires_at DATETIME NOT NULL,
  PRIMARY KEY (id),
  KEY ix_chunk_upload_order (order_id),
  KEY ix_chunk_upload_user (user_id),
  KEY ix_chunk_upload_expires (expires_at),
  CONSTRAINT fk_chunk_upload_order FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
  CONSTRAINT fk_chunk_upload_user FOREIGN KEY (user_id) REFERENCES sys_user (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------- 索引补齐（仅当不存在） ----------
SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE orders ADD INDEX ix_orders_deleted (is_deleted)',
    'SELECT 1')
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'orders' AND INDEX_NAME = 'ix_orders_deleted'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE orders ADD INDEX ix_orders_category (category)',
    'SELECT 1')
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'orders' AND INDEX_NAME = 'ix_orders_category'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE sys_user ADD INDEX ix_user_parent (parent_id)',
    'SELECT 1')
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @dbname AND TABLE_NAME = 'sys_user' AND INDEX_NAME = 'ix_user_parent'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
