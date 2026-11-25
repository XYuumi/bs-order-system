# 代理对接 API 说明

代理可在网页「API 对接」页查看专属 Key 与可复制的示例（本文为离线版说明）。

> v1.16 新增的模板库、系统健康、Excel 导入导出、毛利分析、交期风险、验收单 PDF，以及 v1.21 的状态撤回/审批，均属于登录态管理端接口，不在代理 `/api/v1` 范围内；其入口、权限与请求格式见 [新增功能说明](./新增功能说明.md)。

## 认证

- 请求头：`X-API-Key: 你的Key`（或 `Authorization: Bearer 你的Key`）
- Key 在「API 对接」页自助查看/重置；重置后旧 Key 立即失效
- 频率限制：每分钟 120 次，超限返回 429
- 价格视野：管理员可见 `owner_price` + `agent_price`；代理/写手只返回 `agent_price`
- 订单范围：代理只能访问自己的订单；写手/管理员可访问全部订单
- 状态回传：仅写手/管理员可调用，代理调用返回 403。写手仅 `pending→in_progress`、`pending→completed`、`in_progress→completed`；管理员除已取消外可改为任意状态；`cancelled` 为所有人终态。回退（如已完成→制作中）不由本接口提供，走管理端撤回审批。

## 基础地址

`https://你的域名/api/v1`

## 接口列表

### GET /qualities 品质列表

```bash
curl "https://域名/api/v1/qualities" -H "X-API-Key: $你的KEY"
```

返回：`{"qualities":[{"code":"green","name":"绿色","multiplier":2,"agent_price":100,...}]}`

### GET /orders 我的订单列表

Query 参数：`status`（pending/in_progress/completed/closed/after_sale/cancelled）、`keyword`、`page`、`page_size`

```bash
curl "https://域名/api/v1/orders?status=in_progress&page=1" -H "X-API-Key: $你的KEY"
```

### POST /orders 创建订单

```bash
curl -X POST "https://域名/api/v1/orders" \
  -H "X-API-Key: $你的KEY" \
  -H "Content-Type: application/json" \
  -d '{"title":"基于SpringBoot的图书管理系统设计与实现","quality_code":"green","deadline":"2026-12-20","tech_stack":"SpringBoot+Vue3","remark":"客户催得急"}'
```

Body 字段：`title`（必填 2~255 字）、`quality_code`（必填）、`deadline`（YYYY-MM-DD）、`tech_stack`、`remark`。
返回：`{"order":{"id":"260101-001","agent_price":100,"status":"pending",...}}`

### GET /orders/{id} 订单详情

### POST /orders/{id}/status 回传制作状态（写手/管理员）

```bash
curl -X POST "https://域名/api/v1/orders/260101-001/status" \
  -H "X-API-Key: $你的KEY" -H "Content-Type: application/json" \
  -d '{"status":"in_progress","note":"开始开发"}'
```

状态按角色白名单变更：

| 角色 | 允许的目标状态 |
| --- | --- |
| 管理员 | 除已取消外任意状态（含已完成/已结单回退到制作中、待开始）；回退会清理不再适用的完成/结单时间；已取消不可恢复 |
| 写手 | `pending→in_progress`、`pending→completed`、`in_progress→completed`；仅本人负责或未分派订单 |
| 代理 | 禁止，403 |

- `closed`/`after_sale` 仅管理员可操作；`cancelled` 对所有人都是终态，不可恢复。
- 回退不能通过本接口完成：管理员直接在订单详情改状态；写手在订单详情提交「撤回申请」，由管理员审批后生效。
- 管理员可通过本接口直接设置除已取消外的任意目标状态，但页面上仍建议走状态按钮，便于记录操作日志与通知。

### GET /orders/{id}/requirement.docx 下载需求书 Word

未生成时返回 404，稍后重试即可。

### GET /orders/{id}/files 附件列表

Query：`category`（package/video/doc/other）

### POST /orders/{id}/files 上传交付物（写手/管理员）

`multipart/form-data`：`file`、`category`、可选 `remark`。

### GET /files/{file_id}/download 下载附件

演示视频支持 Range 断点/拖动。

## 错误码

| 状态码 | 含义 |
|---|---|
| 401 | 缺少 / 无效 API Key |
| 403 | 访问了不属于你的订单 |
| 404 | 订单或资源不存在（如需求书尚未生成） |
| 429 | 请求过于频繁 |

## 对接建议

- 拉单轮询建议 ≥30 秒一次
- 创建订单后把返回的单号 `id` 存下来，用详情接口跟踪状态
- 状态值映射：pending 待开始 / in_progress 制作中 / completed 已完成 / closed 已结单 / after_sale 售后中 / cancelled 已取消

## 管理端：状态撤回与审批（登录态，非 /api/v1）

以下接口使用登录会话（Cookie/Bearer 登录令牌），供管理端页面使用，不适用于代理 API Key。

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/orders/{id}/status-revert` | 有订单访问权 | 返回当前待审批申请 `request`（无则 null）、本次可回退目标 `target`、可执行状态 `allowed_statuses` |
| POST | `/api/orders/{id}/status-revert` | 写手（仅负责人） | Body：`{"to_status":"pending|in_progress","reason":"2~300 字"}`；只能回退一步；重复待审批 409；提交后通知所有管理员 |
| GET | `/api/status-reverts?status=pending` | 管理员 | 审批列表（最近 200 条）与 `pending` 计数，用于审计/测试 |
| POST | `/api/status-reverts/{rid}/review` | 管理员 | Body：`{"action":"approve|reject","note":"可选备注"}`；approve 自动回退订单并通知申请人；订单状态已变化则 409 自动失效 |
| POST | `/api/status-reverts/{rid}/cancel` | 申请人 | 仅待审批状态可取消，取消后订单状态不变 |

回退规则：`in_progress→pending`、`completed→in_progress`，即只能撤回最近一步；`closed`/`after_sale` 需管理员处理；`cancelled` 为终态，不可恢复。所有申请、审批、自动失效均写入操作日志。
