"""价格隔离与越权口子的回归（中间商模式）。

价格视野：管理员见成交价 + 写手价；写手只见写手价；代理只见成交价（写手价是内部成本）。
order_view 已按角色裁剪，这里覆盖它之外的出口——日志旁路、验收单 / 收款凭证、公开报价单，
以及会改动价格的越权口子（改交期 / 改品质）和超长需求书的静默截断。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.constants import SOURCE_REQUIREMENT_MAX_CHARS
from app.main import app
from app.models import Order
from app.services.receipt_svc import receipt_amount


def _log_detail(client, oid: str, action: str) -> dict:
    detail = client.get(f"/api/orders/{oid}").json()["order"]
    return next(lg["detail"] for lg in detail["logs"] if lg["action"] == action)


def test_quote_page_shows_customer_price_only(admin_client, agent_client):
    """公开报价单面向客户：给客户价（成交价基准），不下发写手价与倍率。"""
    token = admin_client.get("/api/quote/link").json()["token"]
    items = TestClient(app).get(f"/api/quote/{token}").json()["qualities"]
    assert items
    for item in items:
        assert item["price"] > 0
        assert not {"agent_price", "owner_price", "multiplier"} & set(item)
    # 与代理看到的成交价是同一套数
    agent_prices = {q["code"]: q["owner_price"] for q in agent_client.get("/api/qualities").json()["qualities"]}
    assert {item["code"]: item["price"] for item in items} == agent_prices


def test_order_detail_logs_hide_prices_by_role(admin_client, staff_client, agent_client, order_factory):
    """建单日志的审计原文里存着两个价格：写手不见成交价，代理不见写手价，管理员见全部。"""
    oid = order_factory("日志价格脱敏", agent_username="agent1")["id"]
    assert _log_detail(admin_client, oid, "order_create")["agent_price"] > 0

    staff_detail = _log_detail(staff_client, oid, "order_create")
    assert "owner_price" not in staff_detail and staff_detail["agent_price"] > 0

    agent_detail = _log_detail(agent_client, oid, "order_create")
    assert "agent_price" not in agent_detail and agent_detail["owner_price"] > 0


def test_receipts_expose_deal_price_to_payer_only(
    admin_client, staff_client, agent_client, order_factory, db
):
    """收款凭证含成交价：仅管理员与该单代理可下载，金额是成交价而不是写手价；验收单写手可看。"""
    order = order_factory("凭证价格视野", quality="blue", agent_username="agent1")
    oid = order["id"]
    url = f"/api/orders/{oid}/receipt"
    assert agent_client.get(url).status_code == 200
    assert admin_client.get(url).status_code == 200
    assert staff_client.get(url).status_code == 403
    assert staff_client.get(f"{url}.pdf").status_code == 200

    db.rollback()
    record = db.get(Order, oid)
    assert record.owner_price != record.agent_price  # 蓝色 ×3：成交价 900，写手价 150
    assert receipt_amount(record) == float(record.owner_price)


def test_order_update_deadline_and_quality_are_admin_only(
    admin_client, staff_client, agent_client, order_factory
):
    """交期与品质（决定两个价格）仅管理员可改；写手/代理原样回传不受影响（编辑弹窗总是带这两个字段）。"""
    order = order_factory("改单越权口子", quality="white", agent_username="agent1", deadline="2030-01-15")
    oid = order["id"]
    # 编辑弹窗总是把交期、品质一起回传：原样回传不算越权，照常可以改其他字段
    unchanged = {"quality_code": "white", "deadline": "2030-01-15"}
    for index, client in enumerate((agent_client, staff_client)):
        same = client.patch(f"/api/orders/{oid}", json={**unchanged, "remark": f"只改备注 {index}"})
        assert same.status_code == 200, same.text

    for client in (staff_client, agent_client):
        denied_deadline = client.patch(f"/api/orders/{oid}", json={"deadline": "2030-02-01"})
        assert denied_deadline.status_code == 403, denied_deadline.text
        denied_quality = client.patch(f"/api/orders/{oid}", json={"quality_code": "red"})
        assert denied_quality.status_code == 403, denied_quality.text
    detail = admin_client.get(f"/api/orders/{oid}").json()["order"]
    assert detail["quality"]["code"] == "white"
    assert detail["deadline"] == order["deadline"]

    assert admin_client.patch(f"/api/orders/{oid}", json={"quality_code": "red"}).status_code == 200
    assert admin_client.patch(f"/api/orders/{oid}", json={"deadline": "2030-02-01"}).status_code == 200


def test_requirement_upload_rejects_overlong_text(admin_client, staff_client, order_factory):
    """超长需求书直接拒绝并说明上限，不再收下后悄悄截断（网页端与开放 API 一致）。"""
    oid = order_factory("超长需求书")["id"]
    text = "需" * (SOURCE_REQUIREMENT_MAX_CHARS + 1)
    files = {"file": ("需求.txt", text.encode(), "text/plain")}

    web = admin_client.post(f"/api/orders/{oid}/requirement/upload", files=files)
    assert web.status_code == 400, web.text
    assert "过长" in web.json()["detail"]
    assert f"{SOURCE_REQUIREMENT_MAX_CHARS:,}" in web.json()["detail"]

    api_key = staff_client.get("/api/me/api-key").json()["api_key"]
    api = TestClient(app).post(
        f"/api/v1/orders/{oid}/requirement/upload", headers={"X-API-Key": api_key}, files=files,
    )
    assert api.status_code == 400, api.text
    assert "过长" in api.json()["detail"]
