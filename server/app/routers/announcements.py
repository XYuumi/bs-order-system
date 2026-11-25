"""公告管理 + 客户库（轻 CRM）。"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import Announcement, Customer, User
from ..services.notify_svc import push
from ..services.oplog import log_op

router = APIRouter(prefix="/api", tags=["announcements+customers"])

LEVEL_CN = {"info": "通知", "warning": "警告", "important": "重要"}


# ============================== 公告 ==============================

class AnnouncementIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=2000)
    level: str = Field(default="info", pattern=r"^(info|warning|important)$")
    is_published: bool = True


def _ann_view(a: Announcement) -> dict:
    return {
        "id": a.id, "title": a.title, "content": a.content,
        "level": a.level, "level_cn": LEVEL_CN.get(a.level, a.level),
        "username": a.username, "is_published": a.is_published,
        "created_at": a.created_at, "updated_at": a.updated_at,
    }


@router.get("/announcements")
def list_announcements(
    limit: int = 10,
    include_unpublished: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Announcement)
    if not (include_unpublished and user.role == "admin"):
        q = q.filter(Announcement.is_published == True)  # noqa: E712
    rows = q.order_by(Announcement.created_at.desc()).limit(min(max(limit, 1), 50)).all()
    return {"items": [_ann_view(a) for a in rows]}


@router.post("/announcements")
def create_announcement(
    body: AnnouncementIn,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    a = Announcement(
        title=body.title.strip(), content=body.content.strip(), level=body.level,
        created_by=admin.id, username=admin.display_name or admin.username,
        is_published=body.is_published,
    )
    db.add(a)
    db.flush()
    if body.is_published:
        targets = [uid for (uid,) in db.query(User.id).filter(
            User.is_active == True, User.id != admin.id).all()]  # noqa: E712
        push(db, targets, f"📢 新公告：{a.title[:60]}", body=body.content[:200])
    log_op(db, "announcement_create", request=request, user=admin, entity_id=a.id,
           detail={"level": body.level, "published": body.is_published})
    db.commit()
    return _ann_view(a)


@router.put("/announcements/{aid}")
def update_announcement(
    aid: int,
    body: AnnouncementIn,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    a = db.get(Announcement, aid)
    if not a:
        raise HTTPException(status_code=404, detail="公告不存在")
    was_published = a.is_published
    a.title = body.title.strip()
    a.content = body.content.strip()
    a.level = body.level
    a.is_published = body.is_published
    a.updated_at = datetime.now()
    if body.is_published and not was_published:
        targets = [uid for (uid,) in db.query(User.id).filter(
            User.is_active == True, User.id != admin.id).all()]  # noqa: E712
        push(db, targets, f"📢 新公告：{a.title[:60]}", body=body.content[:200])
    log_op(db, "announcement_update", request=request, user=admin, entity_id=aid, detail={})
    db.commit()
    return _ann_view(a)


@router.delete("/announcements/{aid}")
def delete_announcement(
    aid: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    a = db.get(Announcement, aid)
    if not a:
        raise HTTPException(status_code=404, detail="公告不存在")
    db.delete(a)
    log_op(db, "announcement_delete", request=request, user=admin, entity_id=aid, detail={})
    db.commit()
    return {"ok": True}


# ============================== 客户库（CRM） ==============================

class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    contact: str | None = Field(default=None, max_length=120)
    school: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, max_length=50)
    note: str | None = Field(default=None, max_length=2000)


def _cust_view(c: Customer, order_count: int = 0) -> dict:
    return {
        "id": c.id, "name": c.name, "contact": c.contact, "school": c.school,
        "source": c.source, "note": c.note, "order_count": order_count,
        "owner_id": c.owner_id, "created_at": c.created_at, "updated_at": c.updated_at,
    }


@router.get("/customers")
def list_customers(
    keyword: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Customer)
    if user.role == "agent":
        q = q.filter(Customer.owner_id == user.id)
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter((Customer.name.like(like)) | (Customer.contact.like(like)) | (Customer.school.like(like)))
    rows = q.order_by(Customer.created_at.desc()).limit(300).all()
    counts = _customer_order_counts(db, user, [r.name for r in rows if r.name])
    return {"items": [_cust_view(c, counts.get(c.name, 0)) for c in rows]}


_SPLIT_RE = re.compile(r"[\s,，、;；/|()（）【】\[\]<>《》]+")


def _customer_order_counts(db: Session, user: User, names: list[str]) -> dict[str, int]:
    """按 customer_info 的“整段客户名”计数，避免「张三」误命中「张三丰」。

    用一次全表扫描建立 token→次数倒排，再按客户名取值；不再对每个客户
    重复拼接/扫描整段文本（原实现是 O(客户数 × 全表文本)）。
    """
    from ..models import Order

    wanted = set(names)
    if not wanted:
        return {}
    q = db.query(Order.customer_info).filter(Order.is_deleted == False)  # noqa: E712
    if user.role == "agent":
        q = q.filter(Order.agent_user_id == user.id)
    counts: dict[str, int] = {}
    for (info,) in q.all():
        if not info:
            continue
        for token in set(_SPLIT_RE.split(str(info))):
            token = token.strip()
            if token and token in wanted:
                counts[token] = counts.get(token, 0) + 1
    return counts


@router.post("/customers")
def create_customer(
    body: CustomerIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exists = db.query(Customer).filter(
        Customer.owner_id == user.id, Customer.name == body.name.strip()).first()
    if exists:
        raise HTTPException(status_code=400, detail="该客户已存在（同名同归属）")
    c = Customer(
        name=body.name.strip(), contact=body.contact, school=body.school,
        source=body.source, note=body.note, owner_id=user.id,
    )
    db.add(c)
    db.flush()
    log_op(db, "customer_create", request=request, user=user, entity_id=c.id,
           detail={"name": c.name})
    db.commit()
    return _cust_view(c)


@router.put("/customers/{cid}")
def update_customer(
    cid: int,
    body: CustomerIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    if user.role != "admin" and c.owner_id != user.id:
        raise HTTPException(status_code=403, detail="只能编辑自己的客户")
    c.name = body.name.strip()
    c.contact = body.contact
    c.school = body.school
    c.source = body.source
    c.note = body.note
    c.updated_at = datetime.now()
    log_op(db, "customer_update", request=request, user=user, entity_id=cid, detail={})
    db.commit()
    return _cust_view(c)


@router.delete("/customers/{cid}")
def delete_customer(
    cid: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    if user.role != "admin" and c.owner_id != user.id:
        raise HTTPException(status_code=403, detail="只能删除自己的客户")
    db.delete(c)
    log_op(db, "customer_delete", request=request, user=user, entity_id=cid, detail={"name": c.name})
    db.commit()
    return {"ok": True}
