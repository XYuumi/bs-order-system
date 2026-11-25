"""开放 API v1：X-API-Key 认证。代理只见自己订单与代理价；写手可拉全部订单、回传状态、上传交付物。"""
from __future__ import annotations

import json
from datetime import date
from functools import partial

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import api_key_user
from ..constants import SOURCE_REQUIREMENT_MAX_CHARS
from ..models import Order, OrderFile, Quality, User
from ..ratelimit import rate_limit
from ..services import docgen
from ..services.files_svc import download_response, remove_stored_files, save_upload
from ..services.oplog import log_op
from ..services.order_svc import (
    can_change_status,
    create_order as create_order_svc,
    file_view,
    normalize_project_type,
    order_view,
    set_order_status,
    user_allowed_project_types,
)
from ..services.pricing import get_base_prices, quality_view
from urllib.parse import quote
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/v1", tags=["api-v1"])


def _limit(request: Request, user: User):
    rate_limit(request, "apiv1", user.username, limit=120, window_seconds=60)


class ApiOrderCreateIn(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    quality_code: str = Field(min_length=1, max_length=10)
    # 自定义订单编号（导入历史项目保留原编号）：留空自动生成；仅管理员 API 可指定
    order_no: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{2,16}$")
    # 成交价：代理（销售/同行）下单时自己应付的金额；仅代理 API 生效
    price: float | None = Field(default=None, gt=0, le=1000000, allow_inf_nan=False)
    # program=纯程序设计 thesis=纯论文 thesis_program=论文+设计
    project_type: str | None = Field(default=None, pattern=r"^(program|thesis|thesis_program)$")
    # 废弃兼容：旧脚本仍传工种 code/design/thesis，服务端归一为项目类型
    category: str | None = Field(default=None, pattern=r"^(code|design|thesis)$")
    deadline: date | None = None
    tech_stack: str | None = Field(default=None, max_length=100)
    remark: str | None = Field(default=None, max_length=2000)


@router.get("/qualities")
def list_qualities(request: Request, user: User = Depends(api_key_user), db: Session = Depends(get_db)):
    _limit(request, user)
    owner_base, agent_base = get_base_prices(db)
    q = db.query(Quality).filter(Quality.enabled == True).order_by(Quality.sort, Quality.id)  # noqa: E712
    return {"qualities": [quality_view(qc, owner_base, agent_base, user.role) for qc in q.all()]}


def _own_order(db: Session, user: User, order_id: str) -> Order:
    """代理只能访问自己的订单；写手（staff）可访问全部订单（拉单制作）。"""
    q = (
        db.query(Order)
        .options(selectinload(Order.quality), selectinload(Order.agent),
                 selectinload(Order.assignee), selectinload(Order.creator))
        .filter(Order.id == order_id, Order.is_deleted == False)  # noqa: E712
    )
    if user.role == "agent":
        q = q.filter(Order.agent_user_id == user.id)
    order = q.first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if user.role == "agent":
        allowed = user_allowed_project_types(user)
        if allowed is not None and order.project_type not in allowed:
            raise HTTPException(status_code=404, detail="订单不存在")
    return order


@router.get("/orders")
def list_orders(
    request: Request,
    status: str | None = Query(default=None, max_length=20),
    project_type: str | None = Query(default=None, pattern=r"^(program|thesis|thesis_program)$"),
    keyword: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(api_key_user),
    db: Session = Depends(get_db),
):
    _limit(request, user)
    q = (
        db.query(Order)
        .options(selectinload(Order.quality), selectinload(Order.agent),
                 selectinload(Order.assignee), selectinload(Order.creator))
        .filter(Order.is_deleted == False)  # noqa: E712
    )
    if user.role == "agent":
        q = q.filter(Order.agent_user_id == user.id)
    allowed = None if user.role != "agent" else user_allowed_project_types(user)
    types = allowed
    if project_type:
        if types is not None and project_type not in types:
            return {"total": 0, "page": page, "page_size": page_size, "items": []}
        types = [project_type]
    if types is not None:
        q = q.filter(Order.project_type.in_(types))
    if status:
        q = q.filter(Order.status == status)
    if keyword:
        kw = f"%{keyword.strip()}%"
        q = q.filter(or_(Order.title.like(kw), Order.id.like(kw)))
    total = q.count()
    items = q.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [order_view(o, user.role) for o in items],
    }


