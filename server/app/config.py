"""全局配置：从项目根目录 .env 读取。"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]  # 项目根目录
load_dotenv(BASE_DIR / ".env")

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "bs_order_system")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "46127"))
JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
# 默认/过短的密钥意味着任何人都能离线伪造管理员 token（同时它还是交付签名与备份派生的根密钥）。
WEAK_JWT_SECRETS = {"", "change-me", "changeme", "secret", "your-secret-key", "123456"}
INSECURE_JWT_SECRET = JWT_SECRET in WEAK_JWT_SECRETS or len(JWT_SECRET) < 32
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

# 可选 Redis：配置后 WebSocket 广播与限流跨进程共享，多 worker 必须配置。
REDIS_URL = os.getenv("REDIS_URL", "").strip()
# 仅当请求确实经过可信反向代理时才解析 X-Forwarded-For（逗号分隔 IP/CIDR）。
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"
TRUSTED_PROXIES = {
    item.strip() for item in os.getenv("TRUSTED_PROXIES", "127.0.0.1,::1").split(",") if item.strip()
}

# 允许的浏览器来源（开发默认本机；生产同源部署可留空）
ALLOWED_ORIGINS = [
    item.strip()
    for item in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:46127,http://127.0.0.1:46127",
    ).split(",")
    if item.strip()
]

# 备份加密：未配置时从 JWT_SECRET 派生；更换 JWT_SECRET 前请先导出备份密钥。
BACKUP_ENCRYPTION_KEY = os.getenv("BACKUP_ENCRYPTION_KEY", "").strip()

SERVER_DIR = BASE_DIR / "server"
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(SERVER_DIR / "data" / "uploads"))).resolve()
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", str(SERVER_DIR / "backups"))).resolve()

# 分片上传：单文件上限、分片数上限、会话有效期
CHUNK_MAX_MB = int(os.getenv("CHUNK_MAX_MB", "6144"))
CHUNK_MAX_PARTS = int(os.getenv("CHUNK_MAX_PARTS", "4096"))
CHUNK_TTL_HOURS = int(os.getenv("CHUNK_TTL_HOURS", "48"))

# AI 每日调用上限（0 = 不限制）
AI_DAILY_QUOTA = int(os.getenv("AI_DAILY_QUOTA", "0"))
AI_RATE_PER_MINUTE = int(os.getenv("AI_RATE_PER_MINUTE", "30"))

MAX_UPLOAD_MB = {
    "package": int(os.getenv("MAX_UPLOAD_PACKAGE_MB", "2048")),
    "video": int(os.getenv("MAX_UPLOAD_VIDEO_MB", "6144")),
    "doc": int(os.getenv("MAX_UPLOAD_DOC_MB", "1024")),
    "other": int(os.getenv("MAX_UPLOAD_DOC_MB", "1024")),
    # 论文交付物（任务书/开题报告/初稿/终稿留档），只在论文进度接口中上传
    "paper": int(os.getenv("MAX_UPLOAD_DOC_MB", "1024")),
}

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip()
DEEPSEEK_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "180"))

ADMIN_INITIAL_PASSWORD = os.getenv("ADMIN_INITIAL_PASSWORD", "").strip()

# 上传扩展名白名单
ALLOWED_EXTS = {
    "package": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "video": {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm", ".m4v"},
    "doc": {".doc", ".docx", ".pdf", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md"},
    "other": {".zip", ".rar", ".7z", ".tar", ".gz", ".mp4", ".avi", ".mov", ".mkv", ".wmv",
              ".flv", ".webm", ".m4v", ".doc", ".docx", ".pdf", ".xls", ".xlsx", ".ppt",
              ".pptx", ".txt", ".md", ".sql", ".png", ".jpg", ".jpeg"},
    "paper": {".doc", ".docx", ".pdf", ".txt", ".md"},
}

# 订单状态
ORDER_STATUSES = ["pending", "in_progress", "completed", "closed", "after_sale", "cancelled"]
DEPLOY_STATUSES = ["undeployed", "deployed", "not_required"]
