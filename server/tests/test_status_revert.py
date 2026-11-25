from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_rate_limit_between_reverts():
    from app.ratelimit import _LOCK, _MEMORY

    with _LOCK:
        _MEMORY.clear()
    yield
    with _LOCK:
        _MEMORY.clear()


def _assign(admin_client, oid: str, username: str = "staff1") -> None:
    resp = admin_client.patch(f"/api/orders/{oid}", json={"assignee_username": username})
    assert resp.status_code == 200, resp.text


def _advance(admin_client, oid: str, *statuses: str) -> None:
    for status in statuses:
        resp = admin_client.post(f"/api/orders/{oid}/status", json={"status": status})
        assert resp.status_code == 200, resp.text


def _prepare(admin_client, order_factory, title: str, status: str = "in_progress") -> str:
    order = order_factory(title)
    oid = order["id"]
    _assign(admin_client, oid)
    _advance(admin_client, oid, status)
    return oid


def test_admin_can_change_any_status(admin_client, order_factory):
    order = order_factory("管理员任意状态")
    oid = order["id"]

    closed = admin_client.post(f"/api/orders/{oid}/status", json={"status": "closed"})
    assert closed.status_code == 200, closed.text
    assert closed.json()["order"]["closed_at"] is not None

    reopened = admin_client.post(f"/api/orders/{oid}/status", json={"status": "pending"})
    assert reopened.status_code == 200, reopened.text
    detail = reopened.json()["order"]
    assert detail["status"] == "pending"
    assert detail["accepted_at"] is None
    assert detail["completed_at"] is None
    assert detail["closed_at"] is None

    after_sale = admin_client.post(f"/api/orders/{oid}/status", json={"status": "after_sale"})
    assert after_sale.status_code == 200, after_sale.text
    assert after_sale.json()["order"]["closed_at"] is not None


def test_staff_status_permissions(admin_client, staff_client, order_factory):
    pending = order_factory("写手待开始可完成")
    p_oid = pending["id"]
    _assign(admin_client, p_oid)
    direct_done = staff_client.post(f"/api/orders/{p_oid}/status", json={"status": "completed"})
    assert direct_done.status_code == 200, direct_done.text
    assert direct_done.json()["order"]["status"] == "completed"

    running = order_factory("写手制作中权限")
    r_oid = running["id"]
    _assign(admin_client, r_oid)
    _advance(admin_client, r_oid, "in_progress")
    for status in ("pending", "cancelled", "closed", "after_sale"):
        denied = staff_client.post(f"/api/orders/{r_oid}/status", json={"status": status})
        assert denied.status_code == 403, (status, denied.text)
    allowed = staff_client.post(f"/api/orders/{r_oid}/status", json={"status": "completed"})
    assert allowed.status_code == 200, allowed.text

    back_denied = staff_client.post(f"/api/orders/{r_oid}/status", json={"status": "in_progress"})
    assert back_denied.status_code == 403, back_denied.text


