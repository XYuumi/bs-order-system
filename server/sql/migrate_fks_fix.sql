-- FK 迁移补丁（修复首轮 3 个失败项）：
-- 1) requirement_version 表字符集与 orders 不一致 → 统一为 utf8mb4_0900_ai_ci
-- 2) suggestion.user_id / order_file.uploaded_by 原为 NOT NULL，SET NULL 外键要求可空 → 改为可空
-- 3) 重试三条失败的外键
ALTER TABLE `requirement_version` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
ALTER TABLE `suggestion` MODIFY `user_id` BIGINT NULL;
ALTER TABLE `order_file` MODIFY `uploaded_by` BIGINT NULL;
ALTER TABLE `requirement_version` ADD CONSTRAINT `fk_requirement_version_order_id` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE CASCADE;
ALTER TABLE `suggestion` ADD CONSTRAINT `fk_suggestion_user_id` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL;
ALTER TABLE `order_file` ADD CONSTRAINT `fk_order_file_uploaded_by` FOREIGN KEY (`uploaded_by`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL;
