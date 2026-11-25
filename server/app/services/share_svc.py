"""公开分享页数据：经营大屏（投影/合作方）与代理业绩榜（招商）。

两类页面均不含任何金额与真实价，仅运营规模与质量指标。
token 复用报价单机制：settings 表 KV（screen_token / rank_token），首次取链接时自动生成。
"""
from __future__ import annotations

import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import event
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session, selectinload

from ..constants import CLOSED_STATUSES, DONE_STATUSES
from ..models import Order, Quality, User
from .settings_svc import get_setting, get_settings_map, set_setting

TOKEN_KEYS = {"screen": "screen_token", "rank": "rank_token"}

# 公开大屏/榜单：30 秒进程内缓存，key 含分享类型与 token，命中时不再扫订单表。
CACHE_TTL_SECONDS = 30.0
_cache: dict[tuple[str, str], tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def invalidate_share_cache() -> None:
    """清空公开页缓存：token 轮换、重建或任何写操作提交后调用。"""
    with _cache_lock:
        _cache.clear()


def _cache_get(kind: str, token: str) -> dict | None:
    key = (kind, token)
    now = time.monotonic()
    with _cache_lock:
        item = _cache.get(key)
        if item is None:
            return None
        expires_at, payload = item
        if expires_at <= now:
            _cache.pop(key, None)
            return None
        return payload


def _cache_put(kind: str, token: str, payload: dict) -> None:
    with _cache_lock:
        _cache[(kind, token)] = (time.monotonic() + CACHE_TTL_SECONDS, payload)


@event.listens_for(Session, "after_commit")
def _invalidate_cache_after_commit(session) -> None:  # noqa: ARG001
    """任何写操作提交后立即失效，避免公开页在 TTL 内看到旧数据。"""
    invalidate_share_cache()


def get_share_token(db: Session, kind: str) -> str:
    """只读：读取已生成的分享 token（不写库、不 commit）。"""
    if kind not in TOKEN_KEYS:
        raise ValueError("非法的分享类型")
    return get_setting(db, TOKEN_KEYS[kind]) or ""


def create_share_token(db: Session, kind: str) -> str:
    """写路径：首次生成并持久化分享 token，随后清空公开页缓存。"""
    if kind not in TOKEN_KEYS:
        raise ValueError("非法的分享类型")
    token = secrets.token_urlsafe(12)
    set_setting(db, TOKEN_KEYS[kind], token)
    db.commit()
    invalidate_share_cache()
    return token


def get_or_create_token(db: Session, kind: str) -> str:
    """取分享 token；尚未生成时走 create_share_token 的写路径落库。"""
    return get_share_token(db, kind) or create_share_token(db, kind)


def check_token(db: Session, kind: str, token: str) -> bool:
    saved = get_setting(db, TOKEN_KEYS.get(kind, "")) or ""
    return bool(saved) and hmac.compare_digest(saved, token)


PT_CN = {"program": "纯程序设计", "thesis": "纯论文", "thesis_program": "论文+设计"}


def screen_data(db: Session) -> dict:
    """经营大屏：单量/交付质量/趋势/分布/动态，无金额。"""
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    orders = (
        db.query(Order)
        .filter(Order.is_deleted == False)  # noqa: E712
        .options(selectinload(Order.quality), selectinload(Order.agent))
        .all()
    )
    closed = [o for o in orders if o.status in CLOSED_STATUSES]
    done = [o for o in orders if o.status in DONE_STATUSES]
    month_orders = [o for o in orders if o.created_at and o.created_at >= month_start]
    on_time_total = [o for o in orders if o.completed_at and o.deadline]
    on_time_hit = [o for o in on_time_total if o.completed_at.date() <= o.deadline]
    cycles = [(o.completed_at - o.accepted_at).days for o in closed if o.completed_at and o.accepted_at]

    # 近 12 个月单量
    monthly: dict[str, int] = {}
    for o in orders:
        if o.created_at:
            monthly[o.created_at.strftime("%Y-%m")] = monthly.get(o.created_at.strftime("%Y-%m"), 0) + 1
    y, m = now.year, now.month
    months = []
    for _ in range(12):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()
    trend = [{"month": mk, "orders": monthly.get(mk, 0)} for mk in months]

    pt_counts = {}
    for o in orders:
        key = PT_CN.get(o.project_type, "未设置")
        pt_counts[key] = pt_counts.get(key, 0) + 1

    recent_done = sorted(done, key=lambda o: o.completed_at or datetime.min, reverse=True)[:10]

    return {
        "updated_at": now.strftime("%Y-%m-%d %H:%M"),
        "kpis": {
            "total": len(orders),
            "month_new": len(month_orders),
            "closed": len(closed),
            "close_rate": round(len(closed) / max(len(orders), 1) * 100, 1),
            "on_time_rate": round(len(on_time_hit) / max(len(on_time_total), 1) * 100, 1),
            "avg_cycle_days": round(sum(cycles) / len(cycles), 1) if cycles else 0,
        },
        "trend": trend,
        "project_type_dist": [{"name": k, "value": v} for k, v in pt_counts.items()],
        "recent_done": [
            {"id": o.id, "title": o.title, "project_type": PT_CN.get(o.project_type, o.project_type or "未设置"),
             "quality": o.quality.name if o.quality else "", "done_at": o.completed_at}
            for o in recent_done
        ],
    }


def rank_data(db: Session) -> dict:
    """代理业绩榜：按月单量排名 + 按时交付星级（招商用，无金额）。"""
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    orders = (
        db.query(Order)
        .filter(Order.is_deleted == False)  # noqa: E712
        .options(selectinload(Order.agent))
        .all()
    )
    agents = db.query(User).filter(User.role == "agent", User.is_active == True).all()  # noqa: E712

    stat: dict[int, dict] = {a.id: {"name": a.display_name or a.username, "month": 0, "total": 0, "closed": 0, "on_time": 0, "deadline": 0} for a in agents}
    for o in orders:
        if not o.agent_user_id or o.agent_user_id not in stat:
            continue
        s = stat[o.agent_user_id]
        s["total"] += 1
        if o.created_at and o.created_at >= month_start:
            s["month"] += 1
        if o.status in CLOSED_STATUSES:
            s["closed"] += 1
        if o.completed_at and o.deadline:
            s["deadline"] += 1
            if o.completed_at.date() <= o.deadline:
                s["on_time"] += 1

    month_total = sum(s["month"] for s in stat.values())
    rows = []
    for s in stat.values():
        on_time_rate = round(s["on_time"] / s["deadline"] * 100, 1) if s["deadline"] else None
        stars = round(on_time_rate / 20) if on_time_rate is not None else 4
        rows.append({
            "name": s["name"], "month_count": s["month"], "total": s["total"], "closed": s["closed"],
            "on_time_rate": on_time_rate, "stars": max(1, min(5, stars)),
        })
    rows.sort(key=lambda x: (-x["month_count"], -x["total"]))

    return {
        "month": f"{now.year} 年 {now.month} 月",
        "updated_at": now.strftime("%Y-%m-%d %H:%M"),
        "team": {
            "month_total": month_total,
            "total": len(orders),
            "agent_count": len(agents),
        },
        "agents": rows,
    }


def _site_name(db: Session) -> str:
    return get_settings_map(db, ["site_name"]).get("site_name", "") or "毕设接单"


def public_screen_data(db: Session, token: str) -> dict | None:
    """公开大屏：token 校验 + 30 秒进程内缓存；token 失效返回 None。"""
    if not check_token(db, "screen", token):
        return None
    cached = _cache_get("screen", token)
    if cached is not None:
        return cached
    data = screen_data(db)
    data["site_name"] = _site_name(db)
    _cache_put("screen", token, data)
    return data


def public_rank_data(db: Session, token: str) -> dict | None:
    """公开业绩榜：token 校验 + 30 秒进程内缓存；token 失效返回 None。"""
    if not check_token(db, "rank", token):
        return None
    cached = _cache_get("rank", token)
    if cached is not None:
        return cached
    data = rank_data(db)
    data["site_name"] = _site_name(db)
    _cache_put("rank", token, data)
    return data