@router.post("/orders")
def api_create_order(
    body: ApiOrderCreateIn,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(api_key_user),
    db: Session = Depends(get_db),
):
    _limit(request, user)
    if user.role not in ("agent", "admin"):
        raise HTTPException(status_code=403, detail="仅代理/管理员可通过 API 创建订单（写手请使用网页端）")
    effective_type = normalize_project_type(body.project_type, body.category)
    allowed = user_allowed_project_types(user)
    if allowed is not None and effective_type not in allowed:
        raise HTTPException(status_code=403, detail=f"你的 API 无权创建该类型订单（允许：{','.join(allowed)}）")
    try:
        order = create_order_svc(
            db,
            title=body.title,
            quality_code=body.quality_code,
            creator=user,
            deadline=body.deadline,
            tech_stack=body.tech_stack,
            remark=body.remark,
            agent_user=user if user.role == "agent" else None,
            project_type=effective_type,
            order_no=(body.order_no if user.role == "admin" else None),
            owner_price_override=(body.price if user.role == "agent" else None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    log_op(db, "api_order_create", request=request, user=user,
           entity_type="order", entity_id=order.id, detail={"title": order.title})
    # 站内通知：管理员与全部写手 + 订单代理本人（非创建者）
    from ..services.notify_svc import notify_order_created
    notify_order_created(db, order, user.id)
    db.commit()
    from ..services.webhook import notify_order_created

    background.add_task(
        notify_order_created,
        order.id, order.title,
        (user.display_name or user.username) if user.role == "agent" else None,
        float(order.agent_price),
    )
    return {"order": order_view(order, user.role)}


@router.get("/orders/{order_id}")
def get_order(
    order_id: str,
    request: Request,
    user: User = Depends(api_key_user),
    db: Session = Depends(get_db),
):
    _limit(request, user)
    return {"order": order_view(_own_order(db, user, order_id), user.role)}


@router.get("/orders/{order_id}/requirement.docx")
def download_requirement(
    order_id: str,
    request: Request,
    user: User = Depends(api_key_user),
    db: Session = Depends(get_db),
):
    _limit(request, user)
    order = _own_order(db, user, order_id)
    if not order.requirement:
        raise HTTPException(status_code=404, detail="尚未生成需求书，无法下载")
    try:
        document = json.loads(order.requirement)
    except (ValueError, TypeError):
        raise HTTPException(status_code=500, detail="需求书数据损坏")
    from ..services.settings_svc import get_setting
    buf = docgen.render_docx(document, school=get_setting(db, "docx_school"))
    log_op(db, "api_requirement_download", request=request, user=user,
           entity_type="order", entity_id=order.id)
    db.commit()
    filename = f"{order.id}-需求书.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Content-Length": str(buf.getbuffer().nbytes),
        },
    )


class ApiStatusIn(BaseModel):
    status: str = Field(pattern=r"^(pending|in_progress|completed|closed|after_sale|cancelled)$")
    note: str | None = Field(default=None, max_length=500)


# 需求书九章合法键（分段修改接口校验用）
_REQ_CHAPTERS = {"goal", "scope", "roles", "scenarios", "functions", "rules",
                 "data_scope", "tech", "database"}
_REQ_CHAPTER_CN = {
    "goal": "一、项目目标", "scope": "二、建设范围", "roles": "三、角色定义",
    "scenarios": "四、核心业务场景", "functions": "五、功能需求", "rules": "六、业务规则",
    "data_scope": "七、数据范围", "tech": "八、技术架构", "database": "九、数据库设计",
}


def _load_requirement(order: Order) -> dict:
    if not order.requirement:
        raise HTTPException(status_code=404, detail="尚未生成需求书")
    try:
        return json.loads(order.requirement)
    except (ValueError, TypeError):
        raise HTTPException(status_code=500, detail="需求书数据损坏")


@router.get("/orders/{order_id}/requirement")
def api_get_requirement(
    order_id: str,
    request: Request,
    user: User = Depends(api_key_user),
    db: Session = Depends(get_db),
):
    """获取需求书结构化 JSON（九章），供外部系统读取/编辑后再分段写回。"""
    _limit(request, user)
    order = _own_order(db, user, order_id)
    document = _load_requirement(order)
    if document.get("mode") == "raw":
        return {"order_id": order.id, "mode": "raw", "document": document,
                "note": "原文直用文档：只能整体替换（requirement/upload），不支持分段修改"}
    return {"order_id": order.id, "mode": document.get("mode") or "structured",
            "chapters": {k: v for k, v in (document.get("chapters") or {}).items() if k in _REQ_CHAPTERS}}


class ApiRequirementPatchIn(BaseModel):
    # 只传要改的章节：{"chapters": {"goal": {"paragraphs": [...]}, ...}}
    chapters: dict[str, dict] = Field(min_length=1, max_length=9)
    remark: str | None = Field(default=None, max_length=200)


