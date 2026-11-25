from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.routers import ai_ops
from app.routers.ai_ops import _reply_message


def test_ai_ops_requires_staff(agent_client, staff_client):
    assert TestClient(app).get("/api/ai-ops/overview").status_code == 401
    assert agent_client.get("/api/ai-ops/overview").status_code == 403
    resp = staff_client.get("/api/ai-ops/overview")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data) >= {"stats", "focus", "risks", "recent", "order_options", "ai_ready"}
    assert isinstance(data["stats"].get("active"), int)


def test_ai_ops_risk_radar_uses_real_order(admin_client, order_factory):
    order = order_factory(
        title="【AI-风险】明日到期未开工订单",
        deadline=(date.today() + timedelta(days=1)).isoformat(),
    )
    resp = admin_client.get("/api/ai-ops/overview")
    assert resp.status_code == 200, resp.text
    rows = {r["order_id"]: r for r in resp.json()["risks"]}
    assert order["id"] in rows
    row = rows[order["id"]]
    assert row["risk_score"] >= 34
    assert row["risk_level"] in ("medium", "high")
    assert any(r["code"] == "due_urgent" for r in row["reasons"])
    assert row["next_action"]


def test_ai_ops_validation_does_not_call_model(admin_client, order_factory):
    order = order_factory(title="【AI-校验】无需求书订单")
    bad_scene = admin_client.post("/api/ai-ops/reply", json={"order_id": order["id"], "scene": "nope"})
    assert bad_scene.status_code == 400
    no_requirement = admin_client.post("/api/ai-ops/requirement-review", json={"order_id": order["id"]})
    assert no_requirement.status_code == 400
    missing = admin_client.post("/api/ai-ops/requirement-review", json={})
    assert missing.status_code == 400


def test_empty_risk_brief_skips_model_and_quota(admin_client, monkeypatch):
    monkeypatch.setattr(ai_ops, "_collect_risks", lambda db, user: [])

    def boom(*args, **kwargs):
        raise AssertionError("空态不应调用模型")

    monkeypatch.setattr(ai_ops, "_ai_call", boom)
    monkeypatch.setattr(ai_ops, "_ai_guard", boom)
    resp = admin_client.post("/api/ai-ops/risk-brief")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["priorities"] == []
    assert "没有在制订单" in data["headline"]


def test_reply_message_parser_handles_broken_and_nested_json():
    valid = _reply_message({"message": "您好，今晚 8 点同步"}, "{}")
    assert valid == "您好，今晚 8 点同步"

    nested = '{"message":"{\\"message\\":\\"内层消息\\",\\"tips\\":[]}"}'
    outer = {"message": '{"message":"内层消息","tips":[]}'}
    assert _reply_message(outer, nested) == "内层消息"

    broken = '{"message":"您好，资料已整理好","tips":["a"],"suggested_time":"今天 17:00"'
    assert _reply_message({}, broken) == "您好，资料已整理好"

    plain = _reply_message({}, "直接发送的纯文本消息")
    assert plain == "直接发送的纯文本消息"
