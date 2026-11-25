from __future__ import annotations

import secrets

from fastapi.testclient import TestClient

from app.main import app
from helpers import TEMP_PASSWORD


def test_login_rejects_wrong_password(app_client):
    resp = app_client.post("/api/auth/login", json={"username": "admin", "password": secrets.token_urlsafe(12)})
    assert resp.status_code == 401


def test_price_visibility_by_role(admin_client, staff_client, agent_client, order_factory):
    admin_q = admin_client.get("/api/qualities").json()["qualities"][0]
    staff_q = staff_client.get("/api/qualities").json()["qualities"][0]
    agent_q = agent_client.get("/api/qualities").json()["qualities"][0]
    # 中间商模式：管理员见成交价 + 写手价；写手只见写手价；代理只见成交价（写手价是内部成本）
    assert admin_q["owner_price"] > 0 and admin_q["agent_price"] > 0
    assert "owner_price" not in staff_q and "multiplier" not in staff_q
    assert staff_q["agent_price"] == admin_q["agent_price"]
    assert "agent_price" not in agent_q
    assert agent_q["owner_price"] == admin_q["owner_price"]

    order = order_factory("价格隔离测试订单")
    admin_view = admin_client.get(f"/api/orders/{order['id']}").json()["order"]
    staff_view = staff_client.get(f"/api/orders/{order['id']}").json()["order"]
    assert admin_view["owner_price"] > 0 and admin_view["agent_price"] > 0
    assert "owner_price" not in staff_view
    assert "multiplier" not in staff_view
    assert staff_view["agent_price"] > 0


def test_agent_only_sees_own_orders(agent_client, order_factory):
    order = order_factory("代理可见性测试")
    assert agent_client.get(f"/api/orders/{order['id']}").status_code == 403
    own = agent_client.post("/api/orders", json={"title": "代理自己的订单", "quality_code": "white", "category": "code"})
    assert own.status_code == 200
    oid = own.json()["order"]["id"]
    view = agent_client.get(f"/api/orders/{oid}").json()["order"]
    assert "agent_price" not in view  # 写手价是内部成本，代理不可见
    assert view["owner_price"] > 0    # 代理见自己的成交价


def test_unknown_api_returns_json_404(admin_client):
    resp = admin_client.get("/api/this-does-not-exist")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["detail"] == "接口不存在"


def test_security_headers(admin_client):
    resp = admin_client.get("/api/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "SAMEORIGIN"
    assert "default-src 'self'" in resp.headers["content-security-policy"]
    assert resp.headers["cache-control"] == "no-store"


def test_csrf_origin_rejected(admin_client):
    resp = admin_client.post(
        "/api/orders",
        json={"title": "跨站请求", "quality_code": "white", "category": "code"},
        headers={"Origin": "https://evil.example"},
    )
    assert resp.status_code == 403


def test_token_version_revocation(admin_client):
    created = admin_client.post("/api/users", json={
        "username": "revoke_me", "password": TEMP_PASSWORD, "display_name": "撤销测试", "role": "staff",
    })
    if created.status_code == 400:
        users = admin_client.get("/api/users").json()["items"]
        uid = next(u["id"] for u in users if u["username"] == "revoke_me")
        admin_client.patch(f"/api/users/{uid}", json={"password": TEMP_PASSWORD, "is_active": True})
    else:
        uid = created.json()["user"]["id"]

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "revoke_me", "password": TEMP_PASSWORD})
    assert login.status_code == 200
    assert client.get("/api/auth/me").status_code == 200

    resp = admin_client.patch(f"/api/users/{uid}", json={"is_active": False})
    assert resp.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_public_settings_does_not_require_auth(app_client):
    resp = app_client.get("/api/settings/public")
    assert resp.status_code == 200
    assert "site_name" in resp.json()
    assert "ai_ready" in resp.json()


def test_session_probe_returns_null_for_anonymous(admin_client):
    anon = TestClient(app)
    assert anon.get("/api/auth/session").status_code == 200
    assert anon.get("/api/auth/session").json()["user"] is None
    me = admin_client.get("/api/auth/session").json()["user"]
    assert me and me["username"] == "admin"


def test_long_password_rejected_by_schema(admin_client):
    resp = admin_client.post("/api/users", json={
        "username": "longpwd", "password": secrets.token_urlsafe(60), "display_name": "长密码", "role": "agent",
    })
    assert resp.status_code in (400, 422)


def test_security_headers_on_public_pages(app_client):
    resp = app_client.get("/login")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
