from __future__ import annotations

import json
import math
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import (
    ALLOWED_EXTS, CHUNK_MAX_MB, CHUNK_MAX_PARTS, CHUNK_TTL_HOURS,
    MAX_UPLOAD_MB, UPLOAD_DIR,
)
from ..database import get_db
from ..deps import get_current_user, require_admin, require_staff
from ..models import ChunkUpload, OperationLog, Order, OrderFile, User
from ..ratelimit import client_ip, rate_limit
from ..services.deliver import DELIVER_CATEGORIES, make_token, parse_token, token_order_id
from ..services.files_svc import download_response, file_stream, remove_stored_files, save_upload, thumb_path_for
from ..services.notify_svc import push
from ..services.oplog import log_op
from ..services.order_svc import can_access, can_download, can_manage_files, file_view
from ..services.settings_svc import get_settings_map

router = APIRouter(prefix="/api", tags=["files"])


def _get_order(db: Session, order_id: str) -> Order:
    order = db.get(Order, order_id)
    if not order or order.is_deleted:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order


@router.post("/orders/{order_id}/files")
def upload_file(
    order_id: str,
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(...),
    remark: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = _get_order(db, order_id)
    _check_upload_permission(order, user, category)

    record, replaced = save_upload(
        db,
        order=order,
        category=category,
        original_name=file.filename or "file",
        stream=file.file,
        declared_mime=file.content_type,
        remark=remark,
        uploader=user,
    )
    _log_upload(db, request, user, order, record, replaced)
    db.commit()
    # 替换已提交生效，这时才能删旧文件：上传中途失败时旧文件原样保留
    remove_stored_files(db, replaced)
    from ..services.notify_svc import notify_file_uploaded
    notify_file_uploaded(db, order, user.id, record.original_name, category,
                         replaced=[f.original_name for f in replaced])
    db.commit()
    return _upload_response(record, replaced)


def _log_upload(db: Session, request: Request, user: User, order: Order, record: OrderFile,
                replaced: list[OrderFile], *, chunked: bool = False) -> None:
    """上传写操作日志；发生替换时记下被替换的文件名与 ID（页面显示、人工找回都用得上）。调用方负责 commit。"""
    names = [f.original_name for f in replaced]
    detail = {"file": record.original_name, "category": record.category, "size": record.size}
    if chunked:
        detail["chunked"] = True
    if names:
        detail.update(replaced=names, replaced_ids=[f.id for f in replaced])
    log_op(db, "file_upload", request=request, user=user, entity_type="order", entity_id=order.id,
           detail=detail)


def _upload_response(record: OrderFile, replaced: list[OrderFile]) -> dict:
    return {"file": file_view(record), "replaced": [file_view(f) for f in replaced]}


def _check_upload_permission(order: Order, user: User, category: str) -> None:
    # 论文交付物必须走「论文进度」接口上传，才能形成 任务书/开题/初稿/终稿 的留档链
    if category == "paper":
        raise HTTPException(status_code=400, detail="论文文档请在订单详情「论文进度」中上传，以保证版本留档")
    if user.role == "agent":
        if order.agent_user_id != user.id:
            raise HTTPException(status_code=403, detail="无权向该订单上传文件")
        if category != "other":
            raise HTTPException(status_code=403, detail="代理只能上传「其他附件」类文件")


# ==================== 分片上传（大文件断点续传） ====================

CHUNK_SIZE = 5 * 1024 * 1024


def _chunk_root(upload_id: str) -> Path:
    if not (len(upload_id) == 32 and all(c in "0123456789abcdef" for c in upload_id)):
        raise HTTPException(status_code=400, detail="非法的上传会话")
    root = UPLOAD_DIR / ".chunks" / upload_id
    resolved = root.resolve()
    if ".." in str(root) or not str(resolved).startswith(str(UPLOAD_DIR.resolve())):
        raise HTTPException(status_code=400, detail="非法的上传会话")
    return resolved


class ChunkUploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=2, max_length=10)
    size: int = Field(gt=0)
    remark: str | None = Field(default=None, max_length=200)


def _session(db: Session, order_id: str, upload_id: str, user: User, *, lock: bool = False) -> ChunkUpload:
    q = db.query(ChunkUpload).filter(ChunkUpload.id == upload_id, ChunkUpload.order_id == order_id)
    if lock:
        q = q.with_for_update()
    row = q.first()
    if not row:
        raise HTTPException(status_code=404, detail="上传会话不存在或已过期")
    if row.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问该上传会话")
    if row.expires_at and row.expires_at < datetime.now():
        raise HTTPException(status_code=410, detail="上传会话已过期，请重新开始")
    return row


