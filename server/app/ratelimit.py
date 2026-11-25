"""限流：Redis 固定窗口（多 worker 共享）+ 进程内滑动窗口回退。

IP 解析默认只信任直连地址；只有显式开启 TRUST_PROXY_HEADERS 且请求来自
TRUSTED_PROXIES 时，才从 X-Forwarded-For 右侧向内取第一个非可信地址。
"""
from __future__ import annotations

import ipaddress
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .config import TRUST_PROXY_HEADERS, TRUSTED_PROXIES
from .redis_client import get_sync_redis

_MEMORY: dict[str, deque[float]] = defaultdict(deque)
_LOCK = threading.Lock()
_LAST_CLEAN = 0.0
_CLEAN_INTERVAL = 300.0


def _cleanup(now: float) -> None:
    global _LAST_CLEAN
    if now - _LAST_CLEAN < _CLEAN_INTERVAL:
        return
    _LAST_CLEAN = now
    stale = [key for key, q in _MEMORY.items() if not q or now - q[-1] > 3600]
    for key in stale:
        _MEMORY.pop(key, None)


def rate_limit(request: Request, scope: str, key: str, limit: int, window_seconds: int) -> None:
    """固定窗口限流；超过阈值抛 429。"""
    redis = get_sync_redis()
    bucket = f"bs:rl:{scope}:{key}"
    if redis is not None:
        try:
            count = int(redis.incr(bucket))
            if count == 1:
                redis.expire(bucket, window_seconds)
            if count > limit:
                raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
            return
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001 —— Redis 故障时回退内存
            pass

    now = time.monotonic()
    with _LOCK:
        _cleanup(now)
        q = _MEMORY[bucket]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
        q.append(now)


def _trusted(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for item in TRUSTED_PROXIES:
        try:
            if "/" in item:
                if addr in ipaddress.ip_network(item, strict=False):
                    return True
            elif addr == ipaddress.ip_address(item):
                return True
        except ValueError:
            continue
    return False


def client_ip(request: Request) -> str:
    direct = request.client.host if request.client else "unknown"
    if not TRUST_PROXY_HEADERS or not _trusted(direct):
        return direct
    xff = request.headers.get("x-forwarded-for", "")
    if not xff:
        return direct
    hops = [part.strip() for part in xff.split(",") if part.strip()]
    for hop in reversed(hops):
        if not _trusted(hop):
            return hop
    return direct
