"""文件落盘与鉴权下载（Web 与代理 API 共用），支持 Range 断点/拖动播放。

路径安全策略：
- 存储相对路径只由三段白名单成分组成：订单号(YYMMDD-NNN) / 分类(小写字母) / 32位hex UUID；
- 写盘通过 tempfile 句柄完成，最终文件名不含任何用户输入（扩展名只存数据库）；
- 任何落盘/读取路径都经 _guard_path：resolve 后禁止 ".." 且必须位于 UPLOAD_DIR 内；
- 重命名使用 os.replace 原子操作，避免半写文件被访问。
"""
from __future__ import annotations

import logging
import mimetypes
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..config import ALLOWED_EXTS, MAX_UPLOAD_MB, UPLOAD_DIR
from ..database import SessionLocal
from ..models import ChunkUpload, Order, OrderFile, User
from ..services.oplog import log_op
from ..services.order_svc import can_download

CHUNK_SIZE = 1024 * 1024
# 一单一份的交付物：再次上传即替换同分类旧文件（doc/other 仍可多份并存，paper 只追加留档）
SINGLE_SLOT_CATEGORIES = ("video", "package")
ORDER_ID_RE = re.compile(r"^(?:demo)?\d{6}-\d{3,}$")
CATEGORY_RE = re.compile(r"^[a-z]{2,10}$")
UUID_RE = re.compile(r"^[0-9a-f]{32}$")


def _guard_path(candidate: Path) -> Path:
    """规范化并校验路径：禁止 ..，必须限制在 UPLOAD_DIR 允许目录内。"""
    text = str(candidate)
    full = str(candidate.resolve())
    root = str(UPLOAD_DIR.resolve())
    if ".." in text or ".." in full:
        raise HTTPException(status_code=400, detail="非法的存储路径(含..)")
    if not full.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="非法的存储路径(越界)")
    return Path(full)


def _checked_parts(order_id: str, category: str) -> tuple[str, str]:
    if not ORDER_ID_RE.match(order_id or ""):
        raise HTTPException(status_code=400, detail="非法的订单号")
    if not CATEGORY_RE.match(category or ""):
        raise HTTPException(status_code=400, detail="非法的附件分类")
    return order_id, category


def _make_video_thumb(order_id: str, stored_uuid: str, video_path: Path) -> None:
    """为视频生成 320px 宽首帧缩略图（ffmpeg 不可用或失败时静默跳过）。"""
    import shutil
    import subprocess

    if shutil.which("ffmpeg") is None:
        return
    thumb_dir = _guard_path(UPLOAD_DIR.joinpath(order_id, "thumb"))
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumb_dir / (stored_uuid + ".jpg")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", str(video_path),
             "-frames:v", "1", "-vf", "scale=320:-2", str(thumb_path)],
            timeout=60, check=True, capture_output=True,
        )
    except (subprocess.SubprocessError, OSError):
        thumb_path.unlink(missing_ok=True)


def _replaces_previous(category: str, replace: bool | None) -> bool:
    """replace=None 按分类默认规则；显式 True/False 可强制开/关替换。"""
    return category in SINGLE_SLOT_CATEGORIES if replace is None else replace


def _retire_previous(db: Session, *, order_id: str, category: str) -> list[OrderFile]:
    """软删除该订单同分类的全部旧文件，返回被替换的记录（与新文件记录同一事务提交）。

    先锁订单行，把同一订单的并发上传串行化；取旧文件必须用加锁读取：普通快照读看不到
    并发上传刚提交的记录（REPEATABLE READ），会让两份同时留存。先加锁、后写新记录，
    两个并发上传之间才不会互相等待对方未提交的文件行。
    """
    db.query(Order).filter(Order.id == order_id).with_for_update().first()
    stale = (
        db.query(OrderFile)
        .filter(
            OrderFile.order_id == order_id,
            OrderFile.category == category,
            OrderFile.is_deleted == False,  # noqa: E712
        )
        .with_for_update()
        .all()
    )
    for old in stale:
        old.is_deleted = True
    return stale


