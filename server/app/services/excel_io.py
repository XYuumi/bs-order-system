"""Excel 批量导入/导出：openpyxl 读写、表头校验与公式注入防护。

本模块只做纯数据处理（不查库、不抛 HTTP 异常），路由层负责权限、事务
与状态码；这样读写逻辑可以单独测试，也便于以后被代理 API 复用。
"""
from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, Iterator, Sequence

from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

# 上传上限 10MB：超出直接拒绝，避免把服务器内存/带宽打满。
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# 单次导入行数上限，超出请拆分文件分批导入。
MAX_IMPORT_ROWS = 2000
# 单次导出行数上限，与 orders.py 的 CSV 导出一致。
MAX_EXPORT_ROWS = 20000
# dry_run 预览最多返回的行数，避免响应体过大。
MAX_PREVIEW_ROWS = 100

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Excel/WPS 会把 = + - @ 开头的文本当公式执行，写入前加单引号强制按文本显示。
FORMULA_PREFIXES = ("=", "+", "-", "@")

STATUS_CN = {
    "pending": "待开始",
    "in_progress": "制作中",
    "completed": "已完成",
    "closed": "已结单",
    "after_sale": "售后中",
    "cancelled": "已取消",
}

PROJECT_TYPE_CN = {"program": "纯程序设计", "thesis": "纯论文", "thesis_program": "论文+设计"}

# 导入时“项目类型”列可填中文或英文代码；旧模板的“工种”列与旧值也兼容，留空按纯论文处理。
PROJECT_TYPE_IMPORT = {
    "program": "program",
    "纯程序设计": "program",
    "纯设计": "program",
    # 旧工种值归一：程序/艺术设计与纯程序设计同为“无论文交付”
    "code": "program",
    "design": "program",
    "程序设计": "program",
    "程序": "program",
    "软件": "program",
    "艺术设计": "program",
    "设计": "program",
    "thesis": "thesis",
    "纯论文": "thesis",
    "论文": "thesis",
    "thesis_program": "thesis_program",
    "论文+设计": "thesis_program",
    "论文加设计": "thesis_program",
    "论文和设计": "thesis_program",
}

# 订单导出列：管理员在“代理价”后多出“真实价/毛利”两列。
ORDER_EXPORT_HEADERS = ["单号", "标题", "品质", "状态", "项目类型", "代理", "负责人", "代理价"]
ORDER_OWNER_HEADERS = ["真实价", "毛利"]
ORDER_EXPORT_TAIL_HEADERS = ["下单时间", "完成时间", "期限"]

CUSTOMER_EXPORT_HEADERS = ["客户名称", "联系方式", "学校专业", "来源渠道", "备注", "归属用户", "创建时间"]

# 导入表头别名：既接受导入模板，也接受“导出文件直接改一改再导回”。
# 导出列叫「品质 / 代理」，导入要求「品质代码 / 代理用户名」，这里做兼容。
ORDER_IMPORT_ALIASES = {
    "品质": "品质代码",
    "代理": "代理用户名",
    # 旧模板的“工种”列直接当作项目类型解析（值兼容见 PROJECT_TYPE_IMPORT）
    "工种": "项目类型",
}

CUSTOMER_IMPORT_ALIASES = {
    "姓名": "客户名称",
    "name": "客户名称",
    "owner_username": "归属用户",
    "归属人": "归属用户",
}

ORDER_IMPORT_HEADERS = [
    "单号", "标题", "品质代码", "代理用户名", "项目类型", "期限", "技术栈", "客户信息", "备注", "真实价",
]
CUSTOMER_IMPORT_HEADERS = ["客户名称", "联系方式", "学校专业", "来源渠道", "备注", "归属用户"]

MONEY_MAX = Decimal("99999999")


class ExcelError(ValueError):
    """整份文件级错误（大小/格式/表头/行数）：路由层统一转 400。"""


