"""原始需求资料（v1.24.2）：上传解析、创建/编辑持久化、生成接入与 AI 可见性。"""
from __future__ import annotations

import io
import json

from app.routers import orders as orders_router
from app.services.docgen.template import build_template_doc


def _no_rate_limit(monkeypatch):
    monkeypatch.setattr(orders_router, "rate_limit", lambda *a, **k: None)


# ---------- 提取与解析接口 ----------

def test_parse_txt_and_gbk(admin_client):
    utf8 = admin_client.post(
        "/api/orders/parse-requirement-file",
        files={"file": ("需求.txt", "系统要有用户管理\n支持导出报表".encode("utf-8"), "text/plain")},
    )
    assert utf8.status_code == 200, utf8.text
    body = utf8.json()
    assert body["format_matched"] is False
    assert "导出报表" in body["text"]

    gbk = admin_client.post(
        "/api/orders/parse-requirement-file",
        files={"file": ("需求.txt", "客户要求积分商城功能".encode("gbk"), "text/plain")},
    )
    assert gbk.status_code == 200, gbk.text
    assert "积分商城" in gbk.json()["text"]


def test_parse_docx_includes_tables(admin_client):
    from docx import Document

    doc = Document()
    doc.add_paragraph("系统功能需求：")
    table = doc.add_table(rows=2, cols=3)
    table.cell(0, 0).text = "模块"
    table.cell(0, 1).text = "说明"
    table.cell(1, 0).text = "订单管理"
    table.cell(1, 1).text = "增删改查"
    buf = io.BytesIO()
    doc.save(buf)

    resp = admin_client.post(
        "/api/orders/parse-requirement-file",
        files={"file": ("需求书.docx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert resp.status_code == 200, resp.text
    text = resp.json()["text"]
    assert "系统功能需求" in text
    assert "订单管理 | 增删改查" in text


def test_parse_pdf(admin_client):
    from reportlab.pdfgen import canvas as pdf_canvas

    buf = io.BytesIO()
    c = pdf_canvas.Canvas(buf)
    c.setFont("Helvetica", 12)
    c.drawString(72, 720, "Customer needs: login, orders and reports export")
    c.save()

    resp = admin_client.post(
        "/api/orders/parse-requirement-file",
        files={"file": ("需求.pdf", buf.getvalue(), "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["format_matched"] is False
    assert "orders and reports" in body["text"]


def test_parse_json_format_detection(admin_client):
    our_doc = build_template_doc("测试题目", None)
    matched = admin_client.post(
        "/api/orders/parse-requirement-file",
        files={"file": ("doc.json", json.dumps(our_doc, ensure_ascii=False).encode("utf-8"), "application/json")},
    )
    assert matched.status_code == 200, matched.text
    assert matched.json()["format_matched"] is True

    not_ours = admin_client.post(
        "/api/orders/parse-requirement-file",
        files={"file": ("doc.json", b'{"foo": "bar"}', "application/json")},
    )
    assert not_ours.status_code == 200
    assert not_ours.json()["format_matched"] is False


def test_parse_rejects_bad_input(admin_client):
    bad_ext = admin_client.post(
        "/api/orders/parse-requirement-file",
        files={"file": ("virus.exe", b"MZ...", "application/octet-stream")},
    )
    assert bad_ext.status_code == 400

    empty = admin_client.post(
        "/api/orders/parse-requirement-file",
        files={"file": ("空.txt", b"   ", "text/plain")},
    )
    assert empty.status_code == 400

    anonymous = admin_client.post("/api/orders/parse-requirement-file")
    assert anonymous.status_code in (400, 422)


def test_parse_requires_login():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/orders/parse-requirement-file",
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 401


# ---------- 创建 / 编辑 / 可见性 ----------

def test_create_persists_source_and_notes(admin_client, staff_client, agent_client, order_factory):
    order = order_factory(
        "带原始需求的订单",
        agent_username="agent1",
        source_requirement="客户原文：需要宠物档案、预约挂号、医生排班",
        requirement_notes="要微信小程序端；管理员能导出报表",
    )
    oid = order["id"]

    staff_view = staff_client.get(f"/api/orders/{oid}").json()["order"]
    assert "宠物档案" in staff_view["source_requirement"]
    assert "微信小程序" in staff_view["requirement_notes"]

    admin_view = admin_client.get(f"/api/orders/{oid}").json()["order"]
    assert "source_requirement" in admin_view

    # 代理视图不下发原始需求资料
    agent_view = agent_client.get(f"/api/orders/{oid}").json()["order"]
    assert "source_requirement" not in agent_view
    assert "requirement_notes" not in agent_view

    # 编辑接口可改，且日志不落全文
    resp = admin_client.patch(
        f"/api/orders/{oid}",
        json={"requirement_notes": "改为：H5 端即可"},
    )
    assert resp.status_code == 200, resp.text
    assert "H5 端" in resp.json()["order"]["requirement_notes"]


# ---------- 生成接入 ----------

def test_generate_imports_matched_json_directly(admin_client, order_factory, monkeypatch):
    _no_rate_limit(monkeypatch)
    doc = build_template_doc("直导测试", None)
    doc["chapters"]["scope"]["items"] = ["前台：会员端", "后台：运营端"]
    order = order_factory("直导测试订单", source_requirement=json.dumps(doc, ensure_ascii=False))

    def boom(*a, **k):  # noqa: ANN001
        raise AssertionError("格式匹配时不应调用 AI")

    monkeypatch.setattr(orders_router, "generate_by_ai", boom)
    resp = admin_client.post(f"/api/orders/{order['id']}/requirement/generate", json={"mode": "ai"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "manual"
    assert "直接导入" in (body["note"] or "")
    assert body["document"]["chapters"]["scope"]["items"] == ["前台：会员端", "后台：运营端"]


def test_generate_passes_source_and_notes_to_ai(admin_client, order_factory, monkeypatch):
    _no_rate_limit(monkeypatch)
    order = order_factory(
        "AI基准传递订单",
        source_requirement="客户原文：宠物医院，含疫苗提醒",
        requirement_notes="要医生端排班",
    )

    captured = {}

    def fake_generate(db, title, tech_stack, *, order_id=None, user_id=None, source_text=None, notes=None):
        captured.update(title=title, tech=tech_stack, source=source_text, notes=notes)
        return build_template_doc(title, tech_stack)

    monkeypatch.setattr(orders_router, "ai_available", lambda db: True)
    monkeypatch.setattr(orders_router, "generate_by_ai", fake_generate)

    resp = admin_client.post(f"/api/orders/{order['id']}/requirement/generate", json={"mode": "ai"})
    assert resp.status_code == 200, resp.text
    assert "疫苗提醒" in captured["source"]
    assert "排班" in captured["notes"]
    assert captured["tech"] is None  # 未指定技术栈原样传给 AI 决策


def test_generate_writes_back_tech_label(admin_client, order_factory, monkeypatch):
    _no_rate_limit(monkeypatch)
    order = order_factory("技术栈回写订单")  # 不传 tech_stack

    doc = build_template_doc("技术栈回写订单", None)
    doc["chapters"]["tech"]["stack_table"] = [
        ["后端框架", "Django 5.2", "x"],
        ["前端技术", "Vue 3", "x"],
        ["数据库", "MySQL 8.0", "x"],
    ]

    monkeypatch.setattr(orders_router, "ai_available", lambda db: True)
    monkeypatch.setattr(orders_router, "generate_by_ai", lambda *a, **k: doc)

    resp = admin_client.post(f"/api/orders/{order['id']}/requirement/generate", json={"mode": "ai"})
    assert resp.status_code == 200, resp.text
    view = admin_client.get(f"/api/orders/{order['id']}").json()["order"]
    assert view["tech_stack"] == "Django 5.2 + Vue 3 + MySQL 8.0"


def test_template_mode_notes_missing_ai(admin_client, order_factory, monkeypatch):
    _no_rate_limit(monkeypatch)
    order = order_factory("模板提示订单", requirement_notes="要点若干")
    monkeypatch.setattr(orders_router, "ai_available", lambda db: False)
    resp = admin_client.post(f"/api/orders/{order['id']}/requirement/generate", json={"mode": "auto"})
    assert resp.status_code == 200, resp.text
    assert "未使用原始需求资料" in (resp.json()["note"] or "")
