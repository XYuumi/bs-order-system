-- v1.1 迁移：quality 表增加自定义价字段（可空，不填则按 基础价×倍率）
-- 执行方式（server 目录）：
--   mysql -uroot -p bs_order_system < sql/migrate_v1_1.sql
ALTER TABLE quality ADD COLUMN owner_price_override DECIMAL(10,2) NULL;
ALTER TABLE quality ADD COLUMN agent_price_override DECIMAL(10,2) NULL;
