-- v1.24.2 订单原始需求资料
-- 客户上传需求文档的提取全文（AI 生成需求书的基准）与口头需求要点总结
ALTER TABLE orders ADD COLUMN source_requirement LONGTEXT NULL AFTER remark;
ALTER TABLE orders ADD COLUMN requirement_notes TEXT NULL AFTER source_requirement;
