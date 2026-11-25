"""Webhook 通知：新订单 / 状态变更 推送到企业微信、钉钉等群机器人（text 消息格式）。"""
from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from ..models import Setting
from .settings_svc import get_setting
from ..urlguard import assert_safe_url

STATUS_CN = {
    "pending": "待开始", "in_progress": "制作中", "completed": "已完成",
    "closed": "已结单", "after_sale": "售后中", "cancelled": "已取消",
}


def _enabled(db: Session) -> str | None:
    url = (get_setting(db, "webhook_url") or "").strip()
    return url if url else None


def notify_order_created(order_id: str, title: str, agent_name: str | None, price: float) -> None:
    """在后台任务中调用（独立会话由调用方保证已提交）。"""
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        url = _enabled(db)
        if not url:
            return
        try:
            assert_safe_url(url)
        except ValueError:
            return
        agent_part = f"（代理：{agent_name}）" if agent_name else ""
        text = f"【毕设接单】新订单 {order_id}\n题目：{title}{agent_part}\n代理价：¥{price}"
        _post(url, text)
    except Exception:
        pass  # 通知失败不影响业务
    finally:
        db.close()


def notify_status_changed(order_id: str, title: str, old: str, new: str) -> None:
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        url = _enabled(db)
        if not url:
            return
        try:
            assert_safe_url(url)
        except ValueError:
            return
        text = f"【毕设接单】订单状态变更 {order_id}\n题目：{title}\n{STATUS_CN.get(old, old)} → {STATUS_CN.get(new, new)}"
        _post(url, text)
    except Exception:
        pass
    finally:
        db.close()


def _post(url: str, text: str) -> bool:
    # 企业微信/钉钉群机器人的 text 消息格式一致
    assert_safe_url(url)
    payload = {"msgtype": "text", "text": {"content": text}}
    with httpx.Client(timeout=8, follow_redirects=False) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        return True


def send_text(db, text: str) -> bool:
    """通用文本通知（备份完成 / Token 超限告警等），未配置 webhook 时静默。

    接收已打开的 db 会话读取配置；网络发送失败静默（不阻塞业务）。
    """
    url = _enabled(db)
    if not url:
        return False
    try:
        return _post(url, text)
    except Exception:  # noqa: BLE001
        return False
