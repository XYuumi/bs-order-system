"""WebSocket 实时推送：站内通知 + 私信 + 订单事件。

- Cookie JWT 鉴权，连接时校验用户启用状态与 token_version；
- 多 worker 部署时配置 REDIS_URL，通过 Redis pub/sub 跨进程广播；
- 事件只在数据库事务提交后推送，避免“先收到通知、DB 里还查不到”；
- 强制下线（改密/停用/退出所有设备）通过 force_logout 事件关闭在线连接。
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from urllib.parse import urlparse

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import event
from sqlalchemy.orm import Session

from .config import ALLOWED_ORIGINS
from .database import SessionLocal
from .models import User
from .redis_client import get_async_redis
from .security import ALGORITHM, JWT_SECRET

log = logging.getLogger("bs.ws")

_CONNECTIONS: dict[int, set[WebSocket]] = defaultdict(set)
_LOCK = asyncio.Lock()
_MAIN_LOOP: asyncio.AbstractEventLoop | None = None
_REDIS_TASK: asyncio.Task | None = None
REDIS_CHANNEL = "bs:ws"
MAX_MESSAGE_BYTES = 2048
IDLE_TIMEOUT_SECONDS = 120


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _MAIN_LOOP
    _MAIN_LOOP = loop


def current_online(user_id: int) -> bool:
    return bool(_CONNECTIONS.get(user_id))


async def _send_to(ws: WebSocket, payload: dict) -> bool:
    try:
        await ws.send_text(json.dumps(payload, ensure_ascii=False, default=str))
        if payload.get("type") == "force_logout":
            await ws.close(code=4401, reason="session revoked")
        return True
    except Exception:  # noqa: BLE001 —— 连接已断开等
        return False


async def _broadcast_local(user_ids: list[int], payload: dict) -> None:
    for uid in dict.fromkeys(user_ids):
        sockets = list(_CONNECTIONS.get(uid, ()))
        if not sockets:
            continue
        results = await asyncio.gather(*(_send_to(ws, payload) for ws in sockets), return_exceptions=True)
        dead = [ws for ws, ok in zip(sockets, results) if ok is not True]
        if dead:
            async with _LOCK:
                for ws in dead:
                    _CONNECTIONS[uid].discard(ws)
                if not _CONNECTIONS[uid]:
                    _CONNECTIONS.pop(uid, None)


async def publish_ws(user_ids: list[int], payload: dict) -> None:
    """发布事件：配置 Redis 时交给 pub/sub（全 worker 可达），否则本地广播。"""
    targets = [int(uid) for uid in dict.fromkeys(user_ids) if uid]
    if not targets:
        return
    redis = get_async_redis()
    if redis is not None:
        try:
            await redis.publish(REDIS_CHANNEL, json.dumps({"targets": targets, "payload": payload}, ensure_ascii=False, default=str))
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("Redis 发布失败，回退本地广播：%s", exc)
    await _broadcast_local(targets, payload)


def publish_ws_sync(user_ids: list[int], payload: dict) -> None:
    """同步端点（线程池）中调度回主事件循环。"""
    loop = _MAIN_LOOP
    if not loop or loop.is_closed():
        return
    try:
        asyncio.run_coroutine_threadsafe(publish_ws(user_ids, payload), loop)
    except RuntimeError:
        pass


def queue_ws_event(db: Session, user_ids: list[int], payload: dict) -> None:
    """把事件挂到当前事务，commit 后自动推送；rollback 则丢弃。"""
    targets = [int(uid) for uid in dict.fromkeys(user_ids) if uid]
    if targets:
        db.info.setdefault("_ws_events", []).append((targets, payload))


@event.listens_for(Session, "after_commit")
def _flush_ws_events(session: Session) -> None:
    pending = session.info.pop("_ws_events", [])
    for targets, payload in pending:
        publish_ws_sync(targets, payload)


@event.listens_for(Session, "after_rollback")
def _drop_ws_events(session: Session) -> None:
    session.info.pop("_ws_events", None)


def force_logout_user(user_id: int) -> None:
    """通知所有 worker 关闭该用户的在线连接。"""
    publish_ws_sync([user_id], {"type": "force_logout", "message": "登录状态已失效，请重新登录"})


async def _redis_reader() -> None:
    redis = get_async_redis()
    if redis is None:
        return
    while True:
        try:
            pubsub = redis.pubsub()
            await pubsub.subscribe(REDIS_CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    await _broadcast_local(data.get("targets") or [], data.get("payload") or {})
                except (ValueError, TypeError, KeyError):
                    continue
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("Redis 订阅断开，3 秒后重连：%s", exc)
            await asyncio.sleep(3)


async def startup_realtime() -> None:
    global _REDIS_TASK
    set_main_loop(asyncio.get_running_loop())
    if get_async_redis() is not None and _REDIS_TASK is None:
        _REDIS_TASK = asyncio.create_task(_redis_reader())


async def shutdown_realtime() -> None:
    global _REDIS_TASK
    if _REDIS_TASK is not None:
        _REDIS_TASK.cancel()
        try:
            await _REDIS_TASK
        except asyncio.CancelledError:
            pass
        _REDIS_TASK = None


def _origin_allowed(websocket: WebSocket) -> bool:
    origin = (websocket.headers.get("origin") or "").strip()
    if not origin:
        return True  # 非浏览器客户端（脚本/移动端）通常不带 Origin
    if origin in ALLOWED_ORIGINS:
        return True
    try:
        host = (websocket.headers.get("host") or "").split(":")[0]
        return urlparse(origin).hostname == host
    except ValueError:
        return False


async def ws_endpoint(websocket: WebSocket) -> None:
    """Cookie 鉴权后注册连接；断开时清理。"""
    import jwt as pyjwt

    if not _origin_allowed(websocket):
        await websocket.close(code=4403)
        return

    token = websocket.cookies.get("token") or ""
    user_id = 0
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub") or 0)
        token_ver = int(payload.get("ver", 0) or 0)
    except Exception:  # noqa: BLE001 —— 无效/过期 token
        token_ver = -1

    db = SessionLocal()
    try:
        user = db.get(User, user_id) if user_id else None
        if not user or not user.is_active or int(user.token_version or 0) != token_ver:
            await websocket.close(code=4401)
            return
    finally:
        db.close()

    await websocket.accept()
    async with _LOCK:
        _CONNECTIONS[user_id].add(websocket)
    try:
        await _send_to(websocket, {"type": "hello", "user_id": user_id})
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=IDLE_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                break
            if len(msg.encode("utf-8")) > MAX_MESSAGE_BYTES:
                break
            if msg == "ping":
                await _send_to(websocket, {"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        async with _LOCK:
            _CONNECTIONS[user_id].discard(websocket)
            if not _CONNECTIONS[user_id]:
                _CONNECTIONS.pop(user_id, None)