def clean_text(value: object, limit: int | None = None) -> str:
    """单元格值转文本并去空白；数字型手机号/单号不会变成 12345.0。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        text = "是" if value else "否"
    elif isinstance(value, float) and value.is_integer():
        text = str(int(value))
    elif isinstance(value, Decimal):
        text = format(value.normalize(), "f")
    elif isinstance(value, datetime):
        text = value.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(value, date):
        text = value.isoformat()
    else:
        text = str(value)
    text = text.strip()
    if limit is not None:
        text = text[:limit]
    return text


def safe_cell(value: object) -> object:
    """写单元格前的清洗：去控制字符；= + - @ 开头的文本加前导单引号防公式注入。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float, Decimal)):
        # 数值单元格不会被当公式执行，保持数字类型便于在 Excel 里求和。
        return value
    text = ILLEGAL_CHARACTERS_RE.sub("", str(value))
    if text[:1] in FORMULA_PREFIXES:
        return "'" + text
    return text


def parse_date(value: object, *, field: str = "日期") -> date | None:
    """解析日期：支持 Excel 日期单元格与 YYYY-MM-DD/YYYY/MM/DD 等常见写法。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = clean_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"{field}格式应为 YYYY-MM-DD（当前填写：{text[:20]}）")


def parse_decimal(
    value: object,
    *,
    field: str = "金额",
    maximum: Decimal = MONEY_MAX,
) -> Decimal | None:
    """解析金额：容忍千分位/￥/¥/元，要求大于等于 0 且不超过上限。"""
    if isinstance(value, Decimal):
        return _check_money(value, field=field, maximum=maximum)
    if isinstance(value, bool):
        raise ValueError(f"{field}必须是数字")
    text = (
        clean_text(value)
        .replace(",", "")
        .replace("，", "")
        .replace("￥", "")
        .replace("¥", "")
        .replace("元", "")
    )
    if not text:
        return None
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field}必须是数字（当前填写：{text[:20]}）") from None
    return _check_money(amount, field=field, maximum=maximum)


def _check_money(amount: Decimal, *, field: str, maximum: Decimal) -> Decimal:
    if not amount.is_finite():
        raise ValueError(f"{field}必须是数字")
    amount = amount.quantize(Decimal("0.01"))
    if amount < 0:
        raise ValueError(f"{field}不能小于 0")
    if amount > maximum:
        raise ValueError(f"{field}不能超过 {maximum:.0f}")
    return amount


def order_export_headers(include_owner: bool) -> list[str]:
    """导出表头；include_owner（管理员）时插入真实价与毛利。"""
    if include_owner:
        return ORDER_EXPORT_HEADERS + ORDER_OWNER_HEADERS + ORDER_EXPORT_TAIL_HEADERS
    return ORDER_EXPORT_HEADERS + ORDER_EXPORT_TAIL_HEADERS


def order_export_row(order, *, include_owner: bool) -> list[object]:
    """把 Order 转成一行导出数据（未做公式防护，build_workbook 会统一处理）。"""
    agent_price = _money(order.agent_price)
    row: list[object] = [
        order.id,
        order.title,
        order.quality.name if order.quality else "",
        STATUS_CN.get(order.status, order.status),
        PROJECT_TYPE_CN.get(order.project_type, "未设置"),
        order.agent.username if order.agent else "自接",
        order.assignee.username if order.assignee else "",
        agent_price,
    ]
    if include_owner:
        owner_price = _money(order.owner_price)
        row.extend([owner_price, round(owner_price - agent_price, 2)])
    row.extend([
        _datetime_text(order.created_at),
        _datetime_text(order.completed_at),
        order.deadline.isoformat() if order.deadline else "",
    ])
    return row


def customer_export_row(customer, owner_username: str) -> list[object]:
    """把 Customer 转成一行导出数据。"""
    return [
        customer.name,
        customer.contact or "",
        customer.school or "",
        customer.source or "",
        customer.note or "",
        owner_username,
        _datetime_text(customer.created_at),
    ]


def _money(value: object) -> float:
    return round(float(value or 0), 2)


def _datetime_text(value: object) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)[:19]


def build_workbook(
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
    *,
    sheet_title: str = "数据",
) -> io.BytesIO:
    """按表头+数据生成 xlsx，返回已回到开头的 BytesIO。

    用 write_only 模式逐行写盘，导出几万行也不会把整表实例化进内存。
    """
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(title=sheet_title[:31])
    for index, title in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(index)].width = min(40, max(10, len(title) * 2 + 6))
    header_cells = []
    for title in headers:
        cell = WriteOnlyCell(ws, value=title)
        cell.font = Font(bold=True)
        header_cells.append(cell)
    ws.append(header_cells)
    ws.freeze_panes = "A2"
    for row in rows:
        ws.append([safe_cell(value) for value in row])
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def build_orders_workbook(orders: Iterable[object], *, include_owner: bool) -> io.BytesIO:
    return build_workbook(
        order_export_headers(include_owner),
        (order_export_row(order, include_owner=include_owner) for order in orders),
        sheet_title="订单",
    )


def build_customers_workbook(items: Iterable[tuple[object, str]]) -> io.BytesIO:
    return build_workbook(
        CUSTOMER_EXPORT_HEADERS,
        (customer_export_row(customer, owner_username) for customer, owner_username in items),
        sheet_title="客户",
    )


def build_order_import_template() -> io.BytesIO:
    """订单导入模板：表头必须与导入解析保持一致，留空供填写。"""
    return build_workbook(ORDER_IMPORT_HEADERS, [], sheet_title="订单导入模板")


def build_customer_import_template() -> io.BytesIO:
    """客户导入模板：同上。"""
    return build_workbook(CUSTOMER_IMPORT_HEADERS, [], sheet_title="客户导入模板")


def stream_xlsx(buffer: io.BytesIO, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    """把内存中的 xlsx 分块吐出，流式响应结束后释放缓冲区。"""
    try:
        while True:
            chunk = buffer.read(chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        buffer.close()


def read_sheet(
    data: bytes,
    *,
    required: Sequence[str],
    aliases: dict[str, str] | None = None,
    max_rows: int = MAX_IMPORT_ROWS,
) -> tuple[list[str], list[tuple[int, dict[str, object]]]]:
    """读取上传的 xlsx：校验大小/格式/表头/行数，返回 (表头, [(Excel 行号, 行数据)])。

    行数据以“表头名”为键（别名已归一），整行空白的行自动跳过；行号从 2 开始，
    与 Excel 里用户看到的行号一致，方便定位错误。任何整份文件级问题抛 ExcelError。
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise ExcelError(f"文件超过大小限制 {MAX_UPLOAD_BYTES // 1024 // 1024}MB，请拆分后导入")
    if not data:
        raise ExcelError("文件内容为空，请选择要导入的 .xlsx 文件")

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 —— openpyxl 对坏文件抛的异常类型很杂
        raise ExcelError("文件不是有效的 xlsx 格式（仅支持 .xlsx）") from exc

    try:
        ws = wb.active
        if ws is None:
            raise ExcelError("文件中没有可用的工作表")
        rows = ws.iter_rows(values_only=True)
        raw_headers = next(rows, None)
        if not raw_headers or not any(clean_text(value) for value in raw_headers):
            raise ExcelError("文件内容为空，未找到表头行")

        headers = [clean_text(value) for value in raw_headers]
        columns: dict[str, int] = {}
        for index, title in enumerate(headers):
            key = _header_key(title, aliases)
            if key and key not in columns:
                columns[key] = index

        missing = [name for name in required if name not in columns]
        if missing:
            raise ExcelError("表头缺少必需列：" + "、".join(missing) + "。请使用导出的模板填写")

        collected: list[tuple[int, dict[str, object]]] = []
        for row_no, values in enumerate(rows, start=2):
            if values is None:
                continue
            item = {
                name: (values[index] if index < len(values) else None)
                for name, index in columns.items()
            }
            if all(clean_text(value) == "" for value in item.values()):
                continue
            collected.append((row_no, item))
            if len(collected) > max_rows:
                raise ExcelError(f"数据行数超过上限 {max_rows} 行，请拆分后分批导入")
        if not collected:
            raise ExcelError("没有可导入的数据行")
        return headers, collected
    finally:
        wb.close()


def _header_key(title: str, aliases: dict[str, str] | None) -> str:
    if not aliases:
        return title
    if title in aliases:
        return aliases[title]
    lowered = title.lower()
    return aliases.get(lowered, title)
