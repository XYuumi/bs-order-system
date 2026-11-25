"""操作日志：谁、何时、改了什么。调用方负责 commit。"""
from __future__ import annotations

import json

from fastapi import Request
from sqlalchemy.orm import Session

from ..models import OperationLog, User
from ..ratelimit import client_ip


def log_op(
    db: Session,
    action: str,
    *,
    request: Request | None = None,
    user: User | None = None,
    entity_type: str = "",
    entity_id: str | int = "",
    detail: dict | None = None,
) -> None:
    ip = client_ip(request) if request is not None else ""
    entry = OperationLog(
        user_id=user.id if user else None,
        username=user.username if user else "-",
        role=user.role if user else "-",
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        detail=json.dumps(detail, ensure_ascii=False, default=str) if detail else None,
        ip=ip,
    )
    db.add(entry)