def save_upload(db: Session, *, order: Order, category: str, original_name: str, stream,
                declared_mime: str | None, remark: str | None, uploader: User,
                replace: bool | None = None) -> tuple[OrderFile, list[OrderFile]]:
    """流式写盘；超限/扩展名不合法时抛 HTTPException 并清理残留文件。

    返回 (新文件记录, 被替换的旧文件记录)。演示视频/程序包一单一份：新文件落盘后把
    同分类旧文件软删除，旧文件随即从附件列表、客户交付链接中移除（磁盘文件保留）。
    """
    oid, cat = _checked_parts(order.id, category)
    original_name = Path(original_name or "file").name[:255]
    ext = Path(original_name).suffix.lower()
    allowed = ALLOWED_EXTS.get(category)
    if allowed is None:
        raise HTTPException(status_code=400, detail=f"非法的附件类型: {category}")
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"该分类不允许上传 {ext or '(无扩展名)'} 文件，允许: {', '.join(sorted(allowed))}",
        )

    limit_mb = MAX_UPLOAD_MB.get(category, 1024)
    stored_uuid = uuid.uuid4().hex
    rel_parts = (oid, cat, stored_uuid)
    for part in rel_parts:
        if "/" in part or "\\" in part or ".." in part:
            raise HTTPException(status_code=400, detail="非法的存储路径(分隔符)")
    abs_dir = _guard_path(UPLOAD_DIR.joinpath(oid, cat))
    abs_dir.mkdir(parents=True, exist_ok=True)
    abs_final = _guard_path(abs_dir / stored_uuid)

    size = 0
    tmp_handle = tempfile.NamedTemporaryFile(prefix="upload-", dir=str(abs_dir), delete=False)
    tmp_path = Path(tmp_handle.name)
    try:
        with tmp_handle as out:
            while True:
                chunk = stream.read(CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit_mb * 1024 * 1024:
                    raise HTTPException(status_code=413, detail=f"文件超过大小限制 {limit_mb}MB")
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="空文件")
        # 原子落位到最终 UUID 文件名
        os.replace(str(tmp_path), str(abs_final))
    except HTTPException:
        tmp_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"保存文件失败: {exc}") from exc

    if category == "video":
        _make_video_thumb(oid, stored_uuid, abs_final)

    mime = (declared_mime or mimetypes.guess_type(original_name)[0] or "application/octet-stream")[:100]
    replaced = (
        _retire_previous(db, order_id=order.id, category=category)
        if _replaces_previous(category, replace) else []
    )
    record = OrderFile(
        order_id=order.id,
        category=category,
        original_name=original_name[:255],
        stored_name="/".join(rel_parts),
        size=size,
        mime=mime,
        remark=(remark or "").strip()[:255] or None,
        uploaded_by=uploader.id,
    )
    db.add(record)
    db.flush()
    return record, replaced


def remove_stored_files(db: Session, records: list[OrderFile]) -> int:
    """从磁盘删除已被替换的文件及其视频缩略图，返回删掉的文件个数。

    只能在数据库事务提交之后调用——旧记录此时才真正失效。若还有其他有效记录引用同一个
    存储路径则跳过（删文件不可恢复，宁可不删）。删除失败只记日志、不影响请求：数据库
    状态已经正确，残留文件可事后清理。
    """
    removed = 0
    for record in records:
        still_used = (
            db.query(OrderFile.id)
            .filter(
                OrderFile.stored_name == record.stored_name,
                OrderFile.is_deleted == False,  # noqa: E712
                OrderFile.id != record.id,
            )
            .first()
        )
        if still_used:
            continue
        try:
            candidates = [_resolve_path(record)]
            parts = (record.stored_name or "").split("/")
            if record.category == "video" and len(parts) == 3 and UUID_RE.match(parts[2]):
                candidates.append(_guard_path(UPLOAD_DIR.joinpath(parts[0], "thumb", parts[2] + ".jpg")))
        except HTTPException:
            continue  # 存储路径不合法的记录不动磁盘
        for path in candidates:
            try:
                path.unlink()
                removed += 1
            except FileNotFoundError:
                pass  # 缩略图不一定存在（服务器没装 ffmpeg 时不会生成）
            except OSError as exc:
                logging.getLogger("uvicorn.error").warning(f"清理被替换的旧文件失败 {path.name}: {exc}")
    return removed


