-- v1.12 新增列：登录安全（失败计数/锁定/TOTP）+ 客户验收留痕
ALTER TABLE `sys_user` ADD COLUMN `failed_logins` SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE `sys_user` ADD COLUMN `locked_until` DATETIME NULL;
ALTER TABLE `sys_user` ADD COLUMN `totp_secret` VARCHAR(64) NULL;
ALTER TABLE `sys_user` ADD COLUMN `totp_pending` VARCHAR(64) NULL;
ALTER TABLE `orders` ADD COLUMN `customer_accepted_at` DATETIME NULL;
ALTER TABLE `orders` ADD COLUMN `customer_accepted_ip` VARCHAR(45) NULL;
