"""Excel 批量导入/导出接口测试（/api/excel）。

main.py 不在本次允许改动的文件清单内，测试在导入期显式挂载 excel 路由，
保证本文件可独立运行；正式上线仍需在 main.py 补 include_router。
"""
from __future__ import annotations

import io
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from openpyxl import Workbook, load_workbook

from app.main import app
from app.models import Customer, Order, User
from app.routers import excel as excel_router
from app.services import excel_io
from app.services.excel_io import ExcelError

# FastAPI 的 include_router 在当前版本登记为 _IncludedRouter 占位对象，app.routes
# 里拿不到子路由 path，因此用标记位防止同一进程内重复挂载。
if not getattr(app, "_excel_router_mounted", False):
    app.include_router(excel_router.router)
    app._excel_router_mounted = True

ORDER_IMPORT_HEADERS = ["标题", "品质代码", "代理用户名", "项目类型", "期限", "技术栈", "客户信息", "备注", "真实价"]
CUSTOMER_IMPORT_HEADERS = ["客户名称", "联系方式", "学校专业", "来源渠道", "备注", "owner_username"]


# ============================== 工具函数 ==============================

def _xlsx(headers, rows, *, sheet_title: str = "Sheet1") -> bytes:
    """在测试里现造一个 xlsx 文件（普通模式写，行数少不占内存）。"""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_title
    sheet.append([str(value) for value in headers])
    for row in rows:
        sheet.append([value for value in row])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _sheet(content: bytes) -> list[list[object]]:
    """读回导出的 xlsx（read_only 省内存）；返回二维列表。"""
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        return [list(row) for row in workbook.active.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _index(rows: list[list[object]]) -> dict[str, int]:
    return {str(name): index for index, name in enumerate(rows[0])}


def _body(rows: list[list[object]]) -> list[list[object]]:
    return rows[1:]


def _find(rows: list[list[object]], column: str, value: object) -> list[object]:
    index = _index(rows)
    for row in _body(rows):
        if row[index[column]] == value:
            return row
    raise AssertionError(f"导出结果中未找到 {column}={value}")


def _fresh(db) -> None:
    """结束只读事务，避免 MySQL REPEATABLE READ 读到请求之前的旧快照。"""
    db.rollback()


def _import_orders(client, content: bytes, *, dry_run: int | None = None, filename: str = "orders.xlsx"):
    data = {} if dry_run is None else {"dry_run": str(dry_run)}
    return client.post(
        "/api/excel/orders/import",
        files={"file": (filename, content, excel_io.XLSX_MEDIA_TYPE)},
        data=data,
    )


def _import_customers(client, content: bytes, *, dry_run: int | None = None, filename: str = "customers.xlsx"):
    data = {} if dry_run is None else {"dry_run": str(dry_run)}
    return client.post(
        "/api/excel/customers/import",
        files={"file": (filename, content, excel_io.XLSX_MEDIA_TYPE)},
        data=data,
    )


def _delete_orders(db, ids: list[str]) -> None:
    if not ids:
        return
    db.query(Order).filter(Order.id.in_(ids)).delete(synchronize_session=False)
    db.commit()


# ============================== 导入模板 ==============================

def test_import_templates_headers(admin_client):
    for kind, expected in (
        ("orders", excel_io.ORDER_IMPORT_HEADERS),
        ("customers", excel_io.CUSTOMER_IMPORT_HEADERS),
    ):
        resp = admin_client.get(f"/api/excel/{kind}/template")
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith(excel_io.XLSX_MEDIA_TYPE)
        rows = _sheet(resp.content)
        assert rows and rows[0] == expected


def test_order_import_accepts_quality_name_and_export_alias(admin_client):
    """导出的列叫「品质 / 代理」，导入应能直接复用；品质名也接受。"""
    content = _xlsx(["标题", "品质"], [["导出列回灌", "绿色"]])
    resp = _import_orders(admin_client, content, dry_run=1)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["valid"] == 1
    assert data["failed"] == []
    assert data["preview"][0]["quality_code"] == "green"


# ============================== 订单导出 ==============================

def test_export_orders_admin_and_staff_columns(admin_client, staff_client, order_factory):
    order = order_factory("导出列测试")
    order_id = order["id"]

    resp = admin_client.get("/api/excel/orders/export")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith(excel_io.XLSX_MEDIA_TYPE)
    assert "filename*=UTF-8''" in resp.headers["content-disposition"]
    assert resp.headers["X-Export-Truncated"] == "0"

    rows = _sheet(resp.content)
    assert [str(value) for value in rows[0]] == excel_io.order_export_headers(include_owner=True)
    index = _index(rows)
    row = _find(rows, "单号", order_id)
    assert row[index["标题"]] == "导出列测试"
    assert row[index["品质"]] == "白色"
    assert row[index["状态"]] == "待开始"
    assert row[index["项目类型"]] == "纯程序设计"
    assert row[index["代理"]] == "自接"
    assert isinstance(row[index["代理价"]], (int, float))
    assert isinstance(row[index["真实价"]], (int, float))
    assert row[index["毛利"]] == pytest.approx(row[index["真实价"]] - row[index["代理价"]], abs=0.01)
    assert row[index["下单时间"]]

    staff_resp = staff_client.get("/api/excel/orders/export")
    assert staff_resp.status_code == 200, staff_resp.text
    staff_rows = _sheet(staff_resp.content)
    staff_headers = [str(value) for value in staff_rows[0]]
    assert staff_headers == excel_io.order_export_headers(include_owner=False)
    assert "真实价" not in staff_headers
    assert "毛利" not in staff_headers
    assert _find(staff_rows, "单号", order_id)


def test_export_orders_formula_injection(admin_client, order_factory):
    order = order_factory("=2+2")
    rows = _sheet(admin_client.get("/api/excel/orders/export").content)
    index = _index(rows)
    row = _find(rows, "单号", order["id"])
    assert row[index["标题"]] == "'=2+2"


def test_export_orders_filters(admin_client, order_factory):
    order = order_factory("导出筛选测试", agent_username="agent1")
    order_id = order["id"]
    today = date.today()
    tomorrow = today + timedelta(days=1)

    resp = admin_client.get("/api/excel/orders/export", params={"agent_username": "agent1"})
    assert resp.status_code == 200, resp.text
    rows = _sheet(resp.content)
    index = _index(rows)
    assert _body(rows)
    assert all(row[index["代理"]] == "agent1" for row in _body(rows))
    assert any(row[index["单号"]] == order_id for row in _body(rows))

    resp = admin_client.get("/api/excel/orders/export", params={"status": "completed"})
    assert resp.status_code == 200, resp.text
    rows = _sheet(resp.content)
    index = _index(rows)
    assert all(row[index["状态"]] == "已完成" for row in _body(rows))
    assert all(row[index["单号"]] != order_id for row in _body(rows))

    params = {"date_from": today.isoformat(), "date_to": today.isoformat()}
    resp = admin_client.get("/api/excel/orders/export", params=params)
    assert resp.status_code == 200, resp.text
    rows = _sheet(resp.content)
    index = _index(rows)
    assert any(row[index["单号"]] == order_id for row in _body(rows))

    resp = admin_client.get("/api/excel/orders/export", params={"date_from": tomorrow.isoformat()})
    assert resp.status_code == 200, resp.text
    rows = _sheet(resp.content)
    index = _index(rows)
    assert all(row[index["单号"]] != order_id for row in _body(rows))

    assert admin_client.get("/api/excel/orders/export", params={"status": "unknown"}).status_code == 400
    assert admin_client.get(
        "/api/excel/orders/export", params={"agent_username": "ghost-agent"}
    ).status_code == 400
    assert admin_client.get(
        "/api/excel/orders/export",
        params={"date_from": tomorrow.isoformat(), "date_to": today.isoformat()},
    ).status_code == 400


# ============================== 订单导入 ==============================

def test_import_orders_dry_run_validates_rows(admin_client, db):
    stamp = uuid4().hex[:8]
    title_ok = f"导入预览有效-{stamp}"
    title_ok_second = f"导入预览有效B-{stamp}"
    content = _xlsx(ORDER_IMPORT_HEADERS, [
        [title_ok, "WHITE", "agent1", "程序设计", "2026-12-31", "Vue 3", "张三 13800000000", "备注一", 900],
        ["", "white", "", "", "", "", "", "", ""],
        [f"导入预览品质-{stamp}", "不存在", "", "", "", "", "", "", ""],
        [f"导入预览代理-{stamp}", "white", "ghost-agent", "", "", "", "", "", ""],
        [f"导入预览期限-{stamp}", "white", "", "", "2026/13/45", "", "", "", ""],
        [f"导入预览类型-{stamp}", "white", "", "施工", "", "", "", "", ""],
        [f"导入预览价格-{stamp}", "white", "", "", "", "", "", "", "abc"],
        [title_ok_second, "white", "", "论文+设计", "", "", "", "", ""],
    ])
    resp = _import_orders(admin_client, content, dry_run=1)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is True
    assert body["ok"] is False
    assert body["created"] == 0
    assert body["valid"] == 2
    assert body["total"] == 8
    assert [item["row"] for item in body["failed"]] == [3, 4, 5, 6, 7, 8]
    errors = {item["row"]: item["error"] for item in body["failed"]}
    assert "标题不能为空" in errors[3]
    assert "品质代码" in errors[4]
    assert "代理用户名" in errors[5]
    assert "期限" in errors[6]
    assert "项目类型" in errors[7]
    assert "真实价" in errors[8]
    assert body["preview_truncated"] is False
    assert [item["row"] for item in body["preview"]] == [2, 9]

    first = body["preview"][0]
    assert first["title"] == title_ok
    assert first["quality_code"] == "white"
    assert first["quality_name"] == "白色"
    assert first["agent_username"] == "agent1"
    assert first["project_type"] == "program"
    assert first["deadline"] == "2026-12-31"
    assert first["tech_stack"] == "Vue 3"
    assert first["customer_info"] == "张三 13800000000"
    assert first["remark"] == "备注一"
    assert first["owner_price"] == 900.0
    assert body["preview"][1]["project_type"] == "thesis_program"

    _fresh(db)
    assert db.query(Order).filter(Order.title.in_([title_ok, title_ok_second])).count() == 0


def test_import_orders_creates_rows(admin_client, db):
    stamp = uuid4().hex[:8]
    title_one = f"导入建单A-{stamp}"
    title_two = f"导入建单B-{stamp}"
    content = _xlsx(ORDER_IMPORT_HEADERS, [
        [title_one, "white", "agent1", "程序设计", "2026-12-31", "Vue 3", "李同学 13900000000", "备注", 880],
        [f"导入建单坏行-{stamp}", "不存在", "", "", "", "", "", "", ""],
        [title_two, "green", "", "", "", "", "", "", ""],
    ])
    created_ids: list[str] = []
    try:
        resp = _import_orders(admin_client, content)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        created_ids = body["orders"]
        assert body["dry_run"] is False
        assert body["created"] == 2
        assert body["total"] == 3
        assert [item["row"] for item in body["failed"]] == [3]
        assert len(created_ids) == 2

        _fresh(db)
        admin_id = db.query(User.id).filter(User.username == "admin").scalar()
        agent_id = db.query(User.id).filter(User.username == "agent1").scalar()
        orders = {
            order.title: order
            for order in db.query(Order).filter(Order.id.in_(created_ids)).all()
        }
        assert set(orders) == {title_one, title_two}

        first = orders[title_one]
        assert first.created_by == admin_id
        assert first.agent_user_id == agent_id
        assert first.project_type == "program"
        assert first.category == "code"  # 遗留列按项目类型推导
        assert first.deadline == date(2026, 12, 31)
        assert first.tech_stack == "Vue 3"
        assert first.customer_info == "李同学 13900000000"
        assert first.owner_price == Decimal("880.00")
        assert first.status == "pending"
        # 单号由 next_order_no 生成，形如 YYMMDD-NNN
        assert "-" in first.id

        second = orders[title_two]
        assert second.agent_user_id is None
        assert second.project_type == "thesis"
        assert second.owner_price != Decimal("880.00")
    finally:
        _delete_orders(db, created_ids)


def test_import_orders_staff_cannot_override_owner_price(staff_client, db):
    stamp = uuid4().hex[:8]
    title = f"导入协助者-{stamp}"
    content = _xlsx(ORDER_IMPORT_HEADERS, [
        [title, "white", "", "", "", "", "", "", 999999],
    ])
    created_ids: list[str] = []
    try:
        resp = _import_orders(staff_client, content)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        created_ids = body["orders"]
        assert body["created"] == 1
        assert body["failed"] == []

        _fresh(db)
        staff_id = db.query(User.id).filter(User.username == "staff1").scalar()
        order = db.query(Order).filter(Order.id == created_ids[0]).one()
        assert order.created_by == staff_id
        # 非管理员不能通过 Excel 指定真实价，仍按品质公式计价
        assert order.owner_price != Decimal("999999.00")
    finally:
        _delete_orders(db, created_ids)


def test_import_orders_rejects_bad_files(admin_client):
    valid = _xlsx(ORDER_IMPORT_HEADERS, [["文件校验测试", "white", "", "", "", "", "", "", ""]])

    resp = _import_orders(admin_client, valid, filename="orders.csv")
    assert resp.status_code == 400
    assert "仅支持 .xlsx" in resp.text

    resp = _import_orders(admin_client, b"not an xlsx file", filename="orders.xlsx")
    assert resp.status_code == 400
    assert "不是有效的 xlsx" in resp.text

    resp = _import_orders(admin_client, b"", filename="orders.xlsx")
    assert resp.status_code == 400
    assert "文件内容为空" in resp.text

    resp = _import_orders(admin_client, _xlsx(["标题"], [["只有标题"]]), filename="orders.xlsx")
    assert resp.status_code == 400
    assert "表头缺少必需列" in resp.text
    assert "品质代码" in resp.text

    resp = _import_orders(admin_client, b"0" * (excel_io.MAX_UPLOAD_BYTES + 1), filename="orders.xlsx")
    assert resp.status_code == 413
    assert "10MB" in resp.text


def test_agent_cannot_use_excel_endpoints(agent_client):
    assert agent_client.get("/api/excel/orders/export").status_code == 403
    assert agent_client.get("/api/excel/customers/export").status_code == 403
    content = _xlsx(ORDER_IMPORT_HEADERS, [["代理越权测试", "white", "", "", "", "", "", "", ""]])
    assert _import_orders(agent_client, content).status_code == 403


# ============================== 客户导出/导入 ==============================

def test_export_customers_headers_and_formula_guard(admin_client, db):
    stamp = uuid4().hex[:8]
    formula_name = f"=1+1-{stamp}"
    resp = admin_client.post(
        "/api/customers",
        json={"name": formula_name, "contact": "13800000000", "school": "某某大学", "source": "线下", "note": "备注"},
    )
    assert resp.status_code == 200, resp.text
    customer_id = resp.json()["id"]
    try:
        export = admin_client.get("/api/excel/customers/export")
        assert export.status_code == 200, export.text
        assert export.headers["content-type"].startswith(excel_io.XLSX_MEDIA_TYPE)
        rows = _sheet(export.content)
        assert [str(value) for value in rows[0]] == excel_io.CUSTOMER_EXPORT_HEADERS
        index = _index(rows)
        row = _find(rows, "客户名称", "'" + formula_name)
        assert row[index["联系方式"]] == "13800000000"
        assert row[index["学校专业"]] == "某某大学"
        assert row[index["来源渠道"]] == "线下"
        assert row[index["归属用户"]] == "admin"
    finally:
        db.query(Customer).filter(Customer.id == customer_id).delete(synchronize_session=False)
        db.commit()


def test_import_customers_dry_run_and_dedup(admin_client, db):
    stamp = uuid4().hex[:8]
    existing_name = f"客户已存在-{stamp}"
    created_name = f"客户新建-{stamp}"
    dup_name = f"客户文件内重复-{stamp}"
    resp = admin_client.post("/api/customers", json={"name": existing_name, "contact": "13700000000"})
    assert resp.status_code == 200, resp.text

    content = _xlsx(CUSTOMER_IMPORT_HEADERS, [
        [created_name, "13900000000", "某大学 计算机", "转介绍", "备注", "agent1"],
        [existing_name, "", "", "", "", ""],
        ["", "13600000000", "", "", "", ""],
        [dup_name, "", "", "", "", ""],
        [dup_name, "", "", "", "", ""],
        [f"客户归属错误-{stamp}", "", "", "", "", "ghost-user"],
    ])
    try:
        preview = _import_customers(admin_client, content, dry_run=1)
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["dry_run"] is True
        assert body["created"] == 0
        assert body["valid"] == 2
        assert body["total"] == 6
        assert [item["row"] for item in body["failed"]] == [3, 4, 6, 7]
        assert [item["row"] for item in body["preview"]] == [2, 5]
        assert body["preview"][0]["owner_username"] == "agent1"
        assert body["preview"][0]["contact"] == "13900000000"
        assert body["preview"][1]["owner_username"] == "admin"

        _fresh(db)
        assert db.query(Customer).filter(Customer.name.in_([created_name, dup_name])).count() == 0

        resp = _import_customers(admin_client, content)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dry_run"] is False
        assert body["created"] == 2
        assert [item["row"] for item in body["failed"]] == [3, 4, 6, 7]

        _fresh(db)
        admin_id = db.query(User.id).filter(User.username == "admin").scalar()
        agent_id = db.query(User.id).filter(User.username == "agent1").scalar()
        customers = {
            customer.name: customer
            for customer in db.query(Customer)
            .filter(Customer.name.in_([created_name, dup_name]))
            .all()
        }
        assert customers[created_name].owner_id == agent_id
        assert customers[created_name].contact == "13900000000"
        assert customers[dup_name].owner_id == admin_id

        again = _import_customers(admin_client, content)
        assert again.status_code == 200, again.text
        body = again.json()
        assert body["created"] == 0
        assert [item["row"] for item in body["failed"]] == [2, 3, 4, 5, 6, 7]
    finally:
        db.query(Customer).filter(
            Customer.name.in_([existing_name, created_name, dup_name])
        ).delete(synchronize_session=False)
        db.commit()


# ============================== 服务层纯函数 ==============================

def test_read_sheet_size_and_row_limits():
    with pytest.raises(ExcelError, match="10MB"):
        excel_io.read_sheet(b"0" * (excel_io.MAX_UPLOAD_BYTES + 1), required=("标题",))

    rows = [[f"批量-{index}", "white"] for index in range(excel_io.MAX_IMPORT_ROWS + 1)]
    content = _xlsx(["标题", "品质代码"], rows)
    with pytest.raises(ExcelError, match="2000"):
        excel_io.read_sheet(content, required=("标题", "品质代码"))


def test_read_sheet_header_and_empty_checks():
    with pytest.raises(ExcelError, match="缺少必需列"):
        excel_io.read_sheet(_xlsx(["标题"], [["只有标题"]]), required=("标题", "品质代码"))
    with pytest.raises(ExcelError, match="没有可导入的数据行"):
        excel_io.read_sheet(_xlsx(["标题", "品质代码"], []), required=("标题", "品质代码"))
    with pytest.raises(ExcelError, match="不是有效的 xlsx"):
        excel_io.read_sheet(b"not an xlsx", required=("标题",))
    with pytest.raises(ExcelError, match="文件内容为空"):
        excel_io.read_sheet(b"", required=("标题",))


def test_read_sheet_aliases_and_blank_rows():
    content = _xlsx(["姓名", "owner_username"], [["张三", "agent1"], ["", ""], ["李四", ""]])
    headers, rows = excel_io.read_sheet(
        content, required=("客户名称",), aliases=excel_io.CUSTOMER_IMPORT_ALIASES
    )
    assert headers == ["姓名", "owner_username"]
    assert [row_no for row_no, _ in rows] == [2, 4]
    assert rows[0][1] == {"客户名称": "张三", "归属用户": "agent1"}
    assert rows[1][1]["客户名称"] == "李四"


def test_safe_cell_formula_guard():
    assert excel_io.safe_cell("=1+1") == "'=1+1"
    assert excel_io.safe_cell("+8613800000000") == "'+8613800000000"
    assert excel_io.safe_cell("-2") == "'-2"
    assert excel_io.safe_cell("@name") == "'@name"
    assert excel_io.safe_cell(12.5) == 12.5
    assert excel_io.safe_cell(None) == ""
    assert excel_io.safe_cell("正常文本") == "正常文本"
    assert excel_io.safe_cell("坏\x00字符") == "坏字符"


def test_parse_decimal_and_date():
    assert excel_io.parse_decimal("￥1,200.50") == Decimal("1200.50")
    assert excel_io.parse_decimal(800) == Decimal("800.00")
    assert excel_io.parse_decimal(None) is None
    with pytest.raises(ValueError, match="必须是数字"):
        excel_io.parse_decimal("abc", field="真实价")
    with pytest.raises(ValueError, match="不能小于 0"):
        excel_io.parse_decimal(-1)

    assert excel_io.parse_date(date(2026, 1, 2)) == date(2026, 1, 2)
    assert excel_io.parse_date("2026/1/2") == date(2026, 1, 2)
    assert excel_io.parse_date("20260102") == date(2026, 1, 2)
    assert excel_io.parse_date("") is None
    with pytest.raises(ValueError, match="期限"):
        excel_io.parse_date("2026-13-01", field="期限")