_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def _resolve_path(file: OrderFile) -> Path:
    parts = (file.stored_name or "").split("/")
    if (
        len(parts) != 3
        or not ORDER_ID_RE.match(parts[0])
        or not CATEGORY_RE.match(parts[1])
        or not UUID_RE.match(parts[2])
        or ".." in file.stored_name
    ):
        raise HTTPException(status_code=404, detail="文件不存在")
    return _guard_path(UPLOAD_DIR.joinpath(*parts))


def download_response(
    db: Session,
    *,
    file_id: int,
    request: Request,
    user: User,
    action: str = "file_download",
    force_download: bool = False,
) -> Response:
    file = db.get(OrderFile, file_id)
    if not file or file.is_deleted:
        raise HTTPException(status_code=404, detail="文件不存在")
    order = db.get(Order, file.order_id)
    if not order or order.is_deleted or not can_download(order, user):
        raise HTTPException(status_code=403, detail="无权下载该文件")

    log_op(db, action, request=request, user=user, entity_type="order", entity_id=order.id,
           detail={"file": file.original_name, "category": file.category})
    db.commit()
    return file_stream(file, request, force_attachment=force_download)


def file_stream(file: OrderFile, request: Request, *, force_attachment: bool = False) -> Response:
    """按文件记录流式响应（含 Range 断点/拖动支持）；鉴权与日志由调用方负责。

    视频默认 inline（浏览器在线播放，播放器/预览依赖此行为）；
    下载按钮带 ?download=1 时 force_attachment=True 强制保存文件。
    """
    path = _resolve_path(file)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="文件已丢失，请联系管理员")
    total = path.stat().st_size
    mime = file.mime or "application/octet-stream"

    from urllib.parse import quote

    disposition = "attachment" if (force_attachment or not mime.startswith("video/")) else "inline"
    headers = {
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(file.original_name)}",
        "Accept-Ranges": "bytes",
    }

    range_header = request.headers.get("range", "")
    match = _RANGE_RE.fullmatch(range_header.strip()) if range_header else None
    if match:
        start_s, end_s = match.group(1), match.group(2)
        if not start_s and end_s:
            # 后缀范围 bytes=-N：取最后 N 字节
            n = int(end_s)
            if n == 0 or total == 0:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
            start, end = max(total - n, 0), total - 1
        else:
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else total - 1
        if start >= total or start > end:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        end = min(end, total - 1)

        def gen():
            with path.open("rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        headers.update({
            "Content-Range": f"bytes {start}-{end}/{total}",
            "Content-Length": str(end - start + 1),
        })
        return StreamingResponse(gen(), status_code=206, media_type=mime, headers=headers)

    headers["Content-Length"] = str(total)

    def gen_full():
        with path.open("rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(gen_full(), media_type=mime, headers=headers)


def thumb_path_for(file: OrderFile) -> Path | None:
    """视频缩略图路径（统一走 _guard_path，避免手工拼路径绕过边界检查）。"""
    parts = (file.stored_name or "").split("/")
    if len(parts) != 3 or not ORDER_ID_RE.match(parts[0]) or not UUID_RE.match(parts[2]):
        return None
    candidate = _guard_path(UPLOAD_DIR.joinpath(parts[0], "thumb", parts[2] + ".jpg"))
    return candidate if candidate.exists() and candidate.is_file() else None


def cleanup_expired_chunks() -> int:
    """清理过期的分片上传会话与临时目录（启动时调用，可重复执行）。"""
    db = SessionLocal()
    removed = 0
    try:
        rows = db.query(ChunkUpload).filter(ChunkUpload.expires_at < datetime.now()).all()
        for row in rows:
            root = (UPLOAD_DIR / ".chunks" / row.id).resolve()
            if str(root).startswith(str(UPLOAD_DIR.resolve()) + os.sep):
                shutil.rmtree(root, ignore_errors=True)
            db.delete(row)
            removed += 1
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()
    return removed
