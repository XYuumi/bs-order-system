from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_staff
from ..models import OperationLog, User

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
def list_logs(
    username: str | None = Query(default=None, max_length=50),
    action: str | None = Query(default=None, max_length=50),
    entity_id: str | None = Query(default=None, max_length=32),
    entity_type: str | None = Query(default=None, max_length=30),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    q = db.query(OperationLog)
    conds = []
    if username:
        conds.append(OperationLog.username.like(f"%{username}%"))
    if action:
        conds.append(OperationLog.action == action)
    if entity_id:
        conds.append(OperationLog.entity_id == entity_id)
    if entity_type:
        conds.append(OperationLog.entity_type == entity_type)
    if date_from:
        conds.append(OperationLog.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        conds.append(OperationLog.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
    if conds:
        q = q.filter(and_(*conds))

    total = q.count()
    items = (
        q.order_by(OperationLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    actions = [row[0] for row in db.query(OperationLog.action).distinct().order_by(OperationLog.action).all()]

    # 写手/代理不可见真实价与倍率，防止日志旁路泄漏。
    # 递归处理：detail 里可能是 {before: {...}, after: {...}}、agents: [{...}] 等多种嵌套形态。
    HIDDEN_KEYS = {
        "owner_price",
        "owner_price_override",
        "agent_price_override",
        "price_override",
        "multiplier",
    }

    def _scrub(node, depth: int = 0):
        if depth > 8:
            return None
        if isinstance(node, dict):
            return {k: _scrub(v, depth + 1) for k, v in node.items() if k not in HIDDEN_KEYS}
        if isinstance(node, list):
            return [_scrub(item, depth + 1) for item in node]
        return node

    def detail_for(raw):
        if not raw:
            return None
        try:
            detail = json.loads(raw)
        except (ValueError, TypeError):
            return None
        if user.role == "admin":
            return detail
        return _scrub(detail)

    # 个性角色标签：日志行只存用户名快照，读取时补当前标签
    from ..models import User as _User
    label_map = {
        u: lb for u, lb in db.query(_User.username, _User.role_label)
        .filter(_User.role_label.isnot(None)).all() if lb
    }
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "actions": actions,
        "items": [
            {
                "id": lg.id,
                "username": lg.username,
                "role": lg.role,
                "role_label": label_map.get(lg.username),
                "action": lg.action,
                "entity_type": lg.entity_type,
                "entity_id": lg.entity_id,
                "detail": detail_for(lg.detail),
                "ip": lg.ip,
                "created_at": lg.created_at,
            }
            for lg in items
        ],
    }