def test_revert_request_approve_rolls_back(admin_client, staff_client, order_factory):
    oid = _prepare(admin_client, order_factory, "撤回审批通过")
    detail = staff_client.get(f"/api/orders/{oid}").json()["order"]
    assert detail["status"] == "in_progress"
    assert detail["revert_target"] == "pending"
    assert detail["allowed_statuses"] == ["completed"]
    assert detail["status_revert"] is None

    created = staff_client.post(
        f"/api/orders/{oid}/status-revert",
        json={"to_status": "pending", "reason": "手滑点成了开始制作"},
    )
    assert created.status_code == 200, created.text
    rid = created.json()["request"]["id"]
    assert created.json()["request"]["status"] == "pending"

    duplicate = staff_client.post(
        f"/api/orders/{oid}/status-revert",
        json={"to_status": "pending", "reason": "重复申请"},
    )
    assert duplicate.status_code == 409, duplicate.text

    pending = admin_client.get("/api/status-reverts", params={"status": "pending"}).json()
    assert pending["pending"] >= 1
    assert any(item["id"] == rid for item in pending["items"])

    reviewed = admin_client.post(
        f"/api/status-reverts/{rid}/review", json={"action": "approve", "note": "已核实，同意"}
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["request"]["status"] == "approved"
    assert reviewed.json()["order"]["status"] == "pending"
    after = admin_client.get(f"/api/orders/{oid}").json()["order"]
    assert after["status"] == "pending"
    assert after["accepted_at"] is None
    assert after["status_revert"] is None


def test_revert_request_reject_keeps_status(admin_client, staff_client, order_factory):
    oid = _prepare(admin_client, order_factory, "撤回审批驳回")
    created = staff_client.post(
        f"/api/orders/{oid}/status-revert",
        json={"to_status": "pending", "reason": "误操作"},
    )
    assert created.status_code == 200, created.text
    rid = created.json()["request"]["id"]

    reviewed = admin_client.post(
        f"/api/status-reverts/{rid}/review", json={"action": "reject", "note": "已有交付物，不能回退"}
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["request"]["status"] == "rejected"
    assert reviewed.json()["order"]["status"] == "in_progress"
    detail = admin_client.get(f"/api/orders/{oid}").json()["order"]
    assert detail["status"] == "in_progress"
    assert detail["status_revert"] is None


def test_revert_request_cancel_and_permissions(admin_client, staff_client, order_factory):
    oid = _prepare(admin_client, order_factory, "撤回收回权限")
    created = staff_client.post(
        f"/api/orders/{oid}/status-revert",
        json={"to_status": "pending", "reason": "先申请再撤回"},
    )
    rid = created.json()["request"]["id"]

    admin_apply = admin_client.post(
        f"/api/orders/{oid}/status-revert",
        json={"to_status": "pending", "reason": "管理员无需申请"},
    )
    assert admin_apply.status_code == 400, admin_apply.text

    staff_review = staff_client.post(
        f"/api/status-reverts/{rid}/review", json={"action": "approve"}
    )
    assert staff_review.status_code == 403, staff_review.text

    admin_cancel = admin_client.post(f"/api/status-reverts/{rid}/cancel")
    assert admin_cancel.status_code == 403, admin_cancel.text

    cancelled = staff_client.post(f"/api/status-reverts/{rid}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["request"]["status"] == "cancelled"

    twice = staff_client.post(f"/api/status-reverts/{rid}/cancel")
    assert twice.status_code == 409, twice.text

    approved = admin_client.post(
        f"/api/status-reverts/{rid}/review", json={"action": "approve"}
    )
    assert approved.status_code == 409, approved.text


def test_revert_request_stale_auto_rejects(admin_client, staff_client, order_factory):
    oid = _prepare(admin_client, order_factory, "撤回申请自动失效")
    created = staff_client.post(
        f"/api/orders/{oid}/status-revert",
        json={"to_status": "pending", "reason": "准备回退"},
    )
    rid = created.json()["request"]["id"]

    _advance(admin_client, oid, "completed")
    reviewed = admin_client.post(
        f"/api/status-reverts/{rid}/review", json={"action": "approve"}
    )
    assert reviewed.status_code == 409, reviewed.text
    detail = admin_client.get(f"/api/orders/{oid}").json()["order"]
    assert detail["status"] == "completed"
    assert detail["status_revert"] is None


def test_revert_completed_to_in_progress(admin_client, staff_client, order_factory):
    oid = _prepare(admin_client, order_factory, "已完成撤回制作中", status="completed")
    detail = staff_client.get(f"/api/orders/{oid}").json()["order"]
    assert detail["revert_target"] == "in_progress"
    created = staff_client.post(
        f"/api/orders/{oid}/status-revert",
        json={"to_status": "pending", "reason": "目标错误"},
    )
    assert created.status_code == 400, created.text
    created = staff_client.post(
        f"/api/orders/{oid}/status-revert",
        json={"to_status": "in_progress", "reason": "交付物未完成"},
    )
    assert created.status_code == 200, created.text
    rid = created.json()["request"]["id"]
    reviewed = admin_client.post(
        f"/api/status-reverts/{rid}/review", json={"action": "approve"}
    )
    assert reviewed.status_code == 200, reviewed.text
    after = reviewed.json()["order"]
    assert after["status"] == "in_progress"
    assert after["completed_at"] is None
    assert after["accepted_at"] is not None
