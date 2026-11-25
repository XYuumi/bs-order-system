"""需求书 AI 修订与默认交付期限测试。

- 创建订单留空交付期限 → 默认一个月后；
- AI 修订接口：角色权限、AI 未配置 503、成功路径返回修订稿且不落库；
- revise_by_ai 防截断：AI 输出缺章时回退原文档章节而非模板。
"""
from __future__ import annotations

from app.models import Order
from app.routers import orders as orders_router
from app.services.order_svc import default_deadline


def test_default_deadline_is_one_month_later():
    from datetime import date

    today = date.today()
    d = default_deadline()
    # 一个月后：月份数 +1（跨年则回到 1 月），日期对齐或取目标月月末
    expected_month = today.month + 1 if today.month < 12 else 1
    assert d.year == (today.year + 1 if today.month == 12 else today.year)
    assert d.month == expected_month
    assert d >= today


def test_create_order_without_deadline_defaults_one_month(admin_client):
    resp = admin_client.post(
        "/api/orders",
        json={"title": "默认交付期限测试", "quality_code": "white", "category": "code"},
    )
    assert resp.status_code == 200, resp.text
    order = resp.json()["order"]
    assert order["deadline"] == default_deadline().isoformat()


def test_create_order_with_explicit_deadline_kept(admin_client):
    from datetime import date, timedelta

    explicit = (date.today() + timedelta(days=10)).isoformat()
    resp = admin_client.post(
        "/api/orders",
        json={"title": "显式期限不受默认值影响", "quality_code": "white", "category": "code", "deadline": explicit},
    )
    assert resp.status_code == 200, resp.text
    order = resp.json()["order"]
    assert order["deadline"] == explicit


def test_ai_revise_rejects_agent(agent_client, order_factory):
    order = order_factory("AI修订权限测试")
    resp = agent_client.post(
        f"/api/orders/{order['id']}/requirement/ai-revise",
        json={"instruction": "把角色改名", "document": {}},
    )
    assert resp.status_code == 403


def test_ai_revise_unavailable_returns_503(admin_client, order_factory, monkeypatch):
    order = order_factory("AI未配置测试")
    monkeypatch.setattr(orders_router, "ai_available", lambda db: False)
    resp = admin_client.post(
        f"/api/orders/{order['id']}/requirement/ai-revise",
        json={"instruction": "把角色改名", "document": {}},
    )
    assert resp.status_code == 503


def test_ai_revise_returns_document_without_saving(admin_client, order_factory, monkeypatch, db):
    order = order_factory("AI修订成功路径")

    def fake_revise(db, document, instruction, title, tech_stack, *, order_id=None, user_id=None):
        assert "会员" in instruction
        doc = dict(document)
        doc["chapters"] = {**document["chapters"], "scope": {"items": ["修订后的建设范围"]}}
        return doc

    monkeypatch.setattr(orders_router, "ai_available", lambda db: True)
    monkeypatch.setattr(orders_router, "revise_by_ai", fake_revise)

    current = {"title": "x", "chapters": {"scope": {"items": ["旧范围"]}, "goal": {"paragraphs": ["目标"]}}}
    resp = admin_client.post(
        f"/api/orders/{order['id']}/requirement/ai-revise",
        json={"instruction": "角色改为会员用户", "document": current},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["document"]
    assert body["chapters"]["scope"]["items"] == ["修订后的建设范围"]
    # 修订稿不落库：订单 requirement 仍为空，保存需走既有 PUT 接口
    db.expire_all()
    assert db.get(Order, order["id"]).requirement is None


def test_ai_revise_truncated_output_falls_back_to_original_chapters(db):
    """AI 输出被截断丢章时，缺章回退原文档内容，而不是被通用模板覆盖。"""
    from app.services.docgen.ai import revise_by_ai

    base = {
        "title": "测试需求书",
        "chapters": {
            "goal": {"paragraphs": ["自定义项目目标段落，绝不能被模板覆盖"]},
            "scope": {"items": ["自定义建设范围"]},
        },
    }
    truncated = {
        "title": "测试需求书",
        "chapters": {"goal": {"paragraphs": ["AI 改过的目标"]}},  # 其余八章全部缺失
    }

    def fake_config(d):
        return {"key": "test-key", "base_url": "http://127.0.0.1:1", "model": "m", "timeout": 5}

    class FakeResp:
        status_code = 200

        def json(self):
            import json as _json
            return {"choices": [{"message": {"content": _json.dumps(truncated, ensure_ascii=False)}}], "usage": {}}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return FakeResp()

    import app.services.docgen.ai as ai_module
    from unittest.mock import patch

    with patch.object(ai_module, "get_ai_config", fake_config), \
            patch.object(ai_module, "assert_safe_url", lambda u: None), \
            patch.object(ai_module.httpx, "Client", FakeClient):
        result = revise_by_ai(db, base, "改一下目标", "测试需求书", None)

    assert result["chapters"]["goal"]["paragraphs"] == ["AI 改过的目标"]
    assert result["chapters"]["scope"]["items"] == ["自定义建设范围"]
    # 其余缺章也必须来自原文档兜底链（模板），但不能丢目标/范围这类已有自定义内容
    assert set(result["chapters"]) == {
        "goal", "scope", "roles", "scenarios", "functions", "rules", "data_scope", "tech", "database",
    }
