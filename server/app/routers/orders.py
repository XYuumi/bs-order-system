from __future__ import annotations

import json

from pydantic import BaseModel, Field
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_current_user, require_admin, require_staff
from ..constants import SOURCE_REQUIREMENT_MAX_CHARS
from ..models import OperationLog, Order, OrderFile, Quality, StatusRevertRequest, User
from ..ratelimit import client_ip, rate_limit
from ..schemas import (
    BatchStatusIn,
    DeployStatusIn,
    GenerateIn,
    OrderCreateIn,
    OrderUpdateIn,
    RequirementReviseIn,
    RequirementSaveIn,
    StatusIn,
    StatusRevertIn,
    TitleCheckIn,
)
from ..services import docgen
from ..services.docgen.ai import AIGenerationError, ai_available, generate_by_ai, revise_by_ai
from ..services.docgen.extract import MAX_FILE_MB, extract_text, is_our_doc
from ..services.docgen.importer import text_to_doc
from ..services.oplog import log_op
from ..services.settings_svc import get_setting
from ..services.order_svc import (
    STATUS_CN,
    STATUS_TRANSITIONS,
    allowed_statuses,
    apply_status,
    can_access,
    can_change_status,
    can_download,
    create_order,
    derive_category,
    file_view,
    normalize_project_type,
    order_query,
    order_view,
    revert_target,
    revert_view,
    set_order_status,
    trash_query,
)
from ..services.pricing import compute_prices, get_quality_by_code
from urllib.parse import quote

router = APIRouter(prefix="/api/orders", tags=["orders"])


def snapshot_requirement(db: Session, order: Order, user, remark: str = "") -> None:
    """把当前需求书内容存为历史版本（生成/保存/回滚前调用）。"""
    if not order.requirement:
        return
    from ..models import RequirementVersion

    db.add(RequirementVersion(
        order_id=order.id,
        document=order.requirement,
        source=order.requirement_source,
        created_by=user.id if user else None,
        username=user.username if user else "-",
        remark=(remark or "")[:200] or None,
    ))


def get_order_or_404(db: Session, order_id: str) -> Order:
    order = order_query(db).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order


def ensure_access(order: Order, user: User) -> None:
    if not can_access(order, user):
        raise HTTPException(status_code=403, detail="无权访问该订单")


# 固定预设兜底（与前端原候选一致）；历史订单用过的技术栈会动态排在预设之前
TECH_PRESETS = [
    "SpringBoot+Vue3", "Django", "JSP+Servlet", "Flask", "SpringBoot+Vue3+MySQL",
    "微信小程序+SpringBoot", "Vue3+Node.js", "Python数据分析", "Swing桌面应用",
]


