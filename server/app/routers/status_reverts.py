"""写手状态撤回审批：申请由订单详情内联提交，管理员在通知/详情中审批。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import Order, StatusRevertRequest, User
from ..services.notify_svc import notify_status_changed, push
from ..services.oplog import log_op
from ..schemas import StatusRevertReviewIn
from ..services.order_svc import STATUS_CN, order_query, order_view, revert_view, set_order_status

router = APIRouter(prefix="/api/status-reverts", tags=["status-reverts"])


@router.get("")
def list_status_reverts(
    status: str | None = Query(default=None, pattern=r"^(pending|approved|rejected|cancelled)$"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员审批列表（通知点进订单详情即可审批，此接口用于审计/测试）。"""
    q = db.query(StatusRevertRequest).options(selectinload(StatusRevertRequest.order))
    if status:
        q = q.filter(StatusRevertRequest.status == status)
    rows = q.order_by(StatusRevertRequest.created_at.desc()).limit(200).all()
    return {
        "items": [
            {**revert_view(r), "order_title": r.order.title if r.order else ""}
            for r in rows
        ],
        "pending": db.query(StatusRevertRequest).filter(StatusRevertRequest.status == "pending").count(),
    }


@router.post("/{rid}/review")
def review_status_revert(
    rid: int,
    body: StatusRevertReviewIn,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员审批：通过则自动回退订单状态；订单状态已变化则审批自动失效。"""
    row = (
        db.query(StatusRevertRequest)
        .filter(StatusRevertRequest.id == rid)
        .with_for_update()
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="撤回申请不存在")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail=f"该申请已{revert_view(row)['status_cn']}，不能重复审批")

    order = (
        order_query(db).filter(Order.id == row.order_id).with_for_update().first()
    )
    now = datetime.now()
    if not order or order.status != row.from_status:
        reason = "订单已删除" if not order else f"订单状态已变为「{STATUS_CN.get(order.status, order.status)}」"
        row.status = "rejected"
        row.reviewed_by = user.id
        row.reviewer_name = user.display_name or user.username
        row.review_note = f"自动失效：{reason}"
        row.reviewed_at = now
        row.updated_at = now
        log_op(
            db, "status_revert_auto_reject", request=request, user=user,
            entity_type="order", entity_id=row.order_id,
            detail={"request_id": row.id, "reason": reason},
        )
        db.commit()
        raise HTTPException(status_code=409, detail=f"撤回申请已失效：{reason}")

    if body.action == "approve":
        try:
            set_order_status(order, row.to_status, allow_any=True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        row.status = "approved"
        row.review_note = (body.note or "").strip() or None
        row.reviewed_by = user.id
        row.reviewer_name = user.display_name or user.username
        row.reviewed_at = now
        row.updated_at = now
        log_op(
            db, "status_revert_approve", request=request, user=user,
            entity_type="order", entity_id=order.id,
            detail={
                "request_id": row.id, "before": row.from_status, "after": row.to_status,
                "applicant": row.username, "note": row.review_note,
            },
        )
        notify_status_changed(db, order, user.id, row.to_status)
        push(
            db, [row.requested_by],
            f"撤回申请已通过：订单 {order.id}",
            body=(
                f"{row.reviewer_name} 已同意将状态从「{STATUS_CN.get(row.from_status, row.from_status)}」"
                f"回退为「{STATUS_CN.get(row.to_status, row.to_status)}」"
                + (f"：{row.review_note}" if row.review_note else "")
            ),
            order_id=order.id,
        )
        db.commit()
        db.refresh(row)
        db.refresh(order)
        background.add_task(
            _notify_webhook, order.id, order.title, row.from_status, row.to_status
        )
        return {"request": revert_view(row), "order": order_view(order, user.role)}

    row.status = "rejected"
    row.review_note = (body.note or "").strip() or None
    row.reviewed_by = user.id
    row.reviewer_name = user.display_name or user.username
    row.reviewed_at = now
    row.updated_at = now
    log_op(
        db, "status_revert_reject", request=request, user=user,
        entity_type="order", entity_id=order.id,
        detail={"request_id": row.id, "applicant": row.username, "note": row.review_note},
    )
    push(
        db, [row.requested_by],
        f"撤回申请被驳回：订单 {order.id}",
        body=(row.review_note or "管理员未通过本次撤回申请，订单状态保持不变"),
        order_id=order.id,
    )
    db.commit()
    db.refresh(row)
    return {"request": revert_view(row), "order": order_view(order, user.role)}


@router.post("/{rid}/cancel")
def cancel_status_revert(
    rid: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """申请人主动撤回自己的审批请求。"""
    row = (
        db.query(StatusRevertRequest)
        .filter(StatusRevertRequest.id == rid)
        .with_for_update()
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="撤回申请不存在")
    if row.requested_by != user.id:
        raise HTTPException(status_code=403, detail="只有申请人可撤回该申请")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="该申请已处理，不能撤回")
    now = datetime.now()
    row.status = "cancelled"
    row.updated_at = now
    log_op(
        db, "status_revert_cancel", request=request, user=user,
        entity_type="order", entity_id=row.order_id,
        detail={"request_id": row.id},
    )
    db.commit()
    db.refresh(row)
    return {"request": revert_view(row)}


def _notify_webhook(order_id: str, title: str, old: str, new: str) -> None:
    from ..services.webhook import notify_status_changed as notify_webhook

    notify_webhook(order_id, title, old, new)
