-- v1.25 论文进度与项目类型
-- 说明：新库无需执行（init_db 直接建全量表）；已有库正常情况下服务启动时会自动补齐，
--       本脚本供手工执行兜底（可重复执行，已存在会报 Duplicate column/index，忽略即可）。

ALTER TABLE `orders`
  ADD COLUMN `project_type` VARCHAR(20) NULL DEFAULT NULL AFTER `category`;

-- 上传需求书应用方式：reference=参考生成（默认/NULL）；direct=原文直接应用不做修改
ALTER TABLE `orders`
  ADD COLUMN `source_apply_mode` VARCHAR(10) NULL DEFAULT NULL AFTER `source_requirement`;

CREATE INDEX `ix_orders_project_type` ON `orders` (`project_type`);

-- 历史订单回填：project_type 为空的按旧工种列映射
-- （纯论文→纯论文；程序/艺术设计→纯程序设计，不改变原无论文流程的行为）。幂等，可重复执行。
UPDATE `orders`
SET `project_type` = CASE WHEN `category` = 'thesis' THEN 'thesis' ELSE 'program' END
WHERE `project_type` IS NULL;

-- 论文交付物留档表（任务书/开题报告/初稿/终稿，每次修改追加一行）
CREATE TABLE IF NOT EXISTS `order_paper_doc` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `order_id` VARCHAR(16) NOT NULL,
  `doc_type` VARCHAR(20) NOT NULL COMMENT 'task_book=任务书 proposal=开题报告 draft=初稿 final=终稿',
  `round` INT NOT NULL DEFAULT 1 COMMENT '该类文档第几版（初稿每次修改+1）',
  `file_id` BIGINT NULL COMMENT '关联 order_file.id（category=paper）',
  `note` VARCHAR(500) NULL COMMENT '修改说明',
  `created_by` BIGINT NULL,
  `username` VARCHAR(50) NOT NULL DEFAULT '-',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_paper_doc_order` (`order_id`, `doc_type`),
  KEY `ix_paper_doc_file` (`file_id`),
  CONSTRAINT `fk_paper_doc_order` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_paper_doc_user` FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
