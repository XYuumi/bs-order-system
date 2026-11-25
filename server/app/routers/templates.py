"""模板库：需求书模板 / 技术栈片段 / 报价话术 / 常用备注，下单与需求书编辑时一键复用。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_staff
from ..models import OrderTemplate, User
from ..services.oplog import log_op

router = APIRouter(prefix="/api/templates", tags=["templates"])

KIND_CN = {
    "requirement": "需求模板",
    "tech": "技术栈",
    "remark": "常用备注",
    "quote": "报价话术",
}


class TemplateIn(BaseModel):
    kind: str = Field(default="requirement", pattern=r"^(requirement|tech|remark|quote)$")
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1)
    is_shared: bool = True


class TemplatePatch(BaseModel):
    kind: str | None = Field(default=None, pattern=r"^(requirement|tech|remark|quote)$")
    title: str | None = Field(default=None, min_length=1, max_length=120)
    content: str | None = Field(default=None, min_length=1)
    is_shared: bool | None = None


def _can_manage(user: User, tpl: OrderTemplate) -> bool:
    """创建者或管理员才能改/删；写手可见全部但不等于可改别人的。"""
    return user.role == "admin" or (tpl.created_by is not None and tpl.created_by == user.id)


def _tpl_view(tpl: OrderTemplate, user: User) -> dict:
    return {
        "id": tpl.id,
        "kind": tpl.kind,
        "kind_cn": KIND_CN.get(tpl.kind, tpl.kind),
        "title": tpl.title,
        "content": tpl.content,
        "is_shared": bool(tpl.is_shared),
        "usage_count": int(tpl.usage_count or 0),
        "created_by": tpl.created_by,
        "username": tpl.username,
        "created_at": tpl.created_at,
        "updated_at": tpl.updated_at,
        "can_edit": _can_manage(user, tpl),
        "can_delete": _can_manage(user, tpl),
    }


@router.get("")
def list_templates(
    kind: str | None = None,
    keyword: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """本人可见的模板：公开共享或自己创建；管理员/写手可看全部。"""
    q = db.query(OrderTemplate)
    if user.role not in ("admin", "staff"):
        q = q.filter((OrderTemplate.is_shared == True) | (OrderTemplate.created_by == user.id))  # noqa: E712
    if kind:
        if kind not in KIND_CN:
            raise HTTPException(status_code=400, detail=f"非法的模板类型：{kind}")
        q = q.filter(OrderTemplate.kind == kind)
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(
            (OrderTemplate.title.like(like))
            | (OrderTemplate.content.like(like))
            | (OrderTemplate.username.like(like))
        )
    total = q.count()
    # updated_at 为空的旧数据在 MySQL DESC 排序里天然排最后
    rows = (
        q.order_by(OrderTemplate.updated_at.desc(), OrderTemplate.id.desc())
        .limit(500)
        .all()
    )
    return {"total": total, "items": [_tpl_view(t, user) for t in rows]}


@router.post("")
def create_template(
    body: TemplateIn,
    request: Request,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    title = body.title.strip()
    content = body.content.strip()
    if not title:
        raise HTTPException(status_code=400, detail="模板标题不能为空")
    if not content:
        raise HTTPException(status_code=400, detail="模板内容不能为空")

    now = datetime.now()
    tpl = OrderTemplate(
        kind=body.kind,
        title=title,
        content=content,
        is_shared=body.is_shared,
        usage_count=0,
        created_by=user.id,
        username=user.display_name or user.username,
        created_at=now,
        updated_at=now,
    )
    db.add(tpl)
    db.flush()
    log_op(db, "template_create", request=request, user=user, entity_type="template",
           entity_id=tpl.id,
           detail={"title": tpl.title, "kind": tpl.kind, "shared": bool(tpl.is_shared),
                   "content_len": len(tpl.content)})
    db.commit()
    db.refresh(tpl)
    return _tpl_view(tpl, user)


@router.patch("/{tid}")
def update_template(
    tid: int,
    body: TemplatePatch,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tpl = db.get(OrderTemplate, tid)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    if not _can_manage(user, tpl):
        raise HTTPException(status_code=403, detail="只能修改自己创建的模板")

    if body.kind is None and body.title is None and body.content is None and body.is_shared is None:
        raise HTTPException(status_code=400, detail="没有需要修改的内容")

    before = {
        "title": tpl.title, "kind": tpl.kind,
        "is_shared": bool(tpl.is_shared), "content_len": len(tpl.content or ""),
    }
    if body.kind is not None:
        tpl.kind = body.kind
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="模板标题不能为空")
        tpl.title = title
    if body.content is not None:
        content = body.content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="模板内容不能为空")
        tpl.content = content
    if body.is_shared is not None:
        tpl.is_shared = body.is_shared

    after = {
        "title": tpl.title, "kind": tpl.kind,
        "is_shared": bool(tpl.is_shared), "content_len": len(tpl.content or ""),
    }
    tpl.updated_at = datetime.now()
    log_op(db, "template_update", request=request, user=user, entity_type="template",
           entity_id=tpl.id, detail={"before": before, "after": after})
    db.commit()
    db.refresh(tpl)
    return _tpl_view(tpl, user)


@router.delete("/{tid}")
def delete_template(
    tid: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tpl = db.get(OrderTemplate, tid)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    if not _can_manage(user, tpl):
        raise HTTPException(status_code=403, detail="只能删除自己创建的模板")

    detail = {"title": tpl.title, "kind": tpl.kind, "username": tpl.username}
    # 模型没有 is_deleted，直接物理删除；审计日志保留删除前的信息
    db.delete(tpl)
    log_op(db, "template_delete", request=request, user=user, entity_type="template",
           entity_id=tid, detail=detail)
    db.commit()
    return {"ok": True, "id": tid}


@router.post("/{tid}/use")
def use_template(
    tid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """一键使用：使用次数 +1 并返回模板内容（前端复制到剪贴板）。"""
    tpl = db.get(OrderTemplate, tid)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    if not (tpl.is_shared or tpl.created_by == user.id or user.role in ("admin", "staff")):
        raise HTTPException(status_code=404, detail="模板不存在")

    tpl.usage_count = int(tpl.usage_count or 0) + 1
    db.commit()
    db.refresh(tpl)
    return {
        "id": tpl.id,
        "kind": tpl.kind,
        "kind_cn": KIND_CN.get(tpl.kind, tpl.kind),
        "title": tpl.title,
        "content": tpl.content,
        "usage_count": int(tpl.usage_count or 0),
    }
