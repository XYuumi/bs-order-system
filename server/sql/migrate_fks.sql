-- 外键约束迁移（v1.11）：给存量表补 FK；先清理孤儿引用再加约束。
-- 幂等性：重复执行时已存在的约束会报 1826/1061 类错误，可忽略。
-- 执行：server 目录 .venv/Scripts/python.exe scripts/run_sql.py sql/migrate_fks.sql

-- 1) 孤儿数据清理（SET NULL / CASCADE 类）
UPDATE `orders` SET `agent_user_id` = NULL WHERE `agent_user_id` IS NOT NULL AND `agent_user_id` NOT IN (SELECT `id` FROM `sys_user`);
UPDATE `orders` SET `assignee_user_id` = NULL WHERE `assignee_user_id` IS NOT NULL AND `assignee_user_id` NOT IN (SELECT `id` FROM `sys_user`);
UPDATE `sys_user` SET `parent_id` = NULL WHERE `parent_id` IS NOT NULL AND `parent_id` NOT IN (SELECT `id` FROM `sys_user`);
UPDATE `order_file` SET `uploaded_by` = NULL WHERE `uploaded_by` IS NOT NULL AND `uploaded_by` NOT IN (SELECT `id` FROM `sys_user`);
UPDATE `order_note` SET `user_id` = NULL WHERE `user_id` IS NOT NULL AND `user_id` NOT IN (SELECT `id` FROM `sys_user`);
UPDATE `suggestion` SET `user_id` = NULL WHERE `user_id` IS NOT NULL AND `user_id` NOT IN (SELECT `id` FROM `sys_user`);
DELETE FROM `order_file` WHERE `order_id` IS NOT NULL AND `order_id` NOT IN (SELECT `id` FROM `orders`);
DELETE FROM `order_note` WHERE `order_id` IS NOT NULL AND `order_id` NOT IN (SELECT `id` FROM `orders`);
DELETE FROM `requirement_version` WHERE `order_id` IS NOT NULL AND `order_id` NOT IN (SELECT `id` FROM `orders`);
DELETE FROM `notification` WHERE `user_id` IS NOT NULL AND `user_id` NOT IN (SELECT `id` FROM `sys_user`);
DELETE FROM `chat_message` WHERE `from_id` IS NOT NULL AND `from_id` NOT IN (SELECT `id` FROM `sys_user`);
DELETE FROM `chat_message` WHERE `to_id` IS NOT NULL AND `to_id` NOT IN (SELECT `id` FROM `sys_user`);

-- 2) 订单 → 品质 / 用户
ALTER TABLE `orders` ADD CONSTRAINT `fk_orders_quality_id` FOREIGN KEY (`quality_id`) REFERENCES `quality` (`id`) ON DELETE RESTRICT;
ALTER TABLE `orders` ADD CONSTRAINT `fk_orders_agent_user_id` FOREIGN KEY (`agent_user_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL;
ALTER TABLE `orders` ADD CONSTRAINT `fk_orders_assignee_user_id` FOREIGN KEY (`assignee_user_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL;
ALTER TABLE `orders` ADD CONSTRAINT `fk_orders_created_by` FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`) ON DELETE RESTRICT;

-- 3) 用户自引用（多级代理）
ALTER TABLE `sys_user` ADD CONSTRAINT `fk_sys_user_parent_id` FOREIGN KEY (`parent_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL;

-- 4) 订单附属（级联删除）
ALTER TABLE `order_file` ADD CONSTRAINT `fk_order_file_order_id` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE CASCADE;
ALTER TABLE `order_file` ADD CONSTRAINT `fk_order_file_uploaded_by` FOREIGN KEY (`uploaded_by`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL;
ALTER TABLE `order_note` ADD CONSTRAINT `fk_order_note_order_id` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE CASCADE;
ALTER TABLE `order_note` ADD CONSTRAINT `fk_order_note_user_id` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL;
ALTER TABLE `requirement_version` ADD CONSTRAINT `fk_requirement_version_order_id` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE CASCADE;

-- 5) 消息类
ALTER TABLE `notification` ADD CONSTRAINT `fk_notification_user_id` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE CASCADE;
ALTER TABLE `suggestion` ADD CONSTRAINT `fk_suggestion_user_id` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL;
ALTER TABLE `chat_message` ADD CONSTRAINT `fk_chat_message_from_id` FOREIGN KEY (`from_id`) REFERENCES `sys_user` (`id`) ON DELETE CASCADE;
ALTER TABLE `chat_message` ADD CONSTRAINT `fk_chat_message_to_id` FOREIGN KEY (`to_id`) REFERENCES `sys_user` (`id`) ON DELETE CASCADE;
