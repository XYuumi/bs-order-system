"""可选 Redis 连接：多 worker 的 WebSocket 广播与共享限流。

未配置 REDIS_URL 时所有调用方自动回退到进程内实现。Redis 连接失败也不会阻止
应用启动（只记录告警），便于本机开发和单 worker 部署。
"""
from __future__ import annotations

import logging

from .config import REDIS_URL

log = logging.getLogger("bs.redis")

_sync_client = None
_async_client = None


def redis_configured() -> bool:
    return bool(REDIS_URL)


def get_sync_redis():
    return _sync_client


def get_async_redis():
    return _async_client


async def init_redis() -> None:
    global _sync_client, _async_client
    if not REDIS_URL:
        log.info("REDIS_URL 未配置，WebSocket/限流使用进程内实现")
        return
    try:
        import redis as sync_redis
        import redis.asyncio as async_redis

        _sync_client = sync_redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
        _sync_client.ping()
        _async_client = async_redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
        await _async_client.ping()
        log.info("Redis 已连接：跨进程实时推送/限流已启用")
    except Exception as exc:  # noqa: BLE001
        _sync_client = None
        _async_client = None
        log.warning("Redis 连接失败，回退进程内实现：%s", exc)


async def close_redis() -> None:
    global _sync_client, _async_client
    try:
        if _async_client is not None:
            await _async_client.aclose()
    except Exception:  # noqa: BLE001
        pass
    try:
        if _sync_client is not None:
            _sync_client.close()
    except Exception:  # noqa: BLE001
        pass
    _sync_client = None
    _async_client = None
