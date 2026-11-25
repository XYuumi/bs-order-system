from __future__ import annotations

from helpers import ADMIN_PASSWORD


def test_create_list_and_duplicate(admin_client, order_factory):
    order = order_factory("订单创建与列表测试")
    assert order["id"].startswith("26")
    listed = admin_client.get("/api/orders", params={"keyword": "订单创建与列表测试"}).json()
    assert listed["total"] >= 1
    dup = admin_client.post("/api/orders/check-duplicate", json={"title": "订单创建与列表测试"})
    assert dup.status_code == 200
    assert dup.json()["duplicates"]


def test_whitespace_title_rejected(admin_client):
    resp = admin_client.post("/api/orders", json={"title": "  ", "quality_code": "white", "category": "code"})
    assert resp.status_code == 400


def test_status_machine_is_enforced(admin_client, order_factory):
    order = order_factory("状态机测试订单")
    oid = order["id"]
    invalid = admin_client.post(f"/api/orders/{oid}/status", json={"status": "not-a-status"})
    assert invalid.status_code == 422
    # 管理员可直接修正任意状态，不受流程图限制。
    done = admin_client.post(f"/api/orders/{oid}/status", json={"status": "completed"})
    assert done.status_code == 200, done.text
    assert done.json()["order"]["completed_at"] is not None
    back = admin_client.post(f"/api/orders/{oid}/status", json={"status": "in_progress"})
    assert back.status_code == 200, back.text
    assert back.json()["order"]["completed_at"] is None
    again = admin_client.post(f"/api/orders/{oid}/status", json={"status": "completed"})
    assert again.status_code == 200


def test_cancelled_order_is_terminal(admin_client, order_factory):
    order = order_factory("取消终态测试订单")
    oid = order["id"]
    cancelled = admin_client.post(f"/api/orders/{oid}/status", json={"status": "cancelled"})
    assert cancelled.status_code == 200, cancelled.text
    # 已取消不允许恢复：管理员也不例外，避免取消单重新进入统计/交付流程。
    restore = admin_client.post(f"/api/orders/{oid}/status", json={"status": "pending"})
    assert restore.status_code == 403, restore.text
    assert "已取消订单" in restore.json()["detail"]
    detail = admin_client.get(f"/api/orders/{oid}").json()["order"]
    assert detail["status"] == "cancelled"
    assert detail["allowed_statuses"] == []
    batch = admin_client.post("/api/orders/batch-status", json={"ids": [oid], "status": "pending"})
    assert batch.status_code == 200, batch.text
    assert batch.json()["changed"] == 0
    assert batch.json()["skipped"] == 1
    assert "已取消订单" in batch.json()["results"][0]["reason"]


def test_clearable_fields(admin_client, order_factory):
    order = order_factory("可清空字段测试", tech_stack="SpringBoot", remark="初始备注")
    oid = order["id"]
    resp = admin_client.patch(f"/api/orders/{oid}", json={
        "tech_stack": None,
        "customer_info": None,
        "remark": None,
    })
    assert resp.status_code == 200, resp.text
    detail = admin_client.get(f"/api/orders/{oid}").json()["order"]
    assert detail["tech_stack"] is None
    assert detail["customer_info"] is None
    assert detail["remark"] is None


def test_batch_status(admin_client, order_factory):
    one = order_factory("批量状态一")
    two = order_factory("批量状态二")
    resp = admin_client.post("/api/orders/batch-status", json={
        "ids": [one["id"], two["id"]], "status": "in_progress",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["changed"] == 2
    assert all(r["ok"] for r in data["results"])


def test_export_csv_escapes_formula(admin_client, order_factory):
    order_factory("=2+2")
    resp = admin_client.get("/api/orders/export")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "'=2+2" in resp.text


def test_trash_and_restore(admin_client, order_factory):
    order = order_factory("回收站测试")
    oid = order["id"]
    resp = admin_client.delete(f"/api/orders/{oid}", headers={"X-Confirm-Password": ADMIN_PASSWORD})
    assert resp.status_code == 200
    trash = admin_client.get("/api/orders/trash/list").json()
    assert any(x["id"] == oid for x in trash["items"])
    restored = admin_client.post(f"/api/orders/{oid}/restore")
    assert restored.status_code == 200


def test_agent_create_and_price_hidden(agent_client, admin_client):
    resp = agent_client.post("/api/orders", json={"title": "代理建单价格隐藏", "quality_code": "blue", "category": "code"})
    assert resp.status_code == 200
    oid = resp.json()["order"]["id"]
    try:
        detail = agent_client.get(f"/api/orders/{oid}").json()["order"]
        assert "agent_price" not in detail  # 写手价是内部成本，代理不可见
        assert detail["owner_price"] > 0    # 代理见自己的成交价（蓝色 ×3）
    finally:
        admin_client.delete(f"/api/orders/{oid}", headers={"X-Confirm-Password": ADMIN_PASSWORD})
