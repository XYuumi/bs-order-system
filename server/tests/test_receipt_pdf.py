from __future__ import annotations

import hashlib
import hmac
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app.config import JWT_SECRET
from app.main import app
from app.models import Order, OrderFile
from app.services.receipt_pdf import (
    format_size, receipt_data, render_receipt_pdf, verification_code,
)
from helpers import AGENT_PASSWORD


def _expected_code(order_id: str, accepted_at) -> str:
    """独立复算验证码，避免直接信任被测实现。"""
    stamp = accepted_at.strftime("%Y-%m-%d %H:%M:%S") if accepted_at else ""
    digest = hmac.new(
        JWT_SECRET.encode(), f"{order_id}{stamp}".encode(), hashlib.sha256
    ).hexdigest()
    return digest[:12].upper()


@pytest.fixture(scope="module")
def agent2_client():
    client = TestClient(app)
    resp = client.post("/api/auth/login", json={"username": "agent2", "password": AGENT_PASSWORD})
    assert resp.status_code == 200, resp.text
    return client


def test_verification_code_is_hmac_prefix():
    code = verification_code("260101-001", None)
    assert code == _expected_code("260101-001", None)
    assert len(code) == 12
    assert code == code.upper()
    assert all(ch in "0123456789ABCDEF" for ch in code)

    from datetime import datetime

    accepted = datetime(2026, 5, 20, 10, 30, 15)
    accepted_code = verification_code("260101-001", accepted)
    assert accepted_code == _expected_code("260101-001", accepted)
    assert accepted_code != code
    assert verification_code("260101-002", accepted) != accepted_code


def test_format_size_units():
    assert format_size(0) == "0 B"
    assert format_size(None) == "0 B"
    assert format_size(512) == "512 B"
    assert format_size(2048) == "2.0 KB"
    assert format_size(5 * 1024 * 1024) == "5.0 MB"
    assert format_size(3 * 1024**3) == "3.0 GB"


def test_receipt_data_price_visibility_by_role(order_factory, db):
    """验收单上的成交价只给付款方（代理）与管理员看；写手价、倍率任何角色都不出现。"""
    order = order_factory(
        "验收单价格视野",
        quality="blue",
        category="code",
        agent_username="agent1",
        customer_info="李同学 13800000000",
    )
    oid = order["id"]
    db.rollback()
    record = db.get(Order, oid)

    admin_data = receipt_data(record, role="admin")
    assert admin_data["owner_price"] == float(record.owner_price)

    agent_data = receipt_data(record, role="agent")
    assert agent_data["owner_price"] == float(record.owner_price)  # 代理是付款方，见成交价

    staff_data = receipt_data(record, role="staff")
    assert "owner_price" not in staff_data                         # 写手不见成交价

    for data in (admin_data, agent_data, staff_data):
        assert "agent_price" not in data and "multiplier" not in data

    assert admin_data["order_id"] == oid
    assert admin_data["quality"] == "蓝色"
    assert admin_data["customer_info"] == "李同学 13800000000"
    assert admin_data["verification_code"] == _expected_code(oid, None)
    assert [item["label"] for item in admin_data["timeline"]] == [
        "下单时间", "开始制作", "完成制作", "客户验收",
    ]


def test_receipt_data_lists_files(admin_client, order_factory, db):
    order = order_factory("验收单文件清单", agent_username="agent1")
    oid = order["id"]
    upload = admin_client.post(
        f"/api/orders/{oid}/files",
        files={"file": ("需求说明书.pdf", b"%PDF-1.4 fake", "application/pdf")},  # 13 字节
        data={"category": "doc"},
    )
    assert upload.status_code == 200, upload.text

    db.expire_all()
    files = (
        db.query(OrderFile)
        .filter(OrderFile.order_id == oid, OrderFile.is_deleted.is_(False))
        .all()
    )
    data = receipt_data(db.get(Order, oid), role="admin", files=files)
    assert len(data["files"]) == 1
    item = data["files"][0]
    assert item["name"] == "需求说明书.pdf"
    assert item["category"] == "文档"
    assert item["size"] == 13
    assert item["size_text"] == "13 B"


def test_render_receipt_pdf_bytes(order_factory, db):
    order = order_factory("验收单 PDF 生成", agent_username="agent1")
    db.expire_all()
    record = db.get(Order, order["id"])

    admin_pdf = render_receipt_pdf(record, role="admin")
    assert admin_pdf.startswith(b"%PDF")
    assert admin_pdf.rstrip().endswith(b"%%EOF")
    assert len(admin_pdf) > 2000

    agent_pdf = render_receipt_pdf(record, role="agent", site_name="测试站点")
    assert agent_pdf.startswith(b"%PDF")
    assert agent_pdf.rstrip().endswith(b"%%EOF")


def test_receipt_pdf_endpoint(admin_client, order_factory):
    order = order_factory("验收单接口测试", agent_username="agent1", customer_info="王同学 13900000000")
    oid = order["id"]

    resp = admin_client.get(f"/api/orders/{oid}/receipt.pdf")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/pdf")
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert f"filename*=UTF-8''{quote(f'验收单-{oid}.pdf')}" in disposition
    assert resp.content.startswith(b"%PDF")
    assert resp.content.rstrip().endswith(b"%%EOF")


def test_receipt_pdf_access_control(admin_client, staff_client, agent_client, agent2_client, order_factory):
    order = order_factory("验收单越权测试", agent_username="agent1")
    oid = order["id"]
    url = f"/api/orders/{oid}/receipt.pdf"

    own = agent_client.get(url)
    assert own.status_code == 200, own.text
    staff = staff_client.get(url)
    assert staff.status_code == 200, staff.text
    denied = agent2_client.get(url)
    assert denied.status_code == 403
    assert denied.json()["detail"] == "无权导出该订单的验收单"

    anonymous = TestClient(app)
    assert anonymous.get(url).status_code == 401
    assert admin_client.get("/api/orders/not-exist-000/receipt.pdf").status_code == 404


def test_receipt_pdf_after_customer_accept(admin_client, order_factory, db):
    order = order_factory("验收单客户验收", agent_username="agent1")
    oid = order["id"]
    url = f"/api/orders/{oid}/receipt.pdf"

    before = admin_client.get(url)
    assert before.status_code == 200
    assert receipt_data(db.get(Order, oid), role="admin")["accepted"] is False

    token = admin_client.get(f"/api/orders/{oid}/deliver-link").json()["token"]
    public = TestClient(app)
    accepted = public.post(f"/api/deliver/{token}/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["already"] is False

    after = admin_client.get(url)
    assert after.status_code == 200
    assert after.content != before.content

    # MySQL 默认 REPEATABLE READ：先结束当前事务快照，才能读到交付页新提交的验收时间
    db.rollback()
    record = db.get(Order, oid)
    assert record.customer_accepted_at is not None
    assert record.customer_accepted_ip
    data = receipt_data(record, role="admin")
    assert data["accepted"] is True
    assert data["accepted_at"] == record.customer_accepted_at
    assert data["accepted_ip"] == record.customer_accepted_ip
    assert data["verification_code"] == _expected_code(oid, record.customer_accepted_at)
    assert data["verification_code"] != _expected_code(oid, None)
    accepted_entry = [item for item in data["timeline"] if item["label"] == "客户验收"][0]
    assert accepted_entry["time"] == record.customer_accepted_at
    assert record.customer_accepted_ip in accepted_entry["note"]
