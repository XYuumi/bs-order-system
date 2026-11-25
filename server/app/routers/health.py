"""系统健康检查：管理员视角的关键依赖与资源探活。

所有探测均为只读，单项失败只会在 checks 里体现为 warn/fail，
接口本身始终返回 200，避免探活请求把监控面板打成 500。
"""
from __future__ import annotations

import os
import shutil
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import text

from ..config import BACKUP_DIR, UPLOAD_DIR
from ..database import SessionLocal
from ..deps import require_admin
from ..models import User
from ..services.backup_svc import FILE_PREFIX

router = APIRouter(prefix="/api/admin", tags=["health"])

# 本模块在应用启动时被 main.py 导入，用单调时钟估算进程运行时长（不受系统时间跳变影响）。
_STARTED_AT = time.monotonic()

UPLOAD_FREE_WARN_BYTES = 1 * 1024 ** 3
DISK_USED_WARN_PCT = 85.0
DISK_USED_FAIL_PCT = 95.0
BACKUP_STALE_DAYS = 7

CheckFn = Callable[[], tuple[str, str]]


def _app_version() -> str:
    # APP_VERSION 定义在 main.py；延迟导入避免 routers -> main 的循环导入。
    try:
        from ..main import APP_VERSION
    except Exception:  # noqa: BLE001 —— 版本号拿不到不该影响探活
        return "unknown"
    return str(APP_VERSION)


def _gb(size: int | float) -> str:
    return f"{float(size) / (1024 ** 3):.2f} GB"


def _existing_ancestor(path: Path) -> Path:
    """上传目录可能尚未创建，磁盘统计回退到最近的存在目录。"""
    current = path
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


def _disk_usage(path: Path):
    return shutil.disk_usage(str(path))


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda _exc: None):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total


def _check_db() -> tuple[str, str]:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1")).scalar_one()
    finally:
        db.close()
    return "ok", "SELECT 1 正常，数据库连接可用"


def _check_redis() -> tuple[str, str]:
    from ..redis_client import get_sync_redis, redis_configured

    if not redis_configured():
        # 单机部署不配置 Redis 是受支持的默认形态（进程内限流/广播），
        # 不应把整体健康度标成「存在异常」；配置了但连不上才需要告警。
        return "ok", "未配置（单机可选），实时推送与限流使用进程内实现"
    client = get_sync_redis()
    if client is None:
        return "fail", "已配置 REDIS_URL，但连接不可用（详见服务端日志）"
    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001 —— 连接中断按 fail 返回，不抛给接口
        return "fail", f"PING 失败：{exc}"
    return "ok", "已连接，跨进程实时推送/限流可用"


def _check_uploads() -> tuple[str, str]:
    if not UPLOAD_DIR.is_dir():
        return "warn", "上传目录不存在，首次上传时会自动创建"
    size = _dir_size(UPLOAD_DIR)
    free = int(_disk_usage(UPLOAD_DIR).free)
    detail = f"占用 {_gb(size)} · 磁盘剩余 {_gb(free)}"
    if free < UPLOAD_FREE_WARN_BYTES:
        return "warn", detail + "，低于 1 GB 告警阈值"
    return "ok", detail


def _backup_files() -> list[Path]:
    if not BACKUP_DIR.is_dir():
        return []
    return [p for p in BACKUP_DIR.glob(FILE_PREFIX + "*") if p.is_file()]


def _check_backups() -> tuple[str, str]:
    files = _backup_files()
    if not files:
        return "warn", "暂无备份，建议在「数据备份」页立即创建"
    latest = max(files, key=lambda p: p.stat().st_mtime)
    mtime = latest.stat().st_mtime
    days = (time.time() - mtime) / 86400
    stamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
    detail = f"共 {len(files)} 份 · 最近备份 {stamp}"
    if days > BACKUP_STALE_DAYS:
        return "warn", detail + f"（距今 {int(days)} 天，超过 7 天阈值）"
    return "ok", detail


def _check_ws() -> tuple[str, str]:
    from .. import ws

    connections = getattr(ws, "_CONNECTIONS", None) or {}
    count = sum(len(items) for items in connections.values())
    return "ok", f"当前 {count} 个在线连接（仅统计本进程）"


def _check_disk() -> tuple[str, str]:
    usage = _disk_usage(_existing_ancestor(UPLOAD_DIR))
    total = max(int(usage.total), 1)
    used = int(usage.used)
    pct = used / total * 100
    detail = f"使用率 {pct:.1f}%（已用 {_gb(used)} / 共 {_gb(total)}）"
    if pct >= DISK_USED_FAIL_PCT:
        return "fail", detail + "，超过 95% 危险阈值"
    if pct > DISK_USED_WARN_PCT:
        return "warn", detail + "，超过 85% 告警阈值"
    return "ok", detail


def _run_check(key: str, label: str, fn: CheckFn) -> dict:
    started = time.perf_counter()
    try:
        status, detail = fn()
    except Exception as exc:  # noqa: BLE001 —— 单项异常不能拖垮整个接口
        status, detail = "fail", f"检查执行异常：{type(exc).__name__}: {exc}"
    if status not in ("ok", "warn", "fail"):
        status = "warn"
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def _collect_checks() -> list[dict]:
    return [
        _run_check("db", "数据库", _check_db),
        _run_check("redis", "Redis", _check_redis),
        _run_check("uploads", "上传存储", _check_uploads),
        _run_check("backups", "数据备份", _check_backups),
        _run_check("ws", "实时连接", _check_ws),
        _run_check("disk", "磁盘空间", _check_disk),
    ]


@router.get("/health")
def system_health(admin: User = Depends(require_admin)):
    """系统健康检查（仅管理员）：任一检查异常只降级为 degraded。"""
    checks = _collect_checks()
    overall = "ok" if all(item["status"] == "ok" for item in checks) else "degraded"
    return {
        "status": overall,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "uptime_seconds": int(time.monotonic() - _STARTED_AT),
        "version": _app_version(),
        "checks": checks,
    }
