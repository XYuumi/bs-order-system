-- v1.2 迁移：软删除/需求书版本/多级代理抽成
-- 执行方式（server 目录）：
--   mysql -uroot -p bs_order_system < sql/migrate_v1_2.sql

ALTER TABLE orders ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE orders ADD INDEX ix_orders_deleted (is_deleted);

CREATE TABLE IF NOT EXISTS requirement_version (
  id BIGINT NOT NULL AUTO_INCREMENT,
  order_id VARCHAR(16) NOT NULL,
  document LONGTEXT NULL,
  source VARCHAR(10) NULL,
  created_by BIGINT NULL,
  username VARCHAR(50) NOT NULL DEFAULT '-',
  remark VARCHAR(200) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX ix_reqver_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE sys_user ADD COLUMN parent_id BIGINT NULL;
ALTER TABLE sys_user ADD COLUMN commission_rate DECIMAL(5,2) NOT NULL DEFAULT 0;
ALTER TABLE sys_user ADD INDEX ix_user_parent (parent_id);