@router.get("/tech-suggestions")
def tech_suggestions(
    title: str = Query(default="", max_length=255),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """技术栈动态候选：历史订单实际用过的技术栈（与题目语言/形态相关者优先）+ 固定预设兜底。

    AI 生成订单会回写 tech_stack，因此同类型新订单创建时能直接复用之前
    AI 判定过的技术栈，而不必局限于静态预设。
    """
    from sqlalchemy import func as _func

    rows = (
        db.query(Order.tech_stack, _func.count(Order.id).label("cnt"))
        .filter(Order.is_deleted == False, Order.tech_stack.isnot(None))  # noqa: E712
        .group_by(Order.tech_stack).all()
    )
    hist = [ts.strip() for ts, _ in sorted(rows, key=lambda r: -r[1]) if ts and ts.strip()]

    t = (title or "").lower()

    def related(ts: str) -> int:
        """与题目同族（Python/Java/小程序/数据分析…）的历史技术栈排前面。"""
        low = ts.lower()
        score = 0
        if "python" in t and any(k in low for k in ("python", "django", "flask", "scrapy", "pandas", "requests")):
            score += 2
        if any(k in t for k in ("spring", "java")) and any(k in low for k in ("spring", "java", "maven", "mybatis")):
            score += 2
        if "小程序" in t and "小程序" in low:
            score += 2
        if any(k in t for k in ("爬虫", "采集", "数据分析", "可视化", "舆情", "口碑", "分析")) and any(
                k in low for k in ("scrapy", "pandas", "echarts", "爬虫", "分析", "flask")):
            score += 2
        if any(k in t for k in ("jsp", "servlet")) and any(k in low for k in ("jsp", "servlet")):
            score += 2
        if any(k in t for k in ("swing", "javafx", "桌面")) and any(k in low for k in ("swing", "javafx")):
            score += 2
        return -score

    ranked = sorted(hist, key=related)
    merged = ranked + [p for p in TECH_PRESETS if p not in ranked]
    return {"items": [{"value": v} for v in merged[:24]]}


@router.get("")
def list_orders(
    status: str | None = Query(default=None),
    quality: str | None = Query(default=None),
    agent_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None, max_length=100),
    project_type: str | None = Query(default=None, pattern=r"^(program|thesis|thesis_program)$"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = order_query(db)
    if user.role == "agent":
        q = q.filter(Order.agent_user_id == user.id)
    else:
        if agent_id:
            q = q.filter(Order.agent_user_id == agent_id)
    if status:
        q = q.filter(Order.status == status)
    if quality:
        # 用 join 而不是在 WHERE 里塞 Order.quality_id == Quality.id，
        # 后者会让 SQLAlchemy 把 quality 表塞进 FROM，形成隐式笛卡尔积。
        q = q.join(Quality).filter(Quality.code == quality)
    if project_type:
        q = q.filter(Order.project_type == project_type)
    if keyword:
        kw = f"%{keyword.strip()}%"
        q = q.filter(or_(Order.title.like(kw), Order.id.like(kw)))
    if date_from:
        q = q.filter(Order.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        q = q.filter(Order.created_at < datetime.combine(date_to + timedelta(days=1), time.min))

    total = q.count()
    items = (
        q.order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    # 批量取每单最新一个演示视频（列表缩略图用），避免 N+1
    ids = [o.id for o in items]
    video_map: dict[str, dict] = {}
    if ids:
        vids = (
            db.query(OrderFile)
            .filter(
                OrderFile.order_id.in_(ids),
                OrderFile.is_deleted == False,  # noqa: E712
                OrderFile.category == "video",
            )
            .order_by(OrderFile.created_at.desc())
            .all()
        )
        from ..services.files_svc import thumb_path_for

        for f in vids:
            video_map.setdefault(f.order_id, {
                "id": f.id,
                "name": f.original_name,
                # 没有生成缩略图时前端直接显示占位块，避免每张缩略图打一次 404
                "has_thumb": thumb_path_for(f) is not None,
            })
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        # 真实价可见性由后端下发的统一开关决定，前端不再自行推断（fail-closed）
        "show_money": user.role == "admin",
        "items": [_list_item(o, user, video_map.get(o.id)) for o in items],
    }


def _list_item(order: Order, user: User, video: dict | None) -> dict:
    """列表项：附带下载权限；无权限时不下发视频元数据，避免前端请求必然 403 的缩略图。"""
    view = order_view(order, user.role, video=video)
    allowed = can_download(order, user)
    view["can_download"] = allowed
    if not allowed:
        view["video"] = None
    return view


@router.post("")
def create_order_endpoint(
    body: OrderCreateIn,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent_user = None
    # 写手不接单：订单只能由管理员或代理（销售/同行）创建，写手仅制作侧操作
    if user.role == "staff":
        raise HTTPException(status_code=403, detail="写手不能创建订单，请联系管理员或代理下单")
    rate_limit(request, "order_create", f"{user.id}:{client_ip(request)}", limit=30, window_seconds=60)
    if user.role == "agent":
        agent_user = user
    elif body.agent_username:
        agent_user = db.query(User).filter(
            User.username == body.agent_username, User.role == "agent", User.is_active == True  # noqa: E712
        ).first()
        if not agent_user:
            raise HTTPException(status_code=400, detail=f"代理不存在或已禁用: {body.agent_username}")

    # 创建时覆盖真实价属敏感操作，需密码二次确认
    if user.role == "admin" and body.owner_price is not None:
        from ..deps import require_password_confirm
        require_password_confirm(request, user)

    try:
        order = create_order(
            db,
            title=body.title,
            quality_code=body.quality_code,
            creator=user,
            deadline=body.deadline,
            tech_stack=body.tech_stack,
            customer_info=body.customer_info,
            remark=body.remark,
            source_requirement=body.source_requirement,
            source_apply_mode=body.source_apply_mode,
            requirement_notes=body.requirement_notes,
            agent_user=agent_user,
            # 新字段优先；只传旧工种值时归一映射，保证旧表单/脚本不断
            project_type=normalize_project_type(body.project_type, body.category),
            # 成交价：管理员可改（需密码确认，见上）；代理下单填的就是自己要付的成交价
            owner_price_override=(body.owner_price if user.role in ("admin", "agent") else None),
            # 自定义编号仅管理员/协助者可用；代理一律自动取号
            order_no=(body.order_no if user.role in ("admin", "staff") else None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    log_op(
        db, "order_create", request=request, user=user,
        entity_type="order", entity_id=order.id,
        detail={
            "title": order.title,
            "quality": order.quality.code if order.quality else "",
            "project_type": order.project_type,
            "owner_price": float(order.owner_price),
            "agent_price": float(order.agent_price),
            "price_override": bool(user.role == "admin" and body.owner_price is not None),
            "agent": agent_user.username if agent_user else None,
            "has_source_requirement": bool(order.source_requirement),
            "has_requirement_notes": bool(order.requirement_notes),
            "custom_order_no": bool(user.role in ("admin", "staff") and body.order_no),
        },
    )
    # 站内通知：管理员与全部写手（制作侧）+ 订单代理本人（非创建者）
    from ..services.notify_svc import notify_order_created
    notify_order_created(db, order, user.id)
    db.commit()
    background.add_task(
        _notify_created,
        order.id, order.title,
        (agent_user.display_name or agent_user.username) if agent_user else None,
        float(order.owner_price),
    )
    return {"order": order_view(order, user.role)}


def _notify_created(order_id, title, agent_name, price):
    from ..services.webhook import notify_order_created
    notify_order_created(order_id, title, agent_name, price)


@router.post("/batch-status")
def batch_change_status(
    body: BatchStatusIn,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """批量流转状态：逐单按白名单校验，非法跳转跳过并说明原因，不会部分失败回滚其他单。"""
    # 加锁顺序固定，避免并发批量操作互相死锁；去重并限制上限。
    # total/skipped 必须按实际处理集合计算，否则重复 id 或超 100 条会虚报处理范围。
    requested_ids = list(dict.fromkeys(body.ids))
    ids = requested_ids[:100]
    ignored = len(body.ids) - len(ids)
    truncated = len(requested_ids) > 100
    orders = {
        o.id: o
        for o in order_query(db).filter(Order.id.in_(ids)).order_by(Order.id).with_for_update().all()
    }
    results = []
    changed = 0
    for oid in ids:
        order = orders.get(oid)
        if not order:
            results.append({"id": oid, "ok": False, "reason": "订单不存在或已在回收站"})
            continue
        if not can_change_status(order, user, body.status):
            reason = "已取消订单为终态，不能恢复；如需继续请新建订单" if order.status == "cancelled" \
                else "无权推进该订单状态（仅负责人可操作，结单需管理员）"
            results.append({"id": oid, "ok": False, "reason": reason})
            continue
        old = order.status
        try:
            # 权限已由 can_change_status 校验（管理员可改非取消订单状态，写手仅推进），这里跳过流程图表校验。
            if not set_order_status(order, body.status, allow_any=True):
                raise ValueError("订单已是该状态")
        except ValueError as exc:
            results.append({"id": oid, "ok": False, "reason": str(exc)})
            continue
        log_op(
            db, "order_status", request=request, user=user,
            entity_type="order", entity_id=order.id,
            detail={"before": old, "after": body.status, "batch": True},
        )
        from ..services.notify_svc import notify_status_changed
        notify_status_changed(db, order, user.id, body.status)
        background.add_task(_notify_status, order.id, order.title, old, body.status)
        results.append({"id": oid, "ok": True, "before": old, "after": body.status})
        changed += 1
    db.commit()
    return {
        "changed": changed,
        "skipped": len(ids) - changed,
        "total": len(ids),
        "ignored": ignored,
        "truncated": truncated,
        "results": results,
    }


@router.post("/check-duplicate")
def check_duplicate(
    body: TitleCheckIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """相似题目撞单检测：管理端全库比对；代理只比对自己名下订单（不泄露他人题目）。"""
    from difflib import SequenceMatcher

    rate_limit(request, "duplicate", f"{user.id}:{client_ip(request)}", limit=30, window_seconds=60)
    title = body.title.strip()
    if len(title) < 4:
        return {"duplicates": []}
    q = order_query(db).with_entities(Order.id, Order.title, Order.status)
    if user.role == "agent":
        q = q.filter(Order.agent_user_id == user.id)
    # 只比对最近 800 单，避免全表 SequenceMatcher 造成 CPU 放大。
    rows = q.order_by(Order.created_at.desc()).limit(800).all()
    duplicates = []
    for oid, t, st in rows:
        ratio = SequenceMatcher(None, title, (t or "").strip()).ratio()
        if ratio >= 0.55:
            duplicates.append({"id": oid, "title": t, "status": st, "similarity": round(ratio * 100)})
    duplicates.sort(key=lambda x: -x["similarity"])
    return {"duplicates": duplicates[:5]}


@router.get("/export")
def export_orders_csv(
    request: Request,
    status: str | None = Query(default=None),
    quality: str | None = Query(default=None),
    project_type: str | None = Query(default=None, pattern=r"^(program|thesis|thesis_program)$"),
    agent_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None, max_length=100),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """订单列表导出 CSV（Excel 可直接打开）。含真实价，仅管理员。"""
    import csv
    import io

    q = order_query(db)
    if status:
        q = q.filter(Order.status == status)
    if quality:
        q = q.join(Quality).filter(Quality.code == quality)
    if agent_id:
        q = q.filter(Order.agent_user_id == agent_id)
    if project_type:
        q = q.filter(Order.project_type == project_type)
    if keyword:
        kw = f"%{keyword.strip()}%"
        q = q.filter(or_(Order.title.like(kw), Order.id.like(kw)))
    if date_from:
        q = q.filter(Order.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        q = q.filter(Order.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
    q = q.order_by(Order.created_at.desc())

    STATUS_CN = {"pending": "待开始", "in_progress": "制作中", "completed": "已完成",
                 "closed": "已结单", "after_sale": "售后中", "cancelled": "已取消"}
    DEPLOY_CN = {"undeployed": "未部署", "deployed": "已部署", "not_required": "无需部署"}

    buf = io.StringIO()
    writer = csv.writer(buf)
    PT_CN = {"program": "纯程序设计", "thesis": "纯论文", "thesis_program": "论文+设计"}

    def cell(value):
        text = str(value or "")
        # Excel/Sheets 会把 = + - @ 开头的单元格当公式执行，文本前加单引号。
        return "'" + text if text[:1] in ("=", "+", "-", "@") else text

    writer.writerow(["单号", "题目", "项目类型", "品质", "倍率", "真实价", "代理价", "状态", "部署状态",
                     "交付期限", "来源代理", "制作负责人", "创建时间", "完成时间", "结单时间", "备注"])
    # 用 yield_per 游标批次从库里取，避免一次性 ORM 实例化全表；另设硬上限兜底内存。
    MAX_EXPORT_ROWS = 20000
    exported = 0
    truncated = False
    for o in q.yield_per(500):
        if exported >= MAX_EXPORT_ROWS:
            truncated = True
            break
        exported += 1
        writer.writerow([
            cell(o.id), cell(o.title),
            PT_CN.get(o.project_type, "未设置"),
            cell(o.quality.name if o.quality else ""), float(o.multiplier),
            float(o.owner_price), float(o.agent_price),
            STATUS_CN.get(o.status, o.status), DEPLOY_CN.get(o.deploy_status, o.deploy_status),
            o.deadline or "",
            cell(o.agent.username if o.agent else "自接"),
            cell(o.assignee.username if o.assignee else ""),
            str(o.created_at)[:19],
            str(o.completed_at or "")[:19], str(o.closed_at or "")[:19],
            cell((o.remark or "").replace("\n", " ")),
        ])
    if truncated:
        writer.writerow([f"（结果超过 {MAX_EXPORT_ROWS} 行已截断，请缩小筛选范围后再导出）"])
    log_op(
        db,
        "order_export",
        request=request,
        user=user,
        detail={"count": exported, "truncated": truncated},
    )
    db.commit()

    from urllib.parse import quote

    filename = f"orders-{date.today().strftime('%Y%m%d')}.csv"
    data = "\ufeff" + buf.getvalue()  # BOM 便于 Excel 识别 UTF-8
    return StreamingResponse(
        iter([data]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/trash/list")
def list_trash(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = trash_query(db)
    total = q.count()
    items = q.order_by(Order.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [order_view(o, user.role) for o in items]}


@router.post("/{order_id}/restore")
def restore_order(
    order_id: str,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    order = trash_query(db).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="回收站中不存在该订单")
    order.is_deleted = False
    log_op(db, "order_restore", request=request, user=user, entity_type="order", entity_id=order.id)
    db.commit()
    return {"order": order_view(order, user.role)}


@router.delete("/{order_id}")
def delete_order(
    order_id: str,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from ..deps import require_password_confirm

    require_password_confirm(request, user)
    order = order_query(db).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    order.is_deleted = True
    log_op(db, "order_trash", request=request, user=user, entity_type="order", entity_id=order.id)
    db.commit()
    return {"ok": True}


@router.post("/ai/analyze-title")
def ai_analyze_title(
    request: Request,
    body: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI 分析题目：推荐项目类型/技术栈/难度。"""
    from ..services.ai_extra import AIError, analyze_title
    rate_limit(request, "ai_title", f"{user.id}:{client_ip(request)}", limit=10, window_seconds=60)
    from ..services.ai_quota import ensure_ai_quota

    ensure_ai_quota(db, user.id)
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体格式错误")
    title = str(body.get("title") or "").strip()
    if not title or len(title) < 2:
        raise HTTPException(status_code=400, detail="请输入题目")
    try:
        result = analyze_title(db, title, user_id=user.id)
        db.commit()  # AiUsage 记账随请求落库
        return {"analysis": result}
    except AIError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{order_id}/ai/summary")
def ai_order_summary(
    order_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI 生成订单智能摘要。"""
    from ..services.ai_extra import AIError, order_summary
    rate_limit(request, "ai_summary", f"{user.id}:{client_ip(request)}", limit=6, window_seconds=60)
    from ..services.ai_quota import ensure_ai_quota

    ensure_ai_quota(db, user.id)
    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    data = {
        "id": order.id, "title": order.title, "project_type": order.project_type,
        "status": order.status,
        "quality": order.quality.name if order.quality else "",
        "deadline": str(order.deadline) if order.deadline else None,
        "deploy_status": order.deploy_status,
    }
    try:
        summary = order_summary(db, data, user_id=user.id)
        db.commit()  # AiUsage 记账随请求落库
        return {"summary": summary}
    except AIError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/reminders")
def order_reminders(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """到期提醒：已逾期 + 3 天内到期（未完结订单）。代理只看自己的。"""
    from datetime import date as date_cls

    today = date_cls.today()
    soon = today + timedelta(days=3)
    base = order_query(db).filter(
        Order.deadline.isnot(None),
        Order.status.in_(("pending", "in_progress", "after_sale")),
    )
    if user.role == "agent":
        base = base.filter(Order.agent_user_id == user.id)
    # 逾期与临期分别用 SQL 过滤 + LIMIT，避免先全量加载再在 Python 里切片；
    # 同时单独统计总数，保证提醒铃的计数不被 20 条的分页上限截断。
    overdue_q = base.filter(Order.deadline < today)
    soon_q = base.filter(Order.deadline >= today, Order.deadline <= soon)
    overdue_total = overdue_q.count()
    soon_total = soon_q.count()
    overdue = overdue_q.order_by(Order.deadline.asc()).limit(20).all()
    due_soon = soon_q.order_by(Order.deadline.asc()).limit(20).all()
    return {
        "overdue": [order_view(o, user.role) for o in overdue],
        "due_soon": [order_view(o, user.role) for o in due_soon],
        "count": overdue_total + soon_total,
        "overdue_total": overdue_total,
        "due_soon_total": soon_total,
        "truncated": overdue_total > 20 or soon_total > 20,
    }


def _calendar_query(db: Session, user: User, start: date, end: date):
    """日历/ICS 共用的区间校验与角色过滤，避免两处口径漂移。"""
    if end < start:
        raise HTTPException(status_code=400, detail="结束日期不能早于开始日期")
    if (end - start).days > 62:
        raise HTTPException(status_code=400, detail="日历一次最多查询 62 天")

    q = order_query(db).filter(
        Order.deadline.isnot(None),
        Order.deadline >= start,
        Order.deadline <= end,
    )
    if user.role == "agent":
        q = q.filter(Order.agent_user_id == user.id)
    return q


def _ics_escape(value) -> str:
    """RFC 5545 文本转义：反斜杠、分号、逗号与换行都不能原样输出。"""
    text = str(value or "")
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _ics_fold(line: str) -> str:
    """按 RFC 5545 在 75 字节处折行，续行以空格开头且不切断 UTF-8 字符。"""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks = []
    start = 0
    first = True
    while start < len(raw):
        # 续行开头的空格也占 1 字节，因此续行正文最多 74 字节。
        limit = 75 if first else 74
        end = min(start + limit, len(raw))
        while end > start:
            try:
                chunk = raw[start:end].decode("utf-8")
                break
            except UnicodeDecodeError:
                end -= 1
        else:
            chunk = ""
        if not chunk:
            break
        chunks.append(chunk if first else " " + chunk)
        start = end
        first = False
    return "\r\n".join(chunks)


def _ics_status(status: str) -> str:
    if status == "cancelled":
        return "CANCELLED"
    if status == "pending":
        return "TENTATIVE"
    return "CONFIRMED"


@router.get("/calendar")
def order_calendar(
    start: date = Query(description="起始日期（含）"),
    end: date = Query(description="结束日期（含）"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """订单日历：按交付期限（deadline）取出区间内的订单，代理仍只看自己名下。

    单独开接口而不是给列表加参数，是因为日历一次要拿整个月的订单，
    列表接口的 100 条分页上限会把月末订单截掉。
    """
    q = _calendar_query(db, user, start, end)
    total = q.count()
    orders = (
        q.order_by(Order.deadline.asc(), Order.created_at.asc())
        .limit(500)
        .all()
    )
    today = date.today()
    items = []
    overdue = open_count = done = cancelled = 0
    for o in orders:
        view = order_view(o, user.role)
        items.append({
            "id": view["id"],
            "title": view["title"],
            "deadline": view["deadline"],
            "status": view["status"],
            "project_type": view["project_type"],
            "quality": view["quality"],
            "agent": view["agent"],
            "assignee": view["assignee"],
        })
        if o.status == "cancelled":
            cancelled += 1
        elif o.status in ("closed", "after_sale"):
            done += 1
        else:
            if o.status in ("pending", "in_progress"):
                open_count += 1
            if o.deadline < today:
                overdue += 1

    return {
        "start": start,
        "end": end,
        "today": today,
        "total": total,
        "truncated": total > 500,
        "summary": {
            "open": open_count,
            "done": done,
            "overdue": overdue,
            "cancelled": cancelled,
        },
        "items": items,
    }


@router.get("/calendar.ics")
def order_calendar_ics(
    start: date = Query(description="起始日期（含）"),
    end: date = Query(description="结束日期（含）"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """把当前区间导出为 ICS 日历文件，可直接导入系统日历或订阅。"""
    q = _calendar_query(db, user, start, end)
    orders = (
        q.order_by(Order.deadline.asc(), Order.created_at.asc())
        .limit(500)
        .all()
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//BS Order System//Order Calendar//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:订单交期",
        "X-WR-TIMEZONE:Asia/Shanghai",
    ]
    for o in orders:
        view = order_view(o, user.role)
        quality = (view.get("quality") or {}).get("name") or "未定级"
        assignee = view.get("assignee") or "未分派"
        agent = view.get("agent") or "自接"
        status_cn = STATUS_CN.get(o.status, o.status)
        desc = (
            f"单号：{o.id}\n"
            f"状态：{status_cn}\n"
            f"品质：{quality}\n"
            f"负责人：{assignee}\n"
            f"代理：{agent}"
        )
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{_ics_escape(o.id)}@bs-order-system.local",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{o.deadline.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(o.deadline + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_ics_escape(o.title)}",
            f"DESCRIPTION:{_ics_escape(desc)}",
            f"CATEGORIES:{_ics_escape(quality)}",
            f"STATUS:{_ics_status(o.status)}",
            "TRANSP:TRANSPARENT",
            "SEQUENCE:0",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    body = "\r\n".join(_ics_fold(line) for line in lines) + "\r\n"
    filename = f"orders_{start.isoformat()}_{end.isoformat()}.ics"
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


class OrderDeadlineIn(BaseModel):
    deadline: date


@router.patch("/{order_id}/deadline")
def update_order_deadline(
    order_id: str,
    body: OrderDeadlineIn,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """日历拖拽改期：仅管理员可调整交期，写手/代理不能改客户承诺日期。"""
    rate_limit(request, "order_deadline", f"{user.id}:{client_ip(request)}", limit=60, window_seconds=60)
    order = get_order_or_404(db, order_id)
    if order.status == "cancelled":
        raise HTTPException(status_code=400, detail="已取消订单不可改期")
    old = order.deadline
    if old == body.deadline:
        return {
            "changed": False,
            "deadline": body.deadline.isoformat(),
            "order": order_view(order, user.role),
        }

    order.deadline = body.deadline
    log_op(
        db, "order_deadline_update", request=request, user=user,
        entity_type="order", entity_id=order.id,
        detail={
            "before": old.isoformat() if old else None,
            "after": body.deadline.isoformat(),
            "source": "calendar_drag",
        },
    )
    db.commit()
    db.refresh(order)
    return {
        "changed": True,
        "deadline": body.deadline.isoformat(),
        "order": order_view(order, user.role),
    }


def _role_label_map(db: Session) -> dict[str, str]:
    """用户名 → 个性角色标签（如“高级鸽子”）；时间线/日志按用户名快照存储，读取时补当前标签。"""
    rows = db.query(User.username, User.role_label).filter(User.role_label.isnot(None)).all()
    return {u: lb for u, lb in rows if lb}


@router.get("/{order_id}/notes")
def list_notes(
    order_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """订单跟进记录（时间线）：管理员/写手/该单代理可见。"""
    from ..models import OrderNote

    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    notes = (
        db.query(OrderNote)
        .filter(OrderNote.order_id == order.id)
        .order_by(OrderNote.created_at.desc())
        .limit(100)
        .all()
    )
    labels = _role_label_map(db)
    return {"notes": [
        {"id": n.id, "username": n.username, "role": n.role,
         "role_label": labels.get(n.username), "content": n.content, "created_at": n.created_at}
        for n in notes
    ]}


class NoteCreateIn(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


@router.post("/{order_id}/notes")
def add_note(
    order_id: str,
    body: NoteCreateIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新增跟进记录（与客户/团队的沟通日志）。"""
    from ..models import OrderNote

    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    note = OrderNote(
        order_id=order.id, user_id=user.id, username=user.username, role=user.role,
        content=body.content.strip(),
    )
    db.add(note)
    log_op(db, "order_note", request=request, user=user, entity_type="order", entity_id=order.id,
           detail={"content": body.content.strip()[:80]})
    db.commit()
    return {"note": {"id": note.id, "username": note.username, "role": note.role,
                     "role_label": user.role_label or None,
                     "content": note.content, "created_at": note.created_at}}


@router.get("/{order_id}/receipt")
def order_receipt(
    order_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """收款凭证 PDF（代理发给客户的收款确认单，金额为成交价）。写手不可下载：写手不见成交价。"""
    from ..services.receipt_svc import render_receipt
    from ..services.settings_svc import get_settings_map

    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    if user.role == "staff":
        raise HTTPException(status_code=403, detail="收款凭证含成交价，仅管理员与该单代理可下载")
    site_name = get_settings_map(db, ["site_name"]).get("site_name", "") or "毕设接单"
    holder = (order.agent.display_name or order.agent.username) if order.agent else None
    buf = render_receipt(order, site_name=site_name, holder_name=holder)
    log_op(db, "order_receipt", request=request, user=user, entity_type="order", entity_id=order.id)
    db.commit()

    illegal = '\\/:*?"<>|\r\n\t'
    safe_title = "".join(ch for ch in (order.title or "") if ch not in illegal).strip()[:60] or "未命名"
    filename = f"{order.id}-收款凭证-{safe_title}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/{order_id}")
def get_order(
    order_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    view = order_view(order, user.role, with_requirement=False)
    view["allowed_statuses"] = allowed_statuses(order, user)
    view["revert_target"] = revert_target(order, user)
    pending_revert = (
        db.query(StatusRevertRequest)
        .filter(StatusRevertRequest.order_id == order.id, StatusRevertRequest.status == "pending")
        .order_by(StatusRevertRequest.created_at.desc())
        .first()
    )
    view["status_revert"] = revert_view(pending_revert) if pending_revert else None

    files = (
        db.query(OrderFile)
        .filter(OrderFile.order_id == order.id, OrderFile.is_deleted == False)  # noqa: E712
        .order_by(OrderFile.created_at.desc())
        .all()
    )
    view["files"] = [file_view(f) for f in files]
    first_video = next((f for f in files if f.category == "video"), None)
    view["video"] = {"id": first_video.id, "name": first_video.original_name} if first_video else None

    logs = (
        db.query(OperationLog)
        .filter(OperationLog.entity_type == "order", OperationLog.entity_id == order.id)
        .order_by(OperationLog.created_at.desc())
        .limit(50)
        .all()
    )

    def _redact_detail(detail):
        # 审计原文保留在库中；非管理员视角按角色抹去不该看到的价格，防止日志旁路泄漏：
        # 写手不见成交价/倍率，代理不见写手价/倍率（写手价是内部成本）。
        if user.role == "admin" or not isinstance(detail, dict):
            return detail
        hidden = ("agent_price", "multiplier") if user.role == "agent" else ("owner_price", "multiplier")
        for key in hidden:
            detail.pop(key, None)
        for section in ("before", "after"):
            if isinstance(detail.get(section), dict):
                for key in hidden:
                    detail[section].pop(key, None)
        return detail

    def _safe_detail(raw):
        if not raw:
            return None
        try:
            return _redact_detail(json.loads(raw))
        except (ValueError, TypeError):
            return None

    labels = _role_label_map(db)
    view["logs"] = [
        {
            "id": lg.id,
            "username": lg.username,
            "role": lg.role,
            "role_label": labels.get(lg.username),
            "action": lg.action,
            "detail": _safe_detail(lg.detail),
            "ip": lg.ip,
            "created_at": lg.created_at,
        }
        for lg in logs
    ]
    return {"order": view}


@router.patch("/{order_id}")
def update_order(
    order_id: str,
    body: OrderUpdateIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = get_order_or_404(db, order_id)
    ensure_access(order, user)

    changes: dict = {}
    before: dict = {}
    fields = body.model_fields_set

    def apply(field: str, new_value):
        old_value = getattr(order, field)
        if new_value != old_value:
            before[field] = old_value
            setattr(order, field, new_value)
            changes[field] = new_value

    if user.role == "agent" and order.agent_user_id != user.id and order.created_by != user.id:
        raise HTTPException(status_code=403, detail="代理只能修改自己的订单")

    if "title" in fields and body.title is not None:
        title = body.title.strip()
        if len(title) < 2:
            raise HTTPException(status_code=400, detail="题目至少 2 个字符")
        apply("title", title)
    # 项目类型变更：从含论文改为纯程序设计会丢掉论文留档入口，已存在留档时禁止
    if "project_type" in fields and body.project_type and body.project_type != order.project_type:
        if body.project_type == "program" and order.project_type in ("thesis", "thesis_program"):
            from ..models import OrderPaperDoc

            has_docs = (
                db.query(OrderPaperDoc.id)
                .filter(OrderPaperDoc.order_id == order.id)
                .first()
                is not None
            )
            if has_docs:
                raise HTTPException(
                    status_code=400,
                    detail="该订单已有论文留档（任务书/开题报告/初稿/终稿），不能改为纯程序设计",
                )
        before["project_type"] = order.project_type
        order.project_type = body.project_type
        # 遗留列同步推导，外部 SQL/历史统计不受影响
        order.category = derive_category(body.project_type)
        changes["project_type"] = body.project_type
    # 传 null 或空串 = 清空；未传 = 不修改（Pydantic model_fields_set 区分）
    # 交期是对客户的承诺日期：仅管理员可改（与日历改期接口一致），写手/代理只能原样回传
    if "deadline" in fields:
        if body.deadline != order.deadline and user.role != "admin":
            raise HTTPException(status_code=403, detail="仅管理员可修改交付期限")
        apply("deadline", body.deadline)
    if "tech_stack" in fields:
        apply("tech_stack", (body.tech_stack or "").strip() or None)
    if "customer_info" in fields:
        apply("customer_info", (body.customer_info or "").strip() or None)
    if "remark" in fields:
        apply("remark", (body.remark or "").strip() or None)
    # 原始需求资料：全文可能上万字，日志只记字数变化，不落全文
    if "source_requirement" in fields:
        new_src = (body.source_requirement or "").strip() or None
        if new_src != order.source_requirement:
            before["source_requirement"] = _len_mark(order.source_requirement)
            order.source_requirement = new_src
            changes["source_requirement"] = _len_mark(new_src)
    if "requirement_notes" in fields:
        new_notes = (body.requirement_notes or "").strip() or None
        if new_notes != order.requirement_notes:
            before["requirement_notes"] = _len_mark(order.requirement_notes)
            order.requirement_notes = new_notes
            changes["requirement_notes"] = _len_mark(new_notes)
    # 上传需求书应用方式：reference=参考生成 / direct=原文直接应用
    if "source_apply_mode" in fields and body.source_apply_mode in ("reference", "direct"):
        if body.source_apply_mode != order.source_apply_mode:
            before["source_apply_mode"] = order.source_apply_mode or "reference"
            order.source_apply_mode = body.source_apply_mode
            changes["source_apply_mode"] = body.source_apply_mode

    # 品质变更 → 重新计价（管理员可同时显式指定真实价）
    if body.quality_code and body.quality_code != (order.quality.code if order.quality else ""):
        # 品质决定成交价与写手价，改品质等于改价：仅管理员可改（写手调高品质会直接抬高自己的写手价）
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="仅管理员可修改品质")
        quality = get_quality_by_code(db, body.quality_code)
        if not quality:
            raise HTTPException(status_code=400, detail=f"品质不存在或已停用: {body.quality_code}")
        owner_price, agent_price, multiplier = compute_prices(db, quality)
        if user.role == "admin" and body.owner_price is not None:
            from ..deps import require_password_confirm
            require_password_confirm(request, user)
            if float(body.owner_price) < float(agent_price):
                raise HTTPException(
                    status_code=400,
                    detail=f"真实价不能低于代理价（当前代理价 {float(agent_price):.2f}），否则毛利为负",
                )
            owner_price = body.owner_price
        before.update({"quality": order.quality.code, "owner_price": float(order.owner_price),
                       "agent_price": float(order.agent_price)})
        order.quality_id = quality.id
        order.multiplier = multiplier
        order.owner_price = owner_price
        order.agent_price = agent_price
        changes.update({"quality": quality.code, "owner_price": float(owner_price),
                        "agent_price": float(agent_price)})
    elif body.owner_price is not None and user.role == "admin":
        if float(body.owner_price) != float(order.owner_price):
            from ..deps import require_password_confirm
            require_password_confirm(request, user)
            if float(body.owner_price) < float(order.agent_price):
                raise HTTPException(
                    status_code=400,
                    detail=f"真实价不能低于代理价（当前代理价 {float(order.agent_price):.2f}），否则毛利为负",
                )
            before["owner_price"] = float(order.owner_price)
            order.owner_price = body.owner_price
            changes["owner_price"] = float(body.owner_price)

    if body.agent_username is not None and user.role == "admin":
        if body.agent_username == "":
            before["agent"] = order.agent.username if order.agent else None
            order.agent_user_id = None
            changes["agent"] = None
        else:
            agent_user = db.query(User).filter(
                User.username == body.agent_username, User.role == "agent", User.is_active == True  # noqa: E712
            ).first()
            if not agent_user:
                raise HTTPException(status_code=400, detail=f"代理不存在: {body.agent_username}")
            before["agent"] = order.agent.username if order.agent else None
            order.agent_user_id = agent_user.id
            changes["agent"] = agent_user.username

    if body.assignee_username is not None:
        current_assignee = order.assignee.username if order.assignee else ""
        if user.role != "admin":
            # 写手只能推进自己的单，不能改派/自领他人订单（否则可借此拿到下载权限）。
            if body.assignee_username != current_assignee:
                raise HTTPException(status_code=403, detail="仅管理员可变更订单负责人")
        elif body.assignee_username == "":
            before["assignee"] = order.assignee.username if order.assignee else None
            order.assignee_user_id = None
            changes["assignee"] = None
        else:
            assignee = db.query(User).filter(
                User.username == body.assignee_username, User.role.in_(("admin", "staff")),
                User.is_active == True,  # noqa: E712
            ).first()
            if not assignee:
                raise HTTPException(status_code=400, detail=f"协助者不存在: {body.assignee_username}")
            before["assignee"] = order.assignee.username if order.assignee else None
            order.assignee_user_id = assignee.id
            changes["assignee"] = assignee.username

    if not changes:
        raise HTTPException(status_code=400, detail="没有需要修改的字段")

    log_op(
        db, "order_update", request=request, user=user,
        entity_type="order", entity_id=order.id, detail={"before": before, "after": changes},
    )
    db.commit()
    db.refresh(order)  # 刷新关系（agent/assignee/quality），避免 expire_on_commit=False 下的旧缓存
    return {"order": order_view(order, user.role)}


@router.get("/{order_id}/status-revert")
def get_status_revert(
    order_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """订单当前的待审批撤回申请（无则 null），供详情页内联展示。"""
    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    req = (
        db.query(StatusRevertRequest)
        .filter(StatusRevertRequest.order_id == order.id, StatusRevertRequest.status == "pending")
        .order_by(StatusRevertRequest.created_at.desc())
        .first()
    )
    return {
        "request": revert_view(req) if req else None,
        "target": revert_target(order, user),
        "allowed_statuses": allowed_statuses(order, user),
    }


@router.post("/{order_id}/status-revert")
def create_status_revert(
    order_id: str,
    body: StatusRevertIn,
    request: Request,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """写手申请撤回一次手误的状态推进，由管理员审批后生效。"""
    if user.role != "staff":
        raise HTTPException(status_code=400, detail="管理员可直接修改状态，无需提交撤回申请")
    order = order_query(db).filter(Order.id == order_id).with_for_update().first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    target = revert_target(order, user)
    if not target:
        raise HTTPException(status_code=403, detail="仅订单负责人可对制作中/已完成订单申请撤回")
    if body.to_status != target:
        raise HTTPException(
            status_code=400,
            detail=f"当前状态「{STATUS_CN.get(order.status, order.status)}」只能撤回为「{STATUS_CN.get(target, target)}」",
        )
    reason = body.reason.strip()
    if len(reason) < 2:
        raise HTTPException(status_code=400, detail="请填写撤回原因（至少 2 个字符）")
    exists = (
        db.query(StatusRevertRequest)
        .filter(StatusRevertRequest.order_id == order.id, StatusRevertRequest.status == "pending")
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="该订单已有待审批的撤回申请，请等待管理员处理")

    row = StatusRevertRequest(
        order_id=order.id,
        requested_by=user.id,
        username=user.display_name or user.username,
        from_status=order.status,
        to_status=target,
        reason=reason,
        status="pending",
    )
    db.add(row)
    db.flush()

    from ..services.notify_svc import push

    admins = db.query(User).filter(User.role == "admin", User.is_active == True).all()  # noqa: E712
    push(
        db, [a.id for a in admins],
        f"撤回审批：订单 {order.id}",
        body=(
            f"{row.username} 申请将订单从「{STATUS_CN.get(order.status, order.status)}」"
            f"撤回为「{STATUS_CN.get(target, target)}」：{reason}"
        ),
        order_id=order.id,
    )
    log_op(
        db, "status_revert_request", request=request, user=user,
        entity_type="order", entity_id=order.id,
        detail={"request_id": row.id, "from": order.status, "to": target, "reason": reason},
    )
    db.commit()
    db.refresh(row)
    return {"request": revert_view(row)}


@router.post("/{order_id}/status")
def change_status(
    order_id: str,
    body: StatusIn,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    order = order_query(db).filter(Order.id == order_id).with_for_update().first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if not can_change_status(order, user, body.status):
        detail = "已取消订单为终态，不能恢复；如需继续请新建订单" if order.status == "cancelled" \
            else "无权推进该订单状态（仅负责人可操作，结单需管理员）"
        raise HTTPException(status_code=403, detail=detail)
    old = order.status
    try:
        # 权限已由 can_change_status 校验（管理员可改非取消订单状态，写手仅推进），这里跳过流程图表校验。
        if not set_order_status(order, body.status, allow_any=True):
            raise ValueError(f"订单已是该状态: {body.status}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    log_op(
        db, "order_status", request=request, user=user,
        entity_type="order", entity_id=order.id,
        detail={"before": old, "after": body.status},
    )
    from ..services.notify_svc import notify_status_changed
    notify_status_changed(db, order, user.id, body.status)
    db.commit()
    background.add_task(_notify_status, order.id, order.title, old, body.status)
    return {"order": order_view(order, user.role)}


def _notify_status(order_id, title, old, new):
    from ..services.webhook import notify_status_changed
    notify_status_changed(order_id, title, old, new)


@router.delete("/{order_id}/requirement")
def delete_requirement(
    order_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除需求书（保留版本历史供恢复）。代理/写手/管理员均可操作自己的订单。"""
    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    if not order.requirement:
        raise HTTPException(status_code=404, detail="该订单尚未生成需求书")
    snapshot_requirement(db, order, user, remark="删除前快照")
    order.requirement = None
    order.requirement_source = None
    order.requirement_updated_at = None
    log_op(db, "requirement_delete", request=request, user=user,
           entity_type="order", entity_id=order.id)
    db.commit()
    return {"ok": True, "message": "需求书已删除（可在历史版本中恢复）"}


@router.post("/{order_id}/requirement/upload")
async def upload_requirement(
    order_id: str,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传需求书文件直接替换当前需求书。

    支持三种格式：
    - 本系统九章 JSON（.json）：直接导入（AI 生成的修改版回传场景）
    - Word（.docx）：提取文本 → 结构化解析 → 导入
    - TXT/Markdown：同 Word 处理
    """
    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    rate_limit(request, "req_upload", f"{user.id}:{client_ip(request)}", limit=10, window_seconds=60)

    data = await file.read()
    filename = file.filename or ""
    try:
        text, matched = extract_text(filename, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="未能从文件中提取到内容")
    # 上限与建单/编辑入参一致：超长直接拒绝，不做静默截断
    if len(text) > SOURCE_REQUIREMENT_MAX_CHARS:
        raise HTTPException(status_code=400, detail=f"文件内容过长（超过 {SOURCE_REQUIREMENT_MAX_CHARS:,} 字符），请精简或拆分后上传")

    # 优先识别本系统九章 JSON → 直接导入
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

    # 非系统格式：尝试结构化解析
    if document is None:
        imported = text_to_doc(order.title, text[:20000])
        if imported is not None:
            document = imported
            note = "已将上传文档解析为九章结构（内容未改写，可逐条编辑）"
        else:
            document = docgen.build_raw_doc(order.title, text[:20000])
            source = "manual"
            note = "上传文档按原文展示（未识别出章节结构）"

    # 快照旧版 → 替换
    if order.requirement:
        snapshot_requirement(db, order, user, remark="上传替换前快照")
    order.requirement = json.dumps(document, ensure_ascii=False)
    order.requirement_source = source
    order.requirement_updated_at = datetime.now()
    # 同步更新原始需求文本（后续 AI 重新生成时以此为参考）
    order.source_requirement = text[:20000]
    log_op(db, "requirement_upload", request=request, user=user,
           entity_type="order", entity_id=order.id,
           detail={"filename": filename[:100], "mode": document.get("mode", ""), "note": note})
    db.commit()
    return {"ok": True, "note": note, "document": document}


@router.post("/{order_id}/start-production")
def agent_start_production(
    order_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """代理确认需求书并开工：状态 待开始→制作中，站内通知管理员与写手安排制作。

    业务背景：代理（销售/同行）与客户沟通定稿需求书后，由此按钮通知后台进入制作；
    管理员/写手仍可按原有状态机各自推进。
    """
    if user.role != "agent":
        raise HTTPException(status_code=403, detail="该按钮供代理确认开工使用；写手请在详情页点「开始制作」")
    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    if order.status != "pending":
        raise HTTPException(status_code=400, detail=f"当前状态为「{STATUS_CN.get(order.status, order.status)}」，只有待开始的订单需要确认开工")
    if not order.requirement:
        raise HTTPException(status_code=400, detail="请先生成需求书并与客户确认后，再确认开工")

    old = order.status
    set_order_status(order, "in_progress")
    log_op(
        db, "order_status", request=request, user=user,
        entity_type="order", entity_id=order.id,
        detail={"before": old, "after": "in_progress", "via": "agent_start"},
    )
    # 通知：全体管理员 + 全体写手（重点标注已指派的负责人）
    from ..services.notify_svc import push
    staff_ids = [
        r[0] for r in db.query(User.id).filter(
            User.role.in_(("admin", "staff")), User.is_active == True  # noqa: E712
        ).all()
    ]
    agent_name = user.display_name or user.username
    assignee_name = order.assignee.display_name if order.assignee else None
    push(
        db, staff_ids,
        f"订单 {order.id} 已确认开工",
        body=(
            f"{agent_name} 已与客户确认需求书，订单《{order.title}》开始制作，请安排写手"
            + (f"（负责人：{assignee_name}）" if assignee_name else "")
        ),
        order_id=order.id,
    )
    db.commit()
    return {"order": order_view(order, user.role), "notified": len(staff_ids)}


@router.post("/{order_id}/deploy-status")
def change_deploy_status(
    order_id: str,
    body: DeployStatusIn,
    request: Request,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    order = get_order_or_404(db, order_id)
    old = order.deploy_status
    if old == body.deploy_status:
        raise HTTPException(status_code=400, detail=f"部署状态已是: {body.deploy_status}")
    order.deploy_status = body.deploy_status
    log_op(
        db, "order_deploy_status", request=request, user=user,
        entity_type="order", entity_id=order.id,
        detail={"before": old, "after": body.deploy_status},
    )
    db.commit()
    return {"order": order_view(order, user.role)}


@router.get("/{order_id}/requirement/diff")
def requirement_diff(
    order_id: str,
    request: Request,
    version_id: int = Query(...),
    ai: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """需求书修改对比：指定历史版本 vs 当前，结构化差异。"""
    from ..models import RequirementVersion
    from ..services.reqdiff import diff_documents, diff_text_for_ai, load_document

    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    ver = db.get(RequirementVersion, version_id)
    if not ver or ver.order_id != order.id:
        raise HTTPException(status_code=404, detail="历史版本不存在")
    old_doc = load_document(ver.document)
    new_doc = load_document(order.requirement)
    if not old_doc or not new_doc:
        raise HTTPException(status_code=404, detail="版本或当前需求书内容缺失")

    diffs = diff_documents(old_doc, new_doc)

    summary = None
    if ai and diffs:
        rate_limit(request, "ai_diff", f"{user.id}:{client_ip(request)}", limit=6, window_seconds=60)
        from ..services.ai_quota import ensure_ai_quota

        ensure_ai_quota(db, user.id)
        from ..services.ai_extra import skill_prompt
        from ..services.docgen.ai import AIGenerationError, deepseek_chat

        try:
            summary = deepseek_chat(
                db,
                skill_prompt(db, "req_diff",
                             "你是文档审校助手。根据需求书的版本差异列表，用不超过 150 字的中文概括本次修改的核心内容与意图，口吻客观。"),
                diff_text_for_ai(diffs),
                max_tokens=300, temperature=0.3,
                scene="diff", order_id=order.id,
            )
            db.commit()  # AiUsage 记账随请求落库
        except AIGenerationError:
            db.rollback()
            summary = None

    return {
        "version": {"id": ver.id, "source": ver.source, "username": ver.username, "created_at": ver.created_at,
                    "remark": ver.remark},
        "current_updated_at": order.requirement_updated_at,
        "diffs": diffs,
        "summary": summary,
    }


# ==================== 需求书 ====================

def _len_mark(text: str | None) -> str:
    """操作日志用长度标记：原始需求全文可能上万字，只记字数不落全文。"""
    return "<无>" if not text else f"<{len(text)} 字>"


@router.post("/parse-requirement-file")
async def parse_requirement_file(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """建单前解析客户原始需求文档：提取文字；本系统九章 JSON 标记为可直接导入。"""
    rate_limit(request, "req_parse", f"{user.id}:{client_ip(request)}", limit=20, window_seconds=60)
    data = await file.read()
    filename = file.filename or ""
    try:
        text, matched = extract_text(filename, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="未能从文件中提取到文字（可能是扫描件/图片型 PDF，请改传 Word/TXT）")
    truncated = len(text) > 20000
    message = (
        "格式与本系统一致，可直接导入为需求书，无需 AI 转换" if matched
        else "已提取文字，生成需求书时 AI 将按此内容转换为本系统格式"
    ) + ("；原文过长已截断保存" if truncated else "")
    return {
        "filename": filename,
        "size": len(data),
        "chars": len(text),
        "truncated": truncated,
        "text": text[:20000],
        "format_matched": matched,
        "max_mb": MAX_FILE_MB,
        "message": message,
    }


@router.get("/{order_id}/requirement")
def get_requirement(
    order_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    if not order.requirement:
        raise HTTPException(status_code=404, detail="尚未生成需求书")
    try:
        document = json.loads(order.requirement)
    except (ValueError, TypeError):
        raise HTTPException(status_code=500, detail="需求书数据损坏")
    return {
        "source": order.requirement_source,
        "updated_at": order.requirement_updated_at,
        "document": document,
    }


@router.post("/{order_id}/requirement/generate")
def generate_requirement(
    order_id: str,
    body: GenerateIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = get_order_or_404(db, order_id)
    # 代理（销售/同行）可为自己的订单生成需求书发给客户；写手/管理员按原权限
    ensure_access(order, user)
    rate_limit(request, "ai_docgen", f"{user.id}:{client_ip(request)}", limit=5, window_seconds=60)
    from ..services.ai_quota import ensure_ai_quota

    ensure_ai_quota(db, user.id)

    wants_ai = body.mode in ("ai", "auto")
    use_ai = wants_ai and ai_available(db)
    source = "template"
    document = None
    note = None

    # 直接应用模式：上传的需求书原文即需求书，不做任何修改（不调 AI、不套模板）。
    # 本系统九章 JSON 格式的文档仍走结构化导入（内容同样不变）；
    # 其余格式（Word / TXT / Markdown）一律按原文保存（mode=raw）。
    if wants_ai and order.source_requirement and order.source_apply_mode == "direct":
        try:
            parsed = json.loads(order.source_requirement)
        except (ValueError, TypeError):
            parsed = None
        if parsed is not None and is_our_doc(parsed):
            document = docgen.normalize_doc(parsed, order.title, order.tech_stack)
            note = "已直接采用上传的需求书（系统格式，原样导入，未做修改）"
        else:
            # 不解析成九章：解析会把没有对应章节的段落（如售后服务、验收标准）归进「功能需求」，
            # 与「原文直接应用、系统不做任何修改」不符
            document = docgen.build_raw_doc(order.title, order.source_requirement)
            note = "已直接采用上传的需求书原文（未做任何修改）"
        source = "manual"

    # 参考模式（默认）：客户上传的需求书若本就是本系统九章 JSON：直接导入，跳过 AI
    elif wants_ai and order.source_requirement:
        try:
            parsed = json.loads(order.source_requirement)
        except (ValueError, TypeError):
            parsed = None
        if parsed is not None and is_our_doc(parsed):
            document = docgen.normalize_doc(parsed, order.title, order.tech_stack)
            source = "manual"
            note = "原始需求书格式匹配，已直接导入"

    if document is None and use_ai:
        try:
            document = generate_by_ai(
                db, order.title, order.tech_stack, order_id=order.id, user_id=user.id,
                source_text=order.source_requirement, notes=order.requirement_notes,
            )
            source = "ai"
        except AIGenerationError as exc:
            if body.mode == "ai":
                raise HTTPException(status_code=502, detail=f"AI 生成失败: {exc}")
            note = f"AI 生成失败已回退模板: {exc}"
    if document is None:
        document = docgen.build_template_doc(order.title, order.tech_stack)
        if wants_ai and not use_ai and (order.source_requirement or order.requirement_notes):
            note = note or "AI 未配置：模板生成未使用原始需求资料"

    # 技术栈留空且由 AI 生成：从生成结果回写简短技术栈标签，后续列表/筛选可用
    if source == "ai" and not (order.tech_stack or "").strip():
        label = docgen.tech_label_from_doc(document)
        if label:
            order.tech_stack = label

    snapshot_requirement(db, order, user, remark="重新生成前")
    order.requirement = json.dumps(document, ensure_ascii=False)
    order.requirement_source = source
    order.requirement_updated_at = datetime.now()
    log_op(
        db, "requirement_generate", request=request, user=user,
        entity_type="order", entity_id=order.id,
        detail={"source": source, "mode": body.mode, **({"note": note} if note else {})},
    )
    from ..services.notify_svc import notify_requirement_updated
    notify_requirement_updated(db, order, user.id, "生成" if source != "manual" else "更新")
    db.commit()
    return {"source": source, "note": note, "document": document}


@router.put("/{order_id}/requirement")
def save_requirement(
    order_id: str,
    body: RequirementSaveIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    document = docgen.normalize_doc(body.document, order.title, order.tech_stack)
    snapshot_requirement(db, order, user, remark="编辑保存前")
    order.requirement = json.dumps(document, ensure_ascii=False)
    order.requirement_source = "manual"
    order.requirement_updated_at = datetime.now()
    log_op(db, "requirement_update", request=request, user=user, entity_type="order", entity_id=order.id)
    from ..services.notify_svc import notify_requirement_updated
    notify_requirement_updated(db, order, user.id, "更新")
    db.commit()
    return {"document": document}


@router.post("/{order_id}/requirement/ai-revise")
def ai_revise_requirement(
    order_id: str,
    body: RequirementReviseIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按修改建议让 AI 修订需求书：不落库，返回修订稿；用户确认后走既有保存接口（含版本快照）。"""
    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    rate_limit(request, "ai_docgen", f"{user.id}:{client_ip(request)}", limit=5, window_seconds=60)
    from ..services.ai_quota import ensure_ai_quota

    ensure_ai_quota(db, user.id)

    if not ai_available(db):
        raise HTTPException(status_code=503, detail="AI 未配置，无法按建议修改（可在系统设置页配置 DeepSeek）")
    try:
        document = revise_by_ai(
            db, body.document, body.instruction, order.title, order.tech_stack,
            order_id=order.id, user_id=user.id,
        )
    except AIGenerationError as exc:
        # 失败的调用若已产生 token 消耗，用量记账仍需保留
        db.commit()
        raise HTTPException(status_code=502, detail=f"AI 修改失败: {exc}")
    db.commit()  # 提交 AI 用量记账
    log_op(
        db, "requirement_ai_revise", request=request, user=user,
        entity_type="order", entity_id=order.id,
        detail={"instruction": body.instruction[:200]},
    )
    db.commit()
    return {"document": document}


# ---- 需求书历史版本 ----

@router.get("/{order_id}/requirement/versions")
def list_requirement_versions(
    order_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    from ..models import RequirementVersion

    rows = (
        db.query(RequirementVersion)
        .filter(RequirementVersion.order_id == order.id)
        .order_by(RequirementVersion.created_at.desc(), RequirementVersion.id.desc())
        .limit(50)
        .all()
    )
    return {"versions": [
        {"id": v.id, "source": v.source, "username": v.username,
         "remark": v.remark, "created_at": v.created_at}
        for v in rows
    ]}


@router.post("/{order_id}/requirement/versions/{version_id}/restore")
def restore_requirement_version(
    order_id: str,
    version_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    from ..models import RequirementVersion

    version = (
        db.query(RequirementVersion)
        .filter(RequirementVersion.id == version_id, RequirementVersion.order_id == order.id)
        .first()
    )
    if not version or not version.document:
        raise HTTPException(status_code=404, detail="版本不存在")
    snapshot_requirement(db, order, user, remark="回滚前")
    order.requirement = version.document
    order.requirement_source = version.source or "manual"
    order.requirement_updated_at = datetime.now()
    log_op(db, "requirement_restore", request=request, user=user,
           entity_type="order", entity_id=order.id, detail={"version_id": version_id})
    db.commit()
    try:
        document = json.loads(order.requirement)
    except (ValueError, TypeError):
        document = None
    return {"document": document}


def _docx_response(buf, order: Order):
    # 文件名：单号-题目-需求书.docx，剔除 Windows 文件名非法字符
    illegal = '\\/:*?"<>|\r\n\t'
    safe_title = "".join(ch for ch in (order.title or "") if ch not in illegal).strip()
    safe_title = safe_title[:80] or "未命名"
    filename = f"{order.id}-{safe_title}-需求书.docx"
    quoted = quote(filename)
    return StreamingResponse(
        buf,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted}",
            "Content-Length": str(buf.getbuffer().nbytes),
        },
    )


@router.get("/{order_id}/requirement/docx")
def download_requirement(
    order_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = get_order_or_404(db, order_id)
    ensure_access(order, user)
    if not order.requirement:
        raise HTTPException(status_code=404, detail="尚未生成需求书，无法下载")
    try:
        document = json.loads(order.requirement)
    except (ValueError, TypeError):
        raise HTTPException(status_code=500, detail="需求书数据损坏")
    buf = docgen.render_docx(document, school=get_setting(db, "docx_school"))
    log_op(db, "requirement_download", request=request, user=user, entity_type="order", entity_id=order.id)
    db.commit()
    return _docx_response(buf, order)
