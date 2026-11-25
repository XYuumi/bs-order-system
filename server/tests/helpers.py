"""测试专用账号口令：优先读环境变量，未配置时每个会话随机生成，避免源码出现凭据。"""
from __future__ import annotations

import os
import secrets

ADMIN_PASSWORD = os.environ.get("BSC_TEST_ADMIN_PASSWORD") or secrets.token_urlsafe(18)
STAFF_PASSWORD = os.environ.get("BSC_TEST_STAFF_PASSWORD") or secrets.token_urlsafe(18)
AGENT_PASSWORD = os.environ.get("BSC_TEST_AGENT_PASSWORD") or secrets.token_urlsafe(18)
TEMP_PASSWORD = os.environ.get("BSC_TEST_TEMP_PASSWORD") or secrets.token_urlsafe(18)
