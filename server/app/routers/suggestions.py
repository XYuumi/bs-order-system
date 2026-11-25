"""建议/工单系统：代理提交建议（不能改单，只能提建议），后台与写手同步收到通知。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Order, Suggestion, User
from ..services.notify_svc import push
from ..services.oplog import log_op

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])

KIND_CN = {"suggestion": "建议", "issue": "问题", "urgent": "加急"}
STATUS_CN = {"open": "待处理", "processing": "处理中", "resolved": "已解决", "closed": "已关闭"}


class SuggestIn(BaseModel):
    order_id: str | None = Field(default=None, max_length=16)
    kind: str = Field(default="suggestion", pattern=r"^(suggestion|issue|urgent)$")
    content: str = Field(min_length=5, max_length=2000)


class ReplyIn(BaseModel):
    reply: str = Field(min_length=1, max_length=2000)
    status: str = Field(default="resolved", pattern=r"^(open|processing|resolved|closed)$")


def sug_view(s: Suggestion) -> dict:
    return {
        "id": s.id,
        "order_id": s.order_id,
        "username": s.username,
        "kind": s.kind,
        "kind_cn": KIND_CN.get(s.kind, s.kind),
        "content": s.content,
        "status": s.status,
        "status_cn": STATUS_CN.get(s.status, s.status),
        "reply": s.reply,
        "replied_by": s.replied_by,
        "created_at": s.created_at,
        "replied_at": s.replied_at,
    }


@router.get("")
def list_suggestions(
    status: str | None = None,
    kind: str | None = None,
    mine: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Suggestion)
    # 代理只能看自己提交的；管理员/写手看全部（mine=1 时也只看自己的）
    if user.role == "agent" or mine:
        q = q.filter(Suggestion.user_id == user.id)
    if status in STATUS_CN:
        q = q.filter(Suggestion.status == status)
    if kind in KIND_CN:
        q = q.filter(Suggestion.kind == kind)
    items = q.order_by(Suggestion.created_at.desc()).limit(200).all()
    return {
        "items": [sug_view(s) for s in items],
        "counts": {
            st: db.query(Suggestion).filter(
                *([Suggestion.user_id == user.id] if (user.role == "agent" or mine) else []),
                Suggestion.status == st,
            ).count()
            for st in STATUS_CN
        },
        "can_reply": user.role in ("admin", "staff"),
    }


@router.post("")
def create_suggestion(
    body: SuggestIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order_id = (body.order_id or "").strip() or None
    if order_id:
        order = db.get(Order, order_id)
        if not order or order.is_deleted:
            raise HTTPException(status_code=404, detail=f"订单 {order_id} 不存在")
        if user.role == "agent" and order.agent_user_id != user.id:
            raise HTTPException(status_code=403, detail="只能为本人名下订单提交建议")

    s = Suggestion(
        order_id=order_id,
        user_id=user.id,
        username=user.display_name or user.username,
        kind=body.kind,
        content=body.content.strip(),
    )
    db.add(s)
    db.flush()

    # 后台（管理员）与写手同步收到通知
    receivers = db.query(User).filter(
        User.role.in_(["admin", "staff"]), User.is_active == True, User.id != user.id  # noqa: E712
    ).all()
    push(
        db,
        [u.id for u in receivers],
        f"新{KIND_CN.get(s.kind, '建议')} #{s.id} 来自 {s.username}",
        body=body.content.strip()[:200],
        order_id=s.order_id,
    )
    log_op(db, "suggestion_create", request=request, user=user, entity_id=s.id,
           detail={"kind": s.kind, "order_id": s.order_id})
    db.commit()
    return sug_view(s)


@router.post("/{sid}/reply")
def reply_suggestion(
    sid: int,
    body: ReplyIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role not in ("admin", "staff"):
        raise HTTPException(status_code=403, detail="仅管理员/写手可回复")
    s = db.get(Suggestion, sid)
    if not s:
        raise HTTPException(status_code=404, detail="建议不存在")

    s.reply = body.reply.strip()
    s.replied_by = user.display_name or user.username
    s.replied_at = datetime.now()
    s.status = body.status
    push(
        db, [s.user_id],
        f"你的{KIND_CN.get(s.kind, '建议')} #{s.id} 已回复（{STATUS_CN.get(s.status, s.status)}）",
        body=body.reply.strip()[:200],
        order_id=s.order_id,
    )
    log_op(db, "suggestion_reply", request=request, user=user, entity_id=s.id,
           detail={"status": s.status})
    db.commit()
    return sug_view(s)


@router.post("/{sid}/status")
def set_status(
    sid: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status: str = Query(...),
):
    """快捷改状态（管理员/写手）。"""
    if user.role not in ("admin", "staff"):
        raise HTTPException(status_code=403, detail="仅管理员/写手可操作")
    if status not in STATUS_CN:
        raise HTTPException(status_code=400, detail=f"非法状态: {status}")
    s = db.get(Suggestion, sid)
    if not s:
        raise HTTPException(status_code=404, detail="建议不存在")
    s.status = status
    log_op(db, "suggestion_status", request=request, user=user, entity_id=s.id, detail={"status": status})
    db.commit()
    return sug_view(s)