def _received(row: ChunkUpload) -> list[int]:
    try:
        values = json.loads(row.received or "[]")
        return sorted({int(v) for v in values if isinstance(v, int) or str(v).isdigit()})
    except (ValueError, TypeError):
        return []


@router.post("/orders/{order_id}/chunk-uploads")
def create_chunk_upload(
    order_id: str,
    body: ChunkUploadIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rate_limit(request, "chunk_create", f"{user.id}:{client_ip(request)}", limit=30, window_seconds=60)
    order = _get_order(db, order_id)
    _check_upload_permission(order, user, body.category)
    ext = Path(body.filename).suffix.lower()
    allowed = ALLOWED_EXTS.get(body.category)
    if allowed is None or ext not in allowed:
        raise HTTPException(status_code=400, detail=f"该分类不允许上传 {ext or '(无扩展名)'} 文件")
    limit_mb = min(MAX_UPLOAD_MB.get(body.category, 1024), CHUNK_MAX_MB)
    if body.size > limit_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过大小限制 {limit_mb}MB")
    total_chunks = math.ceil(body.size / CHUNK_SIZE)
    if total_chunks > CHUNK_MAX_PARTS:
        raise HTTPException(status_code=413, detail=f"分片数超过上限 {CHUNK_MAX_PARTS}")

    upload_id = uuid.uuid4().hex
    root = _chunk_root(upload_id)
    root.mkdir(parents=True, exist_ok=True)
    row = ChunkUpload(
        id=upload_id,
        order_id=order.id,
        user_id=user.id,
        original_name=Path(body.filename).name[:255],
        category=body.category,
        size=body.size,
        chunk_size=CHUNK_SIZE,
        total_chunks=total_chunks,
        received="[]",
        remark=(body.remark or "").strip()[:255] or None,
        expires_at=datetime.now() + timedelta(hours=max(CHUNK_TTL_HOURS, 1)),
    )
    db.add(row)
    db.commit()
    log_op(db, "chunk_create", request=request, user=user, entity_type="order", entity_id=order.id,
           detail={"upload_id": upload_id, "size": body.size, "category": body.category})
    db.commit()
    return {"upload_id": upload_id, "chunk_size": CHUNK_SIZE, "total_chunks": total_chunks}


@router.get("/orders/{order_id}/chunk-uploads/{upload_id}")
def chunk_upload_status(
    order_id: str,
    upload_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _session(db, order_id, upload_id, user)
    return {
        "filename": row.original_name,
        "size": row.size,
        "received": _received(row),
        "total_chunks": row.total_chunks,
        "expires_at": row.expires_at,
    }


def _write_chunk(root: Path, index: int, data: bytes, size: int) -> int:
    target = root / f"{index}.part"
    current = sum(p.stat().st_size for p in root.glob("*.part") if p.is_file())
    existing = target.stat().st_size if target.exists() else 0
    if current - existing + len(data) > size:
        raise HTTPException(status_code=413, detail="分片总大小超过声明大小")
    target.write_bytes(data)
    return len(data)


@router.put("/orders/{order_id}/chunk-uploads/{upload_id}/{index}")
async def upload_chunk(
    order_id: str,
    upload_id: str,
    index: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rate_limit(request, "chunk_put", f"{user.id}:{client_ip(request)}", limit=120, window_seconds=60)
    order = _get_order(db, order_id)
    # 行锁串行化同一会话的 received 读-改-写：并行传分片时防止后提交者覆盖前者的序号
    row = _session(db, order.id, upload_id, user, lock=True)
    _check_upload_permission(order, user, row.category)
    if index < 0 or index >= row.total_chunks:
        raise HTTPException(status_code=400, detail="非法分片序号")
    data = await request.body()
    if not data or len(data) > CHUNK_SIZE + 1024 * 1024:
        raise HTTPException(status_code=400, detail="分片大小非法")
    root = _chunk_root(upload_id)
    await run_in_threadpool(_write_chunk, root, index, data, row.size)
    received = sorted(set(_received(row)) | {index})
    row.received = json.dumps(received)
    db.commit()
    return {"received_chunks": len(received), "total_chunks": row.total_chunks}


@router.post("/orders/{order_id}/chunk-uploads/{upload_id}/finish")
def finish_chunk_upload(
    order_id: str,
    upload_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = _get_order(db, order_id)
    row = _session(db, order.id, upload_id, user, lock=True)
    _check_upload_permission(order, user, row.category)
    root = _chunk_root(upload_id)
    received = set(_received(row))
    missing = [i for i in range(row.total_chunks) if i not in received]
    if missing:
        raise HTTPException(status_code=400, detail=f"分片不完整，缺少 {len(missing)} 个分片")
    parts = sorted((int(p.stem), p) for p in root.glob("*.part") if p.stem.isdigit())
    total = sum(p.stat().st_size for _, p in parts)
    if total != row.size:
        raise HTTPException(status_code=400, detail=f"分片大小不符：已收 {total} / 应收 {row.size} 字节")

    merged_tmp = Path(root) / f"merged-{uuid.uuid4().hex}.tmp"
    try:
        with merged_tmp.open("wb") as out:
            for _, part in parts:
                with part.open("rb") as src:
                    shutil.copyfileobj(src, out, length=1024 * 1024)
        with merged_tmp.open("rb") as stream:
            record, replaced = save_upload(
                db,
                order=order,
                category=row.category,
                original_name=row.original_name,
                stream=stream,
                declared_mime=None,
                remark=row.remark,
                uploader=user,
            )
        _log_upload(db, request, user, order, record, replaced, chunked=True)
        from ..services.notify_svc import notify_file_uploaded
        notify_file_uploaded(db, order, user.id, record.original_name, row.category,
                             replaced=[f.original_name for f in replaced])
        db.delete(row)
        db.commit()
        shutil.rmtree(root, ignore_errors=True)
        remove_stored_files(db, replaced)
        return _upload_response(record, replaced)
    finally:
        merged_tmp.unlink(missing_ok=True)


@router.delete("/files/{file_id}")
def delete_file(
    file_id: int,
    request: Request,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    from ..deps import require_password_confirm

    require_password_confirm(request, user)
    record = db.get(OrderFile, file_id)
    if not record or record.is_deleted:
        raise HTTPException(status_code=404, detail="文件不存在")
    order = db.get(Order, record.order_id)
    if not order or order.is_deleted:
        raise HTTPException(status_code=404, detail="订单不存在")
    if not can_manage_files(order, user):
        raise HTTPException(status_code=403, detail="无权删除该订单的文件（仅管理员或该单负责写手）")
    # 论文留档文件不可删：任务书/开题/初稿/终稿的每次版本都要永久留档
    from ..models import OrderPaperDoc

    if db.query(OrderPaperDoc.id).filter(OrderPaperDoc.file_id == record.id).first() is not None:
        raise HTTPException(status_code=400, detail="该文件是论文留档（任务书/开题报告/初稿/终稿），为保证修改记录完整不可删除")
    record.is_deleted = True
    log_op(db, "file_delete", request=request, user=user, entity_type="order", entity_id=record.order_id,
           detail={"file": record.original_name, "category": record.category})
    db.commit()
    # 删除已提交生效，磁盘上的文件（含视频缩略图）一并清掉
    remove_stored_files(db, [record])
    return {"ok": True}


@router.get("/files/{file_id}/download")
def download_file(
    file_id: int,
    request: Request,
    download: str | None = Query(default=None, max_length=8),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # ?download=1：强制保存文件（视频默认 inline 在线播放，下载按钮需要附件头）
    force = (download or "").strip().lower() in ("1", "true", "yes")
    return download_response(db, file_id=file_id, request=request, user=user,
                             action="file_download", force_download=force)


@router.get("/files/{file_id}/thumb")
def file_thumb(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """视频缩略图（登录且有权访问该订单）。"""
    from fastapi.responses import FileResponse

    record = db.get(OrderFile, file_id)
    if not record or record.is_deleted or record.category != "video":
        raise HTTPException(status_code=404, detail="缩略图不存在")
    order = _get_order(db, record.order_id)
    if not can_download(order, user):
        raise HTTPException(status_code=403, detail="无权访问该文件")
    thumb_path = thumb_path_for(record)
    if not thumb_path:
        raise HTTPException(status_code=404, detail="缩略图不存在")
    return FileResponse(str(thumb_path), media_type="image/jpeg")


# ==================== 客户交付分享（免登录） ====================

def _deliver_expire_days(db: Session) -> int:
    raw = get_settings_map(db, ["deliver_expire_days"]).get("deliver_expire_days", "0")
    try:
        value = float(raw)
        if not math.isfinite(value):
            return 0
        return max(0, min(int(value), 3650))
    except (TypeError, ValueError):
        return 0


@router.get("/orders/{order_id}/deliver-link")
def get_deliver_link(
    order_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """生成本订单的客户交付 token（管理员/写手/该单代理可取），发给客户免登录下载。"""
    order = _get_order(db, order_id)
    if not can_download(order, user):
        raise HTTPException(status_code=403, detail="无权获取该订单的交付链接")
    days = _deliver_expire_days(db)
    return {
        "token": make_token(order.id, order.deliver_token_version),
        "categories": list(DELIVER_CATEGORIES),
        "expire_days": days,
        "version": order.deliver_token_version,
    }


@router.post("/orders/{order_id}/deliver-link/revoke")
def revoke_deliver_link(
    order_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """撤销该订单的全部历史交付链接（版本递增，旧链接立即失效）。"""
    order = _get_order(db, order_id)
    order.deliver_token_version = int(order.deliver_token_version or 0) + 1
    log_op(db, "deliver_link_revoke", request=request, user=admin, entity_type="order", entity_id=order.id,
           detail={"version": order.deliver_token_version})
    db.commit()
    return {"ok": True, "version": order.deliver_token_version}


@router.get("/orders/{order_id}/deliver-stats")
def deliver_stats(
    order_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """交付链接访问统计：客户浏览/下载次数（管理员/写手/该单代理）。"""
    from sqlalchemy import func as sa_func

    order = _get_order(db, order_id)
    if not can_access(order, user):
        raise HTTPException(status_code=403, detail="无权查看")
    rows = (
        db.query(OperationLog.action, sa_func.count(OperationLog.id))
        .filter(OperationLog.entity_type == "order", OperationLog.entity_id == order.id,
                OperationLog.action.in_(["deliver_view", "deliver_download"]))
        .group_by(OperationLog.action)
        .all()
    )
    counts = dict(rows)
    return {"views": counts.get("deliver_view", 0), "downloads": counts.get("deliver_download", 0)}


def _deliver_order(db: Session, token: str) -> Order | None:
    """先提取订单号加载版本，再按当前版本验签；撤销后的旧 token 立即失效。"""
    oid = token_order_id(token)
    if not oid:
        return None
    order = db.get(Order, oid)
    if not order or order.is_deleted:
        return None
    if not parse_token(token, expire_days=_deliver_expire_days(db), version=order.deliver_token_version):
        return None
    return order


@router.get("/deliver/{token}")
def deliver_view(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """客户交付页数据：仅暴露 订单题目 + 程序包/演示视频 文件清单。"""
    rate_limit(request, "deliver", client_ip(request), 30, 60)
    order = _deliver_order(db, token)
    if not order:
        raise HTTPException(status_code=404, detail="交付链接不存在或已失效")
    files = (
        db.query(OrderFile)
        .filter(
            OrderFile.order_id == order.id,
            OrderFile.is_deleted == False,  # noqa: E712
            OrderFile.category.in_(DELIVER_CATEGORIES),
        )
        .order_by(OrderFile.category, OrderFile.created_at.desc())
        .all()
    )
    updated = max((f.created_at for f in files), default=None) or order.updated_at
    site_name = get_settings_map(db, ["site_name"]).get("site_name", "")
    log_op(db, "deliver_view", request=request, user=None, entity_type="order", entity_id=order.id,
           detail={"share": True})
    db.commit()
    return {
        "site_name": site_name or "毕设接单",
        "order": {"id": order.id, "title": order.title, "deadline": order.deadline,
                  "accepted_at": order.customer_accepted_at},
        "updated_at": updated,
        "files": [
            {"id": f.id, "name": f.original_name, "size": f.size, "category": f.category,
             "created_at": f.created_at, "remark": f.remark}
            for f in files
        ],
    }


@router.post("/deliver/{token}/accept")
def deliver_accept(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """客户确认验收：留时间戳与 IP（一次性），代理与平台经通知实时得知。"""
    rate_limit(request, "deliver_accept", client_ip(request), 10, 60)
    order = _deliver_order(db, token)
    if not order:
        raise HTTPException(status_code=404, detail="交付链接不存在或已失效")

    now = datetime.now()
    ip = client_ip(request)
    updated = (
        db.query(Order)
        .filter(Order.id == order.id, Order.customer_accepted_at.is_(None))
        .update({"customer_accepted_at": now, "customer_accepted_ip": ip}, synchronize_session=False)
    )
    if not updated:
        db.refresh(order)
        return {"ok": True, "accepted_at": order.customer_accepted_at, "already": True}

    order.customer_accepted_at = now
    order.customer_accepted_ip = ip
    log_op(db, "customer_accept", request=request, user=None, entity_type="order", entity_id=order.id,
           detail={"ip": ip})
    targets = [uid for uid in (order.agent_user_id, order.created_by) if uid]
    push(db, targets, f"客户已验收订单 {order.id}", body=order.title, order_id=order.id)
    db.commit()
    return {"ok": True, "accepted_at": now, "already": False}


@router.post("/orders/{order_id}/accept-revoke")
def accept_revoke(
    order_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员撤销客户验收（需登录密码二次确认）。"""
    from ..deps import require_password_confirm

    require_password_confirm(request, admin)
    order = db.get(Order, order_id)
    if not order or order.is_deleted:
        raise HTTPException(status_code=404, detail="订单不存在")
    if not order.customer_accepted_at:
        raise HTTPException(status_code=400, detail="该订单尚未验收")
    order.customer_accepted_at = None
    order.customer_accepted_ip = None
    log_op(db, "customer_accept_revoke", request=request, user=admin, entity_type="order", entity_id=order.id)
    targets = [uid for uid in (order.agent_user_id, order.created_by) if uid and uid != admin.id]
    push(db, targets, f"订单 {order.id} 的客户验收已被管理员撤销", body=order.title, order_id=order.id)
    db.commit()
    return {"ok": True}


@router.get("/deliver/{token}/files/{file_id}/download")
def deliver_download(
    token: str,
    file_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """客户免登录下载：token 校验 + 文件必须属于该订单且在交付分类内。"""
    rate_limit(request, "deliver-dl", client_ip(request), 60, 60)
    order = _deliver_order(db, token)
    if not order:
        raise HTTPException(status_code=404, detail="交付链接不存在或已失效")
    file = db.get(OrderFile, file_id)
    if (
        not file or file.is_deleted
        or file.order_id != order.id
        or file.category not in DELIVER_CATEGORIES
    ):
        raise HTTPException(status_code=404, detail="文件不存在")
    log_op(db, "deliver_download", request=request, user=None, entity_type="order", entity_id=order.id,
           detail={"file": file.original_name, "category": file.category, "share": True})
    db.commit()
    force = ((request.query_params.get("download") or "").strip().lower() in ("1", "true", "yes"))
    return file_stream(file, request, force_attachment=force)


@router.get("/orders/{order_id}/receipt.pdf")
def order_receipt_pdf(
    order_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """交付验收单 PDF：订单信息、交付时间线、文件清单与防伪验证码（非 admin 不含真实价/倍率）。"""
    import tempfile
    from urllib.parse import quote

    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    from ..services.receipt_pdf import render_receipt_pdf

    order = _get_order(db, order_id)
    if not can_access(order, user):
        raise HTTPException(status_code=403, detail="无权导出该订单的验收单")

    files = (
        db.query(OrderFile)
        .filter(OrderFile.order_id == order.id, OrderFile.is_deleted.is_(False))
        .order_by(OrderFile.category, OrderFile.created_at.desc(), OrderFile.id.desc())
        .all()
    )
    site_name = get_settings_map(db, ["site_name"]).get("site_name", "") or "毕设接单"
    pdf = render_receipt_pdf(order, role=user.role, files=files, site_name=site_name)
    log_op(db, "order_receipt_pdf", request=request, user=user, entity_type="order", entity_id=order.id,
           detail={"files": len(files), "accepted": bool(order.customer_accepted_at)})
    db.commit()

    target = Path(tempfile.gettempdir()) / f"receipt-{uuid.uuid4().hex}.pdf"
    target.write_bytes(pdf)
    filename = f"验收单-{order.id}.pdf"
    return FileResponse(
        str(target),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        background=BackgroundTask(target.unlink, missing_ok=True),
    )
