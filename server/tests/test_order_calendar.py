from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient


def test_calendar_filters_by_deadline_and_role(admin_client, agent_client, staff_client, order_factory):
    target = date.today() + timedelta(days=5)
    inside = order_factory(title="日历区间内订单", deadline=target.isoformat())
    order_factory(title="日历区间外订单", deadline=(target + timedelta(days=20)).isoformat())
    order_factory(title="日历无期限订单")
    agent_order = order_factory(
        title="日历代理订单",
        deadline=(target + timedelta(days=1)).isoformat(),
        agent_username="agent1",
    )

    resp = admin_client.get(
        "/api/orders/calendar",
        params={"start": target.isoformat(), "end": (target + timedelta(days=2)).isoformat()},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    ids = {it["id"] for it in data["items"]}
    assert inside["id"] in ids
    assert agent_order["id"] in ids
    assert all(it["deadline"] == target.isoformat() or it["deadline"] == (target + timedelta(days=1)).isoformat() for it in data["items"])
    assert data["total"] == 2
    assert data["summary"]["open"] == 2
    assert data["truncated"] is False

    agent_view = agent_client.get(
        "/api/orders/calendar",
        params={"start": target.isoformat(), "end": (target + timedelta(days=2)).isoformat()},
    )
    assert agent_view.status_code == 200
    agent_ids = {it["id"] for it in agent_view.json()["items"]}
    assert agent_ids == {agent_order["id"]}

    staff_view = staff_client.get(
        "/api/orders/calendar",
        params={"start": target.isoformat(), "end": (target + timedelta(days=2)).isoformat()},
    )
    assert staff_view.status_code == 200
    assert {it["id"] for it in staff_view.json()["items"]} == ids


def test_calendar_rejects_bad_range(admin_client):
    start = date.today()
    earlier = admin_client.get(
        "/api/orders/calendar",
        params={"start": start.isoformat(), "end": (start - timedelta(days=1)).isoformat()},
    )
    assert earlier.status_code == 400
    too_long = admin_client.get(
        "/api/orders/calendar",
        params={"start": start.isoformat(), "end": (start + timedelta(days=63)).isoformat()},
    )
    assert too_long.status_code == 400
    no_auth = TestClient(admin_client.app).get(
        "/api/orders/calendar",
        params={"start": start.isoformat(), "end": start.isoformat()},
    )
    assert no_auth.status_code == 401



def test_admin_reschedules_deadline(admin_client, staff_client, agent_client, order_factory):
    old_day = date.today() + timedelta(days=5)
    new_day = old_day + timedelta(days=2)
    order = order_factory(title="日历拖拽改期测试", deadline=old_day.isoformat())

    resp = admin_client.patch(
        f"/api/orders/{order['id']}/deadline",
        json={"deadline": new_day.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["changed"] is True
    assert data["deadline"] == new_day.isoformat()

    detail = admin_client.get(f"/api/orders/{order['id']}")
    assert detail.status_code == 200
    assert detail.json()["order"]["deadline"] == new_day.isoformat()

    same = admin_client.patch(
        f"/api/orders/{order['id']}/deadline",
        json={"deadline": new_day.isoformat()},
    )
    assert same.status_code == 200
    assert same.json()["changed"] is False

    for client in (staff_client, agent_client):
        forbidden = client.patch(
            f"/api/orders/{order['id']}/deadline",
            json={"deadline": old_day.isoformat()},
        )
        assert forbidden.status_code == 403

    no_auth = TestClient(admin_client.app).patch(
        f"/api/orders/{order['id']}/deadline",
        json={"deadline": old_day.isoformat()},
    )
    assert no_auth.status_code == 401

    cancelled = admin_client.post(
        f"/api/orders/{order['id']}/status",
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200, cancelled.text
    blocked = admin_client.patch(
        f"/api/orders/{order['id']}/deadline",
        json={"deadline": old_day.isoformat()},
    )
    assert blocked.status_code == 400
    assert "已取消" in blocked.json()["detail"]


def test_calendar_ics_export(admin_client, agent_client, order_factory):
    target = date.today() + timedelta(days=8)
    order = order_factory(
        title="ICS; 导出, 测试",
        deadline=target.isoformat(),
    )
    own = order_factory(
        title="ICS 代理订单",
        deadline=target.isoformat(),
        agent_username="agent1",
    )

    resp = admin_client.get(
        "/api/orders/calendar.ics",
        params={"start": target.isoformat(), "end": target.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/calendar")
    assert "attachment" in resp.headers["content-disposition"]
    text = resp.text
    assert "BEGIN:VCALENDAR" in text
    assert "END:VCALENDAR" in text
    assert f"UID:{order['id']}@bs-order-system.local" in text
    assert "SUMMARY:ICS\\; 导出\\, 测试" in text
    assert f"DTSTART;VALUE=DATE:{target.strftime('%Y%m%d')}" in text
    assert f"DTEND;VALUE=DATE:{(target + timedelta(days=1)).strftime('%Y%m%d')}" in text
    assert "STATUS:TENTATIVE" in text
    assert all(len(line.encode("utf-8")) <= 75 for line in text.splitlines())

    agent_view = agent_client.get(
        "/api/orders/calendar.ics",
        params={"start": target.isoformat(), "end": target.isoformat()},
    )
    assert agent_view.status_code == 200
    assert f"UID:{own['id']}@bs-order-system.local" in agent_view.text
    assert f"UID:{order['id']}@bs-order-system.local" not in agent_view.text

    no_auth = TestClient(admin_client.app).get(
        "/api/orders/calendar.ics",
        params={"start": target.isoformat(), "end": target.isoformat()},
    )
    assert no_auth.status_code == 401
