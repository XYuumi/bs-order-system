"""跨模块共享的业务状态口径。

同一口径必须只定义一处：工作台、统计、对账单、AI 工具与公开大屏共用，
避免售后单在某个入口被漏算/追溯抹掉。
"""
from __future__ import annotations

# 原始需求全文（建单/编辑入参、上传需求书后保存）的字符上限。
# 只定义一处：接口校验的上限必须与实际保存的上限一致，否则会出现“收下了却悄悄截断”。
SOURCE_REQUIREMENT_MAX_CHARS = 20_000

# 已结单/售后都代表财务已结，必须计入营收、结单数与对账。
CLOSED_STATUSES = ("closed", "after_sale")
# 制作已完成（含后续结单/售后）的口径，用于交付数、大屏动态。
DONE_STATUSES = ("completed", "closed", "after_sale")
