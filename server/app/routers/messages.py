"""站内私信：上下级代理互聊 + 代理与平台（管理员/写手）互聊。

联系人范围（防止代理之间串通/窥探）：
- 管理员/写手：所有活跃用户
- 代理：管理员 + 写手（平台） + 自己的上级 + 自己的直接下级
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import ChatMessage, User
from ..ratelimit import client_ip, rate_limit
from ..services.oplog import log_op
from ..ws import queue_ws_event

router = APIRouter(prefix="/api/messages", tags=["messages"])

ROLE_CN = {"admin": "管理员", "staff": "写手", "agent": "代理"}


def contact_ids(db: Session, user: User) -> list[int]:
    """当前用户可聊天的对象 ID 列表。"""
    if user.role in ("admin", "staff"):
        rows = db.query(User).filter(
            User.is_active == True, User.id != user.id  # noqa: E712
        ).all()
        return [u.id for u in rows]
    # 代理：平台（admin+staff）+ 上级 + 直接下级
    ids = {u.id for u in db.query(User).filter(
        User.role.in_(["admin", "staff"]), User.is_active == True  # noqa: E712
    ).all()}
    if user.parent_id:
        ids.add(user.parent_id)
    children = db.query(User).filter(User.parent_id == user.id, User.is_active == True).all()  # noqa: E712
    ids.update(c.id for c in children)
    ids.discard(user.id)
    return sorted(ids)


def user_brief(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "display_name": u.display_name or u.username,
        "role": u.role,
        "role_cn": u.role_label or ROLE_CN.get(u.role, u.role),
        "role_label": u.role_label or None,
        "last_login_at": u.last_login_at,
    }


class SendIn(BaseModel):
    to_user_id: int = Field(gt=0)
    content: str = Field(min_length=1, max_length=2000)


@router.get("/contacts")
def contacts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """联系人列表：含每人最后一条消息、未读数、总未读。

    以「对方 ID」分组的一条聚合查询同时拿到每个联系人的最后一条消息 ID 与未读数，
    替代原先每个联系人各查两次的 2N+1 查询；响应字段保持不变。
    """
    ids = contact_ids(db, user)
    if not ids:
        return {"items": [], "total_unread": 0}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}
    peer_id = case(
        (ChatMessage.from_id == user.id, ChatMessage.to_id),
        else_=ChatMessage.from_id,
    )
    stats = (
        db.query(
            peer_id.label("peer_id"),
            func.max(ChatMessage.id).label("last_id"),
            func.sum(case(
                (and_(ChatMessage.to_id == user.id, ChatMessage.is_read == False), 1),  # noqa: E712
                else_=0,
            )).label("unread"),
        )
        .filter(or_(ChatMessage.from_id == user.id, ChatMessage.to_id == user.id))
        .group_by(peer_id)
        .subquery()
    )
    last_rows = (
        db.query(
            stats.c.peer_id,
            stats.c.unread,
            ChatMessage.content,
            ChatMessage.from_id,
            ChatMessage.created_at,
        )
        .join(ChatMessage, ChatMessage.id == stats.c.last_id)
        .filter(stats.c.peer_id.in_(ids))
        .all()
    )
    last_map = {row.peer_id: row for row in last_rows}
    items = []
    total_unread = 0
    for uid in ids:
        u = users.get(uid)
        if not u:
            continue
        last = last_map.get(uid)
        unread = int(last.unread or 0) if last else 0
        total_unread += unread
        items.append({
            **user_brief(u),
            "unread": unread,
            "last_content": ((last.content or "")[:60] if last else ""),
            "last_from_me": bool(last and last.from_id == user.id),
            "last_at": (last.created_at if last else None),
        })
    items.sort(key=lambda x: x["last_at"].isoformat() if x["last_at"] else "", reverse=True)
    return {"items": items, "total_unread": total_unread}


@router.get("/unread")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"unread": db.query(ChatMessage).filter(
        ChatMessage.to_id == user.id, ChatMessage.is_read == False  # noqa: E712
    ).count()}


@router.get("")
def thread(
    user_id: int = Query(..., gt=0),
    before_id: int | None = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """与某人的消息记录（拉取即标记对方来信已读），按时间正序返回。"""
    if user_id not in contact_ids(db, user):
        raise HTTPException(status_code=403, detail="对方不在你的联系人范围内")
    peer = db.get(User, user_id)
    q = db.query(ChatMessage).filter(
        ((ChatMessage.from_id == user.id) & (ChatMessage.to_id == user_id))
        | ((ChatMessage.from_id == user_id) & (ChatMessage.to_id == user.id))
    )
    if before_id:
        q = q.filter(ChatMessage.id < before_id)
    rows = q.order_by(ChatMessage.id.desc()).limit(limit).all()
    rows.reverse()
    # 只标记本次实际拉取到的对方来信为已读，避免把更早的未读一并吞掉。
    unread_ids = [m.id for m in rows if m.from_id == user_id and not m.is_read]
    if unread_ids:
        db.query(ChatMessage).filter(ChatMessage.id.in_(unread_ids)).update(
            {"is_read": True}, synchronize_session=False
        )
        for m in rows:
            if m.id in unread_ids:
                m.is_read = True
    db.commit()
    return {
        "peer": user_brief(peer) if peer else None,
        "items": [
            {"id": m.id, "from_id": m.from_id, "to_id": m.to_id,
             "content": m.content, "is_read": m.is_read, "created_at": m.created_at}
            for m in rows
        ],
    }


@router.post("")
def send_message(
    body: SendIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rate_limit(request, "chat_send", f"{user.id}:{client_ip(request)}", limit=60, window_seconds=60)
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    if body.to_user_id not in contact_ids(db, user):
        raise HTTPException(status_code=403, detail="对方不在你的联系人范围内")
    peer = db.get(User, body.to_user_id)
    if not peer or not peer.is_active:
        raise HTTPException(status_code=404, detail="对方不存在或已停用")
    if body.to_user_id == user.id:
        raise HTTPException(status_code=400, detail="不能给自己发消息")
    m = ChatMessage(from_id=user.id, to_id=body.to_user_id, content=content)
    db.add(m)
    log_op(db, "chat_send", request=request, user=user, entity_id=peer.username,
           detail={"to": peer.username, "len": len(content)})
    queue_ws_event(db, [body.to_user_id], {
        "type": "chat",
        "from_id": user.id,
        "from_name": user.display_name or user.username,
        "content": content[:200],
    })
    db.commit()
    return {"id": m.id, "from_id": m.from_id, "to_id": m.to_id,
            "content": m.content, "is_read": False, "created_at": m.created_at}
