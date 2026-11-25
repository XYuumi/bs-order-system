"""论文进度：项目类型含论文的订单按 任务书→开题报告→初稿→终稿 四阶段留档。

规则：
- 每次提交（含修改）都追加一条 order_paper_doc 记录，历史版本永不可删（append-only 留档）；
- 初稿第 1 版为首次提交，其后每一版计一次「修改」；
- 提交终稿前，初稿修改次数必须达到下限（默认 5 次，设置项 paper_draft_min_revisions）；
- 上传仅限管理员/写手；代理与其余有订单访问权的人只读（可下载留档文件发给客户）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_current_user, require_staff
from ..models import Order, OrderPaperDoc, User
from ..ratelimit import client_ip, rate_limit
from ..services.files_svc import save_upload
from ..services.notify_svc import push
from ..services.oplog import log_op
from ..services.order_svc import can_access, has_paper_workflow
from ..services.settings_svc import get_setting

router = APIRouter(prefix="/api/orders/{order_id}/paper", tags=["paper"])

# 四类论文交付物（展示顺序即流程顺序）
PAPER_DOC_TYPES = ("task_book", "proposal", "draft", "final")
PAPER_DOC_CN = {
    "task_book": "任务书",
    "proposal": "开题报告",
    "draft": "论文初稿",
    "final": "论文终稿",
}


def _get_order(db: Session, order_id: str) -> Order:
    order = db.query(Order).filter(Order.id == order_id, Order.is_deleted == False).first()  # noqa: E712
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order


def min_draft_revisions(db: Session) -> int:
    """初稿最少修改次数（默认 5；可在设置表调整，0-50 之间）。"""
    raw = get_setting(db, "paper_draft_min_revisions", "5") or "5"
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = 5
    return max(0, min(value, 50))


def _doc_view(d: OrderPaperDoc) -> dict:
    f = d.file
    return {
        "id": d.id,
        "doc_type": d.doc_type,
        "doc_type_cn": PAPER_DOC_CN.get(d.doc_type, d.doc_type),
        "round": d.round,
        "note": d.note,
        "username": d.username,
        "created_at": d.created_at,
        "file": (
            {"id": f.id, "name": f.original_name, "size": f.size}
            if f and not f.is_deleted else None
        ),
    }


def _progress(db: Session, order: Order) -> dict:
    rows = (
        db.query(OrderPaperDoc)
        .filter(OrderPaperDoc.order_id == order.id)
        .options(selectinload(OrderPaperDoc.file))
        .order_by(OrderPaperDoc.doc_type, OrderPaperDoc.round.desc(), OrderPaperDoc.id.desc())
        .all()
    )
    min_rev = min_draft_revisions(db)
    by_type: dict[str, list[OrderPaperDoc]] = {}
    for row in rows:
        by_type.setdefault(row.doc_type, []).append(row)
    draft_revisions = max(0, len(by_type.get("draft", [])) - 1)
    docs = []
    for doc_type in PAPER_DOC_TYPES:
        items = by_type.get(doc_type, [])
        latest = items[0] if items else None
        count = len(items)
        # 第 1 版为首次提交，其后每版计一次修改（留档链）
        revisions = max(0, count - 1)
        docs.append({
            "doc_type": doc_type,
            "label": PAPER_DOC_CN[doc_type],
            "count": count,
            "revisions": revisions,
            "latest": _doc_view(latest) if latest else None,
            # 仅初稿展示修改进度条；终稿能否提交由初稿修改次数决定
            **({"revision_progress": min(100, round(draft_revisions / min_rev * 100)) if min_rev else 100}
               if doc_type == "draft" else {}),
            **({"ready": draft_revisions >= min_rev} if doc_type == "final" else {}),
        })
    return {
        "project_type": order.project_type,
        "enabled": has_paper_workflow(order),
        "min_revisions": min_rev,
        "docs": docs,
        "draft_revisions": draft_revisions,
        "final_submitted": bool(by_type.get("final")),
        "all_done": all(by_type.get(t) for t in PAPER_DOC_TYPES),
    }


@router.get("")
def paper_progress(
    order_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = _get_order(db, order_id)
    if not can_access(order, user):
        raise HTTPException(status_code=403, detail="无权访问该订单")
    data = _progress(db, order)
    data["order_id"] = order.id
    return data


@router.get("/docs")
def list_paper_docs(
    order_id: str,
    doc_type: str | None = Query(default=None, pattern=r"^(task_book|proposal|draft|final)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = _get_order(db, order_id)
    if not can_access(order, user):
        raise HTTPException(status_code=403, detail="无权访问该订单")
    q = (
        db.query(OrderPaperDoc)
        .filter(OrderPaperDoc.order_id == order.id)
        .options(selectinload(OrderPaperDoc.file))
    )
    if doc_type:
        q = q.filter(OrderPaperDoc.doc_type == doc_type)
    rows = q.order_by(OrderPaperDoc.round.desc(), OrderPaperDoc.id.desc()).limit(200).all()
    return {"docs": [_doc_view(r) for r in rows]}


@router.post("/docs")
def upload_paper_doc(
    order_id: str,
    request: Request,
    doc_type: str = Form(pattern=r"^(task_book|proposal|draft|final)$"),
    note: str | None = Form(default=None),
    file: UploadFile = File(...),
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    rate_limit(request, "paper_upload", f"{user.id}:{client_ip(request)}", limit=20, window_seconds=60)
    if doc_type not in PAPER_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"非法的论文文档类型: {doc_type}")
    # 行锁串行化同一订单的留档写入：并发上传时轮次号不会重复
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.is_deleted == False)  # noqa: E712
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if not has_paper_workflow(order):
        raise HTTPException(status_code=400, detail="该订单不含论文交付（项目类型为纯程序设计），无需上传论文文档")

    existing = db.query(OrderPaperDoc).filter(
        OrderPaperDoc.order_id == order.id, OrderPaperDoc.doc_type == doc_type
    ).count()

    # 终稿门槛：初稿至少完成 min_draft_revisions 次修改（每次修改都已留档）
    min_rev = min_draft_revisions(db)
    if doc_type == "final":
        draft_count = db.query(OrderPaperDoc).filter(
            OrderPaperDoc.order_id == order.id, OrderPaperDoc.doc_type == "draft"
        ).count()
        revisions = max(0, draft_count - 1)
        if revisions < min_rev:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"初稿至少需修改 {min_rev} 次才能提交终稿（当前已修改 {revisions} 次，"
                    f"还差 {min_rev - revisions} 次）；每次修改请在「论文初稿」中重新上传留档"
                ),
            )

    note_clean = (note or "").strip()[:500] or None
    try:
        # paper 不在一单一份的分类里，replaced 恒为空：每次上传都追加留档
        record, _replaced = save_upload(
            db,
            order=order,
            category="paper",
            original_name=file.filename or "paper.docx",
            stream=file.file,
            declared_mime=file.content_type,
            remark=f"{PAPER_DOC_CN[doc_type]} 第 {existing + 1} 版",
            uploader=user,
        )
    except HTTPException:
        db.rollback()
        raise

    doc = OrderPaperDoc(
        order_id=order.id,
        doc_type=doc_type,
        round=existing + 1,
        file_id=record.id,
        note=note_clean,
        created_by=user.id,
        username=user.display_name or user.username,
    )
    db.add(doc)
    log_op(
        db, "paper_doc_upload", request=request, user=user,
        entity_type="order", entity_id=order.id,
        detail={
            "doc_type": doc_type, "round": doc.round,
            "file": record.original_name, "size": record.size,
            **({"note": note_clean} if note_clean else {}),
        },
    )
    # 通知代理与负责人（操作者除外）：论文阶段有新版本
    targets = [order.agent_user_id, order.assignee_user_id]
    push(
        db, [t for t in targets if t and t != user.id],
        f"订单 {order.id} 论文{PAPER_DOC_CN[doc_type]}更新（第 {doc.round} 版）",
        body=record.original_name,
        order_id=order.id,
    )
    db.commit()
    data = _progress(db, order)
    data["order_id"] = order.id
    data["uploaded"] = _doc_view(doc)
    return data
