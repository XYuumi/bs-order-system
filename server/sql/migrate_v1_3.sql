-- v1.3 迁移：订单工种分类 + 用户 API 拉取类别权限
-- 执行方式（server 目录）：
--   mysql -uroot -p bs_order_system < sql/migrate_v1_3.sql

-- 订单工种：code=计算机/程序设计  design=艺术设计  thesis=纯论文
ALTER TABLE orders ADD COLUMN category VARCHAR(10) NOT NULL DEFAULT 'thesis';
ALTER TABLE orders ADD INDEX ix_orders_category (category);

-- 用户（代理/写手）API 可拉取的订单类别，CSV 存储，空=全部（code,design,thesis）
ALTER TABLE sys_user ADD COLUMN api_categories VARCHAR(60) NULL;