@router.patch("/orders/{order_id}/requirement")
def api_patch_requirement(
    order_id: str,
    body: ApiRequirementPatchIn,
    request: Request,
    user: User = Depends(api_key_user),
    db: Session = Depends(get_db),
):
    """分段修改需求书：按章节覆盖（未提交的章节保持原样），免去本地改完再整体上传替换。

    章节键：goal/scope/roles/scenarios/functions/rules/data_scope/tech/database，
    章节对象的内部结构与 GET 返回的一致；修改前自动快照，可在网页端「历史版本」回滚。
    """
    from datetime import datetime

    from .orders import snapshot_requirement

    _limit(request, user)
    order = _own_order(db, user, order_id)
    document = _load_requirement(order)
    if document.get("mode") == "raw":
        raise HTTPException(status_code=400, detail="原文直用文档不支持分段修改，请整体替换")

    bad = [k for k in body.chapters if k not in _REQ_CHAPTERS]
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"非法章节键: {', '.join(bad)}；合法键: {', '.join(sorted(_REQ_CHAPTERS))}",
        )

    chapters = document.setdefault("chapters", {})
    changed = []
    for key, val in body.chapters.items():
        if not isinstance(val, dict) or not val:
            raise HTTPException(status_code=400, detail=f"章节 {key} 的内容必须是非空对象")
        chapters[key] = val
        changed.append(_REQ_CHAPTER_CN.get(key, key))

    merged = docgen.normalize_doc(document, order.title, order.tech_stack)
    snapshot_requirement(db, order, user,
                         remark=(body.remark or "")[:200] or f"API 分段修改：{'、'.join(changed)}")
    order.requirement = json.dumps(merged, ensure_ascii=False)
    order.requirement_updated_at = datetime.now()
    log_op(db, "api_requirement_update", request=request, user=user,
           entity_type="order", entity_id=order.id,
           detail={"chapters": changed, "via": "api"})
    db.commit()
    return {
        "order_id": order.id,
        "updated_chapters": list(body.chapters.keys()),
        "requirement": merged,
        "note": "已按章节覆盖保存；修改前内容已存入历史版本",
    }


@router.post("/orders/{order_id}/requirement/upload")
async def api_upload_requirement(
    order_id: str,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(api_key_user),
    db: Session = Depends(get_db),
):
    """上传需求书文件整体替换当前需求书（写手大改后回传 / 不走 AI 自行撰写时使用）。

    支持三种格式（与网页端一致）：
    - 本系统九章 JSON（.json，可先用 GET /requirement 取回修改后再传）：直接导入
    - Word（.docx）：提取文本 → 解析为九章结构
    - TXT / Markdown：同 Word 处理
    替换前自动快照，可在网页端「历史版本」回滚。
    """
    from datetime import datetime

    from .orders import snapshot_requirement
    from ..services.docgen.extract import extract_text, is_our_doc
    from ..services.docgen.importer import text_to_doc

    _limit(request, user)
    order = _own_order(db, user, order_id)

    data = await file.read()
    filename = file.filename or ""
    try:
        text, _matched = extract_text(filename, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="未能从文件中提取到内容")
    # 上限与建单/编辑入参一致：超长直接拒绝，不做静默截断
    if len(text) > SOURCE_REQUIREMENT_MAX_CHARS:
        raise HTTPException(
            status_code=400, detail=f"文件内容过长（超过 {SOURCE_REQUIREMENT_MAX_CHARS:,} 字符），请精简或拆分后上传")

    document = None
    source = "manual"
    note = ""
    try:
        parsed = json.loads(text)
        if is_our_doc(parsed):
            document = docgen.normalize_doc(parsed, order.title, order.tech_stack)
            note = "已导入系统格式需求书（九章结构原样保留）"
    except (ValueError, TypeError):
        pass

    if document is None:
        imported = text_to_doc(order.title, text[:20000])
        if imported is not None:
            document = imported
            note = "已将上传文档解析为九章结构（内容未改写，可逐条编辑）"
        else:
            document = docgen.build_raw_doc(order.title, text[:20000])
            note = "上传文档按原文展示（未识别出章节结构）"

    if order.requirement:
        snapshot_requirement(db, order, user, remark="API 上传替换前快照")
    order.requirement = json.dumps(document, ensure_ascii=False)
    order.requirement_source = source
    order.requirement_updated_at = datetime.now()
    order.source_requirement = text[:20000]
    log_op(db, "api_requirement_upload", request=request, user=user,
           entity_type="order", entity_id=order.id,
           detail={"filename": filename[:100], "mode": document.get("mode", ""), "note": note})
    db.commit()
    return {
        "order_id": order.id,
        "ok": True,
        "note": note,
        "mode": document.get("mode", ""),
        "requirement": document,
        "hint": "整体替换完成；修改前内容已存入历史版本，可用 PATCH /requirement 做后续小改",
    }


