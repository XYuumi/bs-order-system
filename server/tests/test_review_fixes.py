"""本轮代码审查修复的回归测试。

覆盖：
- requirement_diff 缺 request 参数（ai=true 时 500）→ 现在正常返回；
- _same_origin 端口归一化（标准端口同源被误杀）；
- api_key_user 的 Bearer 回退切片错误；
- 品质改价缺少 owner>=agent 交叉校验。
"""
from __future__ import annotations

from helpers import ADMIN_PASSWORD
from starlette.requests import Request


def _req(host: str) -> Request:
    return Request({"type": "http", "headers": [(b"host", host.encode())], "method": "GET", "path": "/"})


def test_same_origin_port_normalization():
    from app.main import _same_origin

    # 标准端口：Origin 无端口、Host 无端口 → 同源
    assert _same_origin(_req("example.com"), "https://example.com") is True
    # 标准端口：Origin 无端口、Host 显式带默认端口 → 仍同源
    assert _same_origin(_req("example.com:443"), "https://example.com") is True
    assert _same_origin(_req("example.com:80"), "http://example.com") is True
    # 非默认端口：两侧都显式 → 同源
    assert _same_origin(_req("example.com:8000"), "http://example.com:8000") is True
    # 端口不一致 / 主机不一致 → 跨站
    assert _same_origin(_req("example.com"), "https://example.com:8443") is False
    assert _same_origin(_req("example.com"), "https://evil.com") is False
    # IPv6 Host
    assert _same_origin(_req("[::1]:8000"), "http://[::1]:8000") is True


def test_requirement_diff_with_ai_does_not_500(admin_client, order_factory, monkeypatch):
    """ai=true 分支此前引用未定义的 request，必然 500。"""
    order = order_factory("需求书对比回归")
    oid = order["id"]
    gen = admin_client.post(f"/api/orders/{oid}/requirement/generate", json={"mode": "template"})
    assert gen.status_code == 200, gen.text

    # 保存一个修改版，产生历史版本快照
    doc = gen.json()["document"]
    doc["chapters"]["scope"]["items"] = ["回归测试用的新范围条目"]
    saved = admin_client.put(f"/api/orders/{oid}/requirement", json={"document": doc})
    assert saved.status_code == 200, saved.text

    versions = admin_client.get(f"/api/orders/{oid}/requirement/versions").json()["versions"]
    assert versions, "应至少有一个历史版本"

    import app.services.docgen.ai as ai_module

    monkeypatch.setattr(ai_module, "deepseek_chat", lambda *a, **k: "AI 差异总结")
    resp = admin_client.get(
        f"/api/orders/{oid}/requirement/diff",
        params={"version_id": versions[0]["id"], "ai": "true"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"] == "AI 差异总结"
    assert body["diffs"], "模板生成稿与修改稿之间应存在差异"


def test_api_v1_bearer_token_auth(staff_client):
    """Authorization: Bearer <api_key> 应等价于 X-API-Key（此前切片只取了 1 个字符）。"""
    key_resp = staff_client.get("/api/me/api-key")
    assert key_resp.status_code == 200, key_resp.text
    api_key = key_resp.json()["api_key"]

    import app.main as main_module
    from fastapi.testclient import TestClient

    client = TestClient(main_module.app)
    resp = client.get("/api/v1/orders", headers={"Authorization": f"Bearer {api_key}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] is not None


def test_quality_update_rejects_owner_below_agent(admin_client):
    """自定义真实价低于代理价必须拒绝，防止负毛利订单绕过下单口径。"""
    resp = admin_client.put(
        "/api/qualities/white",
        json={"owner_price_override": 1, "agent_price_override": 100},
        headers={"X-Confirm-Password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 400, resp.text
    assert "不能低于代理价" in resp.json()["detail"]

    # 确认没有残留脏数据
    view = admin_client.get("/api/qualities").json()["qualities"]
    white = next(q for q in view if q["code"] == "white")
    assert white["owner_price"] >= white["agent_price"]
