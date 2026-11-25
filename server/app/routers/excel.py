"""Excel 批量导入/导出接口（/api/excel）。

导出用 StreamingResponse 分块下发；导入先整份读进内存（≤10MB）再逐行校验，
失败行只跳过并回填 Excel 行号，成功行每行 flush、最后统一 commit。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import ORDER_STATUSES
from ..database import get_db
from ..deps import require_staff
from ..models import Customer, Order, Quality, User
from ..services import excel_io
from ..services.oplog import log_op
from ..services.order_no import CUSTOM_NO_RE
from ..services.order_svc import create_order, order_query
from ..services.pricing import compute_prices, get_quality_by_code

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/excel", tags=["excel"])

# 单行字段上限，与 schemas.OrderCreateIn / CustomerIn 保持一致。
MAX_TITLE = 255
MAX_TECH_STACK = 100
MAX_CUSTOMER_INFO = 255
MAX_REMARK = 2000
MAX_CUSTOMER_NAME = 100
MAX_CUSTOMER_CONTACT = 120
MAX_CUSTOMER_SCHOOL = 100
MAX_CUSTOMER_SOURCE = 50
MAX_CUSTOMER_NOTE = 2000


async def _read_upload(file: UploadFile) -> bytes:
    """读取上传文件：后缀、大小（10MB）与空文件校验。"""
    filename = (file.filename or "").strip()
    if filename and Path(filename).suffix.lower() != ".xlsx":
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 文件，请用 Excel 另存为 .xlsx 后再上传")
    data = await file.read(excel_io.MAX_UPLOAD_BYTES + 1)
    if len(data) > excel_io.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件超过大小限制 {excel_io.MAX_UPLOAD_BYTES // 1024 // 1024}MB，请拆分后导入",
        )
    if not data:
        raise HTTPException(status_code=400, detail="文件内容为空，请选择要导入的 .xlsx 文件")
    return data


def _optional_text(value: object, limit: int, field: str) -> str | None:
    text = excel_io.clean_text(value)
    if not text:
        return None
    if len(text) > limit:
        raise ValueError(f"{field}不能超过 {limit} 个字符")
    return text


def _stream_response(buffer, filename: str, *, truncated: bool) -> StreamingResponse:
    """xlsx 流式响应；Content-Length 让浏览器能显示下载进度。"""
    return StreamingResponse(
        excel_io.stream_xlsx(buffer),
        media_type=excel_io.XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Content-Length": str(buffer.getbuffer().nbytes),
            "X-Export-Truncated": "1" if truncated else "0",
        },
    )


# ============================== 订单 ==============================

@router.get("/orders/template")
def order_import_template(user: User = Depends(require_staff)):
    """下载订单导入模板（仅表头，列名与导入解析一致）。"""
    return _stream_response(excel_io.build_order_import_template(), "订单导入模板.xlsx", truncated=False)


@router.get("/orders/export")
def export_orders(
    request: Request,
    status: str | None = Query(default=None),
    quality: str | None = Query(default=None, max_length=10),
    project_type: str | None = Query(default=None, pattern=r"^(program|thesis|thesis_program)$"),
    keyword: str | None = Query(default=None, max_length=100),
    agent_id: int | None = Query(default=None),
    agent_username: str | None = Query(default=None, max_length=50),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """导出订单 xlsx：管理员含真实价与毛利，协助者不含真实价。

    筛选条件与 /api/orders 列表保持一致，便于「筛完直接导出」。
    """
    if status and status not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail=f"订单状态无效：{status}")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")

    q = order_query(db)
    if status:
        q = q.filter(Order.status == status)
    if quality:
        q = q.join(Quality).filter(Quality.code == quality)
    if project_type:
        q = q.filter(Order.project_type == project_type)
    if keyword:
        kw = f"%{keyword.strip()}%"
        q = q.filter(or_(Order.title.like(kw), Order.id.like(kw)))
    if agent_id:
        q = q.filter(Order.agent_user_id == agent_id)
    if date_from:
        q = q.filter(Order.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        q = q.filter(Order.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
    if agent_username:
        agent = db.query(User).filter(User.username == agent_username.strip()).first()
        if not agent:
            raise HTTPException(status_code=400, detail=f"代理不存在：{agent_username}")
        q = q.filter(Order.agent_user_id == agent.id)
    q = q.order_by(Order.created_at.desc())

    include_owner = user.role == "admin"
    exported = {"count": 0, "truncated": False}

    def rows():
        # 用 yield_per 游标分批取，避免一次性实例化整表；另设硬上限兜底内存。
        for order in q.yield_per(500):
            if exported["count"] >= excel_io.MAX_EXPORT_ROWS:
                exported["truncated"] = True
                break
            exported["count"] += 1
            yield excel_io.order_export_row(order, include_owner=include_owner)

    buffer = excel_io.build_workbook(
        excel_io.order_export_headers(include_owner),
        rows(),
        sheet_title="订单",
    )
    log_op(
        db,
        "order_excel_export",
        request=request,
        user=user,
        detail={
            "count": exported["count"],
            "truncated": exported["truncated"],
            "include_owner": include_owner,
        },
    )
    db.commit()
    filename = f"订单导出-{date.today().strftime('%Y%m%d')}.xlsx"
    return _stream_response(buffer, filename, truncated=exported["truncated"])


def _parse_order_row(
    db: Session,
    item: dict[str, object],
    *,
    allow_owner_price: bool,
    agent_cache: dict[str, User | None],
) -> dict[str, object]:
    """校验并规整一行订单数据；不合法抛 ValueError（中文提示）。"""
    title = excel_io.clean_text(item.get("标题"))
    if not title:
        raise ValueError("标题不能为空")
    if len(title) < 2:
        raise ValueError("标题至少 2 个字符")
    if len(title) > MAX_TITLE:
        raise ValueError(f"标题不能超过 {MAX_TITLE} 个字符")

    quality_code = excel_io.clean_text(item.get("品质代码")).lower()
    if not quality_code:
        raise ValueError("品质代码不能为空")
    quality = get_quality_by_code(db, quality_code)
    if quality is None:
        # 兼容“导出文件直接改一改再导回”：导出列是中文品质名（如“绿色”）
        quality = (
            db.query(Quality)
            .filter(Quality.name == quality_code, Quality.enabled == True)  # noqa: E712
            .first()
        )
    if quality is None:
        raise ValueError(f"品质代码不存在或已停用：{quality_code}")

    agent_user: User | None = None
    agent_name = excel_io.clean_text(item.get("代理用户名"))
    if agent_name:
        if agent_name not in agent_cache:
            agent_cache[agent_name] = (
                db.query(User)
                .filter(
                    User.username == agent_name,
                    User.role == "agent",
                    User.is_active == True,  # noqa: E712
                )
                .first()
            )
        agent_user = agent_cache[agent_name]
        if agent_user is None:
            raise ValueError(f"代理用户名不存在或已停用：{agent_name}")

    type_text = excel_io.clean_text(item.get("项目类型"))
    if type_text:
        key = type_text.lower() if type_text.isascii() else type_text
        project_type = excel_io.PROJECT_TYPE_IMPORT.get(key)
        if not project_type:
            raise ValueError(f"项目类型无效：{type_text}（可填 纯程序设计/纯论文/论文+设计）")
    else:
        project_type = "thesis"

    deadline = excel_io.parse_date(item.get("期限"), field="期限")
    tech_stack = _optional_text(item.get("技术栈"), MAX_TECH_STACK, "技术栈")
    customer_info = _optional_text(item.get("客户信息"), MAX_CUSTOMER_INFO, "客户信息")
    remark = _optional_text(item.get("备注"), MAX_REMARK, "备注")

    owner_price: Decimal | None = None
    if allow_owner_price:
        owner_price = excel_io.parse_decimal(item.get("真实价"), field="真实价")

    # 可选“单号”列：导入历史项目保留原编号；填了就先做格式校验（重复/冲突在写入时校验）
    order_no = excel_io.clean_text(item.get("单号"))
    if order_no and not CUSTOM_NO_RE.fullmatch(order_no):
        raise ValueError("单号仅支持 2-16 位字母、数字、中划线(-)、下划线(_)")

    return {
        "title": title,
        "order_no": order_no or None,
        "quality": quality,
        "agent_user": agent_user,
        "agent_username": agent_user.username if agent_user else "",
        "project_type": project_type,
        "deadline": deadline,
        "tech_stack": tech_stack,
        "customer_info": customer_info,
        "remark": remark,
        "owner_price": owner_price,
    }


@router.post("/orders/import")
async def import_orders(
    request: Request,
    file: UploadFile = File(...),
    dry_run: int = Form(default=0),
    # 订单/客户 Excel 导入导出限管理员与写手（README）：写手可协助导入，但不能通过 Excel 指定真实价
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """批量导入订单；dry_run=1 只校验并返回预览，不写库。"""
    data = await _read_upload(file)
    try:
        _, rows = excel_io.read_sheet(
            data,
            required=("标题", "品质代码"),
            aliases=excel_io.ORDER_IMPORT_ALIASES,
        )
    except excel_io.ExcelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    allow_owner_price = user.role == "admin"
    agent_cache: dict[str, User | None] = {}
    failed: list[dict[str, object]] = []
    preview: list[dict[str, object]] = []
    created_ids: list[str] = []
    valid = 0

    for row_no, item in rows:
        try:
            values = _parse_order_row(
                db, item, allow_owner_price=allow_owner_price, agent_cache=agent_cache,
            )
            if dry_run:
                valid += 1
                if len(preview) < excel_io.MAX_PREVIEW_ROWS:
                    preview.append({
                        "row": row_no,
                        "order_no": values["order_no"] or "自动生成",
                        "title": values["title"],
                        "quality_code": values["quality"].code,
                        "quality_name": values["quality"].name,
                        "agent_username": values["agent_username"],
                        "project_type": values["project_type"],
                        "deadline": (
                            values["deadline"].isoformat() if values["deadline"] else None
                        ),
                        "tech_stack": values["tech_stack"] or "",
                        "customer_info": values["customer_info"] or "",
                        "remark": values["remark"] or "",
                        "owner_price": (
                            float(values["owner_price"])
                            if values["owner_price"] is not None
                            else None
                        ),
                    })
                continue

            with db.begin_nested():
                order = create_order(
                    db,
                    title=values["title"],
                    # “单号”列仅管理员导入生效（导入历史项目保留原编号）
                    order_no=(values["order_no"] if user.role == "admin" else None),
                    quality_code=values["quality"].code,
                    creator=user,
                    deadline=values["deadline"],
                    tech_stack=values["tech_stack"],
                    customer_info=values["customer_info"],
                    remark=values["remark"],
                    agent_user=values["agent_user"],
                    project_type=values["project_type"],
                    owner_price_override=(
                        float(values["owner_price"])
                        if values["owner_price"] is not None
                        else None
                    ),
                )
            created_ids.append(order.id)
        except ValueError as exc:
            failed.append({"row": row_no, "error": str(exc)})
        except Exception:  # noqa: BLE001 —— 单行失败不影响其他行，整批最后统一提交
            logger.exception("订单 Excel 导入第 %s 行失败", row_no)
            failed.append({"row": row_no, "error": "该行写入失败，请检查内容后重试"})

    total = len(rows)
    failed.sort(key=lambda entry: entry["row"])

    if dry_run:
        return {
            "ok": not failed,
            "dry_run": True,
            "created": 0,
            "valid": valid,
            "total": total,
            "preview": preview,
            "preview_truncated": valid > len(preview),
            "failed": failed,
        }

    log_op(
        db,
        "order_excel_import",
        request=request,
        user=user,
        detail={"created": len(created_ids), "failed": len(failed), "total": total},
    )
    db.commit()
    return {
        "ok": not failed,
        "dry_run": False,
        "created": len(created_ids),
        "total": total,
        "orders": created_ids,
        "failed": failed,
    }


# ============================== 客户 ==============================

@router.get("/customers/template")
def customer_import_template(user: User = Depends(require_staff)):
    """下载客户导入模板（仅表头）。"""
    return _stream_response(excel_io.build_customer_import_template(), "客户导入模板.xlsx", truncated=False)


@router.get("/customers/export")
def export_customers(
    request: Request,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """导出客户库 xlsx；归属用户以用户名展示。"""
    rows = (
        db.query(Customer)
        .order_by(Customer.created_at.desc())
        .limit(excel_io.MAX_EXPORT_ROWS + 1)
        .all()
    )
    truncated = len(rows) > excel_io.MAX_EXPORT_ROWS
    rows = rows[: excel_io.MAX_EXPORT_ROWS]

    owner_ids = {customer.owner_id for customer in rows if customer.owner_id}
    owner_names: dict[int, str] = {}
    if owner_ids:
        for owner_id, username in (
            db.query(User.id, User.username).filter(User.id.in_(owner_ids)).all()
        ):
            owner_names[owner_id] = username

    buffer = excel_io.build_customers_workbook(
        (customer, owner_names.get(customer.owner_id, "")) for customer in rows
    )
    log_op(
        db,
        "customer_excel_export",
        request=request,
        user=user,
        detail={"count": len(rows), "truncated": truncated},
    )
    db.commit()
    filename = f"客户导出-{date.today().strftime('%Y%m%d')}.xlsx"
    return _stream_response(buffer, filename, truncated=truncated)


def _parse_customer_row(
    db: Session,
    item: dict[str, object],
    *,
    current_user: User,
    owner_cache: dict[str, User | None],
) -> dict[str, object]:
    """校验并规整一行客户数据；不合法抛 ValueError（中文提示）。"""
    name = excel_io.clean_text(item.get("客户名称"))
    if not name:
        raise ValueError("客户名称不能为空")
    if len(name) > MAX_CUSTOMER_NAME:
        raise ValueError(f"客户名称不能超过 {MAX_CUSTOMER_NAME} 个字符")

    owner_text = excel_io.clean_text(item.get("归属用户"))
    if owner_text:
        if owner_text not in owner_cache:
            owner_cache[owner_text] = (
                db.query(User)
                .filter(User.username == owner_text, User.is_active == True)  # noqa: E712
                .first()
            )
        owner = owner_cache[owner_text]
        if owner is None:
            raise ValueError(f"归属用户不存在或已停用：{owner_text}")
    else:
        # 留空 = 归属当前操作人
        owner = current_user

    return {
        "name": name,
        "contact": _optional_text(item.get("联系方式"), MAX_CUSTOMER_CONTACT, "联系方式"),
        "school": _optional_text(item.get("学校专业"), MAX_CUSTOMER_SCHOOL, "学校专业"),
        "source": _optional_text(item.get("来源渠道"), MAX_CUSTOMER_SOURCE, "来源渠道"),
        "note": _optional_text(item.get("备注"), MAX_CUSTOMER_NOTE, "备注"),
        "owner_id": owner.id,
        "owner_username": owner.username,
    }


@router.post("/customers/import")
async def import_customers(
    request: Request,
    file: UploadFile = File(...),
    dry_run: int = Form(default=0),
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """批量导入客户；同一归属下同名的客户自动跳过并计入 failed。"""
    data = await _read_upload(file)
    try:
        _, rows = excel_io.read_sheet(
            data,
            required=("客户名称",),
            aliases=excel_io.CUSTOMER_IMPORT_ALIASES,
        )
    except excel_io.ExcelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    owner_cache: dict[str, User | None] = {}
    failed: list[dict[str, object]] = []
    parsed: list[tuple[int, dict[str, object]]] = []

    for row_no, item in rows:
        try:
            parsed.append((
                row_no,
                _parse_customer_row(db, item, current_user=user, owner_cache=owner_cache),
            ))
        except ValueError as exc:
            failed.append({"row": row_no, "error": str(exc)})

    # 一次查出涉及的 (归属, 姓名) 判断重复，含文件内重复，避免逐行查库。
    owner_ids = {values["owner_id"] for _, values in parsed}
    existing: set[tuple[int, str]] = set()
    if owner_ids:
        existing = {
            (owner_id, name)
            for owner_id, name in db.query(Customer.owner_id, Customer.name)
            .filter(Customer.owner_id.in_(owner_ids))
            .all()
        }

    preview: list[dict[str, object]] = []
    to_create: list[tuple[int, dict[str, object]]] = []
    valid = 0
    for row_no, values in parsed:
        key = (values["owner_id"], values["name"])
        if key in existing:
            failed.append({"row": row_no, "error": "该客户已存在（同名同归属），已跳过"})
            continue
        existing.add(key)
        valid += 1
        if dry_run:
            if len(preview) < excel_io.MAX_PREVIEW_ROWS:
                preview.append({
                    "row": row_no,
                    "name": values["name"],
                    "contact": values["contact"] or "",
                    "school": values["school"] or "",
                    "source": values["source"] or "",
                    "note": values["note"] or "",
                    "owner_username": values["owner_username"],
                })
        else:
            to_create.append((row_no, values))

    total = len(rows)
    failed.sort(key=lambda entry: entry["row"])

    if dry_run:
        return {
            "ok": not failed,
            "dry_run": True,
            "created": 0,
            "valid": valid,
            "total": total,
            "preview": preview,
            "preview_truncated": valid > len(preview),
            "failed": failed,
        }

    created = 0
    for row_no, values in to_create:
        try:
            with db.begin_nested():
                customer = Customer(
                    name=values["name"],
                    contact=values["contact"],
                    school=values["school"],
                    source=values["source"],
                    note=values["note"],
                    owner_id=values["owner_id"],
                )
                db.add(customer)
                db.flush()
            created += 1
        except Exception:  # noqa: BLE001 —— 单行失败不影响其他行，整批最后统一提交
            logger.exception("客户 Excel 导入第 %s 行失败", row_no)
            failed.append({"row": row_no, "error": "该行写入失败，请检查内容后重试"})

    failed.sort(key=lambda entry: entry["row"])
    log_op(
        db,
        "customer_excel_import",
        request=request,
        user=user,
        detail={"created": created, "failed": len(failed), "total": total},
    )
    db.commit()
    return {
        "ok": not failed,
        "dry_run": False,
        "created": created,
        "total": total,
        "failed": failed,
    }