@router.post("/orders/{order_id}/status")
def api_update_status(
    order_id: str,
    body: ApiStatusIn,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(api_key_user),
    db: Session = Depends(get_db),
):
    """写手/管理员回传状态，严格走统一状态机；代理无权改状态。"""
    _limit(request, user)
    if user.role == "agent":
        raise HTTPException(status_code=403, detail="代理不能通过 API 修改订单状态")
    order = _own_order(db, user, order_id)
    if not can_change_status(order, user, body.status):
        raise HTTPException(status_code=403, detail="无权把该订单推进到此状态（结单/售后仅管理员）")
    old = order.status
    try:
        if not set_order_status(order, body.status, allow_any=True):  # 权限已由 can_change_status 校验
            raise ValueError("订单已是该状态")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    detail = {"before": old, "after": body.status, "via": "api"}
    if body.note:
        detail["note"] = body.note
    log_op(db, "api_order_status", request=request, user=user,
           entity_type="order", entity_id=order.id, detail=detail)
    from ..services.notify_svc import notify_status_changed

    notify_status_changed(db, order, user.id, body.status)
    db.commit()
    from ..services.webhook import notify_status_changed as notify_webhook

    background.add_task(notify_webhook, order.id, order.title, old, body.status)
    return {"order": order_view(order, user.role)}


@router.get("/orders/{order_id}/files")
def list_files(
    order_id: str,
    request: Request,
    category: str | None = Query(default=None, max_length=10),
    user: User = Depends(api_key_user),
    db: Session = Depends(get_db),
):
    _limit(request, user)
    order = _own_order(db, user, order_id)
    q = db.query(OrderFile).filter(OrderFile.order_id == order.id, OrderFile.is_deleted == False)  # noqa: E712
    if category:
        q = q.filter(OrderFile.category == category)
    files = q.order_by(OrderFile.created_at.desc()).all()
    return {"files": [file_view(f) for f in files]}


@router.post("/orders/{order_id}/files")
async def api_upload_file(
    order_id: str,
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(...),
    remark: str | None = Form(default=None),
    replace: str = Form(default=""),
    user: User = Depends(api_key_user),
    db: Session = Depends(get_db),
):
    """写手回传交付物：上传演示视频 / 交付包 / 文档到指定订单（仅写手角色）。

    演示视频（video）与交付包（package）每单各保留一份：再次上传即替换旧文件，
    响应的 replaced 列出被替换的文件。传 replace=0 则保留旧文件、追加为新文件。
    """
    _limit(request, user)
    if user.role not in ("staff", "admin"):
        raise HTTPException(status_code=403, detail="仅写手/管理员可通过 API 上传交付物（代理请使用网页端）")
    if category not in ("video", "package", "doc", "other"):
        raise HTTPException(status_code=400, detail=f"非法分类: {category}")
    order = _own_order(db, user, order_id)
    record, replaced = await run_in_threadpool(
        partial(
            save_upload,
            db,
            order=order,
            category=category,
            original_name=file.filename or "file",
            stream=file.file,
            declared_mime=file.content_type,
            remark=remark,
            uploader=user,
            # 不传 = 按分类默认规则（只有视频/程序包会替换）；replace=0 = 保留旧文件。
            # 其余取值一律按默认规则：文档、其他附件不会因为传了 replace=1 而被替换。
            replace=False if replace.strip().lower() in ("0", "false", "no", "off") else None,
        )
    )
    names = [f.original_name for f in replaced]
    detail = {"file": record.original_name, "category": category, "size": record.size}
    if names:
        detail.update(replaced=names, replaced_ids=[f.id for f in replaced])
    log_op(db, "api_file_upload", request=request, user=user,
           entity_type="order", entity_id=order.id, detail=detail)
    from ..services.notify_svc import notify_file_uploaded
    notify_file_uploaded(db, order, user.id, record.original_name, category, replaced=names)
    db.commit()
    await run_in_threadpool(remove_stored_files, db, replaced)  # 替换已提交，再删磁盘上的旧文件
    return {"file": file_view(record), "replaced": [file_view(f) for f in replaced]}


@router.get("/files/{file_id}/download")
def download_file(
    file_id: int,
    request: Request,
    download: str | None = Query(default=None, max_length=8),
    user: User = Depends(api_key_user),
    db: Session = Depends(get_db),
):
    """下载附件（视频支持断点/拖动）。?download=1 强制保存文件，默认视频在线播放。"""
    _limit(request, user)
    force = (download or "").strip().lower() in ("1", "true", "yes")
    return download_response(db, file_id=file_id, request=request, user=user,
                             action="api_file_download", force_download=force)
