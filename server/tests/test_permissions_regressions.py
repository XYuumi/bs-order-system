from __future__ import annotations

import pytest

from helpers import ADMIN_PASSWORD, AGENT_PASSWORD, STAFF_PASSWORD


@pytest.fixture(autouse=True)
def _clear_rate_limit_between_regressions():
    """回归用例会额外建单，清空进程内限流桶，避免影响后续测试。"""
    from app.ratelimit import _LOCK, _MEMORY

    with _LOCK:
        _MEMORY.clear()
    yield
    with _LOCK:
        _MEMORY.clear()

def _advance(admin_client, oid: str, *statuses: str) -> None:
    for status in statuses:
        resp = admin_client.post(f"/api/orders/{oid}/status", json={"status": status})
        assert resp.status_code == 200, resp.text


def test_staff_cannot_close_or_after_sale(admin_client, staff_client, order_factory):
    order = order_factory("写手越权结单回归")
    oid = order["id"]
    _advance(admin_client, oid, "in_progress", "completed")

    for status in ("closed", "after_sale"):
        resp = staff_client.post(f"/api/orders/{oid}/status", json={"status": status})
        assert resp.status_code == 403, (status, resp.text)
    detail = admin_client.get(f"/api/orders/{oid}").json()["order"]
    assert detail["status"] == "completed"


def test_staff_cannot_change_assignee(admin_client, staff_client, order_factory):
    order = order_factory("写手改派负责人回归")
    oid = order["id"]

    denied = staff_client.patch(f"/api/orders/{oid}", json={"assignee_username": "staff1"})
    assert denied.status_code == 403, denied.text
    assert admin_client.get(f"/api/orders/{oid}").json()["order"]["assignee"] is None

    allowed = admin_client.patch(f"/api/orders/{oid}", json={"assignee_username": "staff1"})
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["order"]["assignee"]["username"] == "staff1"


def test_staff_can_delete_any_order_file_but_agent_cannot(admin_client, staff_client, agent_client, order_factory):
    """写手可管理全部订单的文件（含未分派给自己的订单）；代理不能删除文件。"""
    order = order_factory("文件删除权限")
    oid = order["id"]
    uploaded = admin_client.post(
        f"/api/orders/{oid}/files",
        files={"file": ("guard.txt", b"hello", "text/plain")},
        data={"category": "doc"},
    )
    assert uploaded.status_code == 200, uploaded.text
    file_id = uploaded.json()["file"]["id"]

    denied = agent_client.delete(f"/api/files/{file_id}", headers={"X-Confirm-Password": AGENT_PASSWORD})
    assert denied.status_code == 403, denied.text
    files = admin_client.get(f"/api/orders/{oid}").json()["order"]["files"]
    assert any(f["id"] == file_id for f in files)

    removed = staff_client.delete(f"/api/files/{file_id}", headers={"X-Confirm-Password": STAFF_PASSWORD})
    assert removed.status_code == 200, removed.text
    files = admin_client.get(f"/api/orders/{oid}").json()["order"]["files"]
    assert not any(f["id"] == file_id for f in files)


def test_order_list_exposes_download_permission(admin_client, staff_client, order_factory):
    order = order_factory("列表下载权限标记回归")
    oid = order["id"]

    # 写手可下载全部订单的交付物（含未分派给自己的订单）
    staff_items = staff_client.get("/api/orders?page_size=100").json()["items"]
    staff_item = next(i for i in staff_items if i["id"] == oid)
    assert staff_item["can_download"] is True
    assert staff_item["video"] is None

    admin_items = admin_client.get("/api/orders?page_size=100").json()["items"]
    admin_item = next(i for i in admin_items if i["id"] == oid)
    assert admin_item["can_download"] is True


def test_staff_api_key_cannot_close_order(admin_client, staff_client, order_factory):
    order = order_factory("写手 API Key 越权回归")
    oid = order["id"]
    _advance(admin_client, oid, "in_progress", "completed")

    key_resp = staff_client.get("/api/me/api-key")
    assert key_resp.status_code == 200, key_resp.text
    api_key = key_resp.json()["api_key"]
    denied = staff_client.post(
        f"/api/v1/orders/{oid}/status",
        json={"status": "closed"},
        headers={"X-API-Key": api_key},
    )
    assert denied.status_code == 403, denied.text


def test_create_order_rejects_invalid_owner_price(admin_client, order_factory):
    def create(price: int):
        return admin_client.post(
            "/api/orders",
            json={
                "title": f"真实价校验回归-{price}",
                "quality_code": "white",
                "category": "code",
                "owner_price": price,
            },
            headers={"X-Confirm-Password": ADMIN_PASSWORD},
        )

    negative = create(0)
    assert negative.status_code == 400, negative.text
    below_agent = create(10)
    assert below_agent.status_code == 400, below_agent.text
    assert "代理价" in below_agent.json()["detail"]

    ok = create(300)
    assert ok.status_code == 200, ok.text
    oid = ok.json()["order"]["id"]
    admin_client.delete(f"/api/orders/{oid}", headers={"X-Confirm-Password": ADMIN_PASSWORD})


def test_after_sale_gets_closed_at(admin_client, order_factory):
    order = order_factory("售后补 closed_at 回归")
    oid = order["id"]
    _advance(admin_client, oid, "in_progress", "completed", "after_sale")

    detail = admin_client.get(f"/api/orders/{oid}").json()["order"]
    assert detail["status"] == "after_sale"
    assert detail["closed_at"] is not None


def test_quality_multiplier_is_admin_only(admin_client, staff_client):
    admin_item = admin_client.get("/api/qualities").json()["qualities"][0]
    staff_item = staff_client.get("/api/qualities").json()["qualities"][0]
    assert "multiplier" in admin_item
    assert "multiplier" not in staff_item
    assert "owner_price" not in staff_item
    assert staff_item["agent_price"] > 0


def test_batch_status_counts_deduplicated_ids(admin_client, order_factory):
    order = order_factory("批量去重计数回归")
    oid = order["id"]
    resp = admin_client.post("/api/orders/batch-status", json={
        "ids": [oid, oid],
        "status": "in_progress",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["changed"] == 1
    assert data["total"] == 1
    assert data["skipped"] == 0
    assert data["ignored"] == 1
    assert data["truncated"] is False
