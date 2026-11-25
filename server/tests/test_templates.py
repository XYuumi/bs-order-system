"""模板库接口测试：登录/角色权限、可见性、筛选、使用计数与审计。

主应用（app/main.py）由父任务统一接线，本测试文件在路由尚未挂载时临时挂载，
挂载后自动跳过，因此无论接线前后测试都能独立运行。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models import OperationLog, OrderTemplate
from app.routers import templates as templates_module


def _ensure_templates_router() -> None:
    """主应用还没接线时临时挂载路由。

    注意：web/dist 存在时 main.py 会注册 SPA 兜底路由 GET /{full_path:path}，
    它按注册顺序先匹配，所以新路由必须插到兜底路由之前。
    """
    if any(getattr(r, "path", "").startswith("/api/templates") for r in app.routes):
        return
    before = len(app.router.routes)
    app.include_router(templates_module.router)
    added = app.router.routes[before:]
    del app.router.routes[before:]
    fallback = next(
        (i for i, r in enumerate(app.router.routes) if getattr(r, "path", "") == "/{full_path:path}"),
        len(app.router.routes),
    )
    app.router.routes[fallback:fallback] = added


_ensure_templates_router()


def _create(client, title: str, kind: str = "requirement", content: str = "模板正文", is_shared: bool = True) -> dict:
    resp = client.post(
        "/api/templates",
        json={"kind": kind, "title": title, "content": content, "is_shared": is_shared},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ids(items) -> set[int]:
    return {x["id"] for x in items}


def test_templates_require_login():
    client = TestClient(app)
    assert client.get("/api/templates").status_code == 401
    assert client.post("/api/templates", json={"title": "未登录", "content": "x"}).status_code == 401
    assert client.post("/api/templates/1/use").status_code == 401


def test_agent_cannot_create_template(agent_client):
    resp = agent_client.post("/api/templates", json={"title": "代理不该能建", "content": "x"})
    assert resp.status_code == 403


def test_create_validates_payload(staff_client):
    bad = [
        {"title": "", "content": "x"},
        {"title": "x" * 121, "content": "x"},
        {"title": "类型非法", "content": "x", "kind": "bad"},
        {"title": "内容为空", "content": ""},
        {"title": "内容缺失"},
    ]
    for payload in bad:
        assert staff_client.post("/api/templates", json=payload).status_code == 422, payload

    # 纯空白字符 pydantic 放行，业务层再拦
    assert staff_client.post("/api/templates", json={"title": "   ", "content": "x"}).status_code == 400
    assert staff_client.post("/api/templates", json={"title": "合法标题", "content": "   "}).status_code == 400

    # 120 字标题是合法上界
    ok = staff_client.post("/api/templates", json={"title": "长" * 120, "content": "正文"})
    assert ok.status_code == 200
    assert len(ok.json()["title"]) == 120


def test_staff_create_template_and_list(staff_client, db):
    title = "创建测试-需求模板"
    tpl = _create(staff_client, title, kind="requirement", content="第一章 绪论\n第二章 系统设计")

    assert tpl["kind"] == "requirement"
    assert tpl["kind_cn"] == "需求模板"
    assert tpl["usage_count"] == 0
    assert tpl["is_shared"] is True
    assert tpl["username"] == "测试写手"
    assert tpl["can_edit"] is True and tpl["can_delete"] is True
    assert tpl["created_at"] and tpl["updated_at"]

    data = staff_client.get("/api/templates", params={"keyword": title}).json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == tpl["id"]

    log = (
        db.query(OperationLog)
        .filter(OperationLog.action == "template_create", OperationLog.entity_id == str(tpl["id"]))
        .first()
    )
    assert log is not None
    assert log.entity_type == "template"
    assert title in (log.detail or "")


def test_visibility_by_share_and_role(admin_client, staff_client, agent_client):
    shared = _create(admin_client, "可见性测试-共享", content="共享正文", is_shared=True)
    private = _create(admin_client, "可见性测试-私有", content="私有正文", is_shared=False)

    agent_items = agent_client.get("/api/templates", params={"keyword": "可见性测试"}).json()["items"]
    assert _ids(agent_items) == {shared["id"]}

    staff_items = staff_client.get("/api/templates", params={"keyword": "可见性测试"}).json()["items"]
    assert _ids(staff_items) == {shared["id"], private["id"]}
    private_view = next(x for x in staff_items if x["id"] == private["id"])
    # 写手可见全部，但不是创建者，不能改
    assert private_view["can_edit"] is False and private_view["can_delete"] is False

    admin_items = admin_client.get("/api/templates", params={"keyword": "可见性测试"}).json()["items"]
    assert _ids(admin_items) == {shared["id"], private["id"]}


def test_kind_and_keyword_filters(staff_client):
    tech = _create(staff_client, "筛选测试-Kafka幂等", kind="tech", content="Kafka 幂等消费方案")
    quote = _create(staff_client, "筛选测试-报价话术", kind="quote", content="报价按工时计算")

    by_kind = staff_client.get("/api/templates", params={"kind": "tech", "keyword": "筛选测试"}).json()
    assert by_kind["total"] == 1
    assert by_kind["items"][0]["id"] == tech["id"]

    # keyword 同时匹配标题、正文、创建人
    by_content = staff_client.get("/api/templates", params={"keyword": "报价按工时"}).json()
    assert quote["id"] in _ids(by_content["items"])

    by_user = staff_client.get("/api/templates", params={"keyword": "测试写手", "kind": "quote"}).json()
    assert quote["id"] in _ids(by_user["items"])

    assert staff_client.get("/api/templates", params={"kind": "unknown"}).status_code == 400


def test_patch_permissions_and_audit(admin_client, staff_client, agent_client, db):
    own = _create(staff_client, "更新测试-写手自己的", content="旧内容")

    resp = staff_client.patch(
        f"/api/templates/{own['id']}",
        json={"title": "更新测试-写手改标题", "content": "新内容", "kind": "remark", "is_shared": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "更新测试-写手改标题"
    assert body["kind"] == "remark"
    assert body["kind_cn"] == "常用备注"
    assert body["content"] == "新内容"
    assert body["is_shared"] is False
    assert body["can_edit"] is True

    log = (
        db.query(OperationLog)
        .filter(OperationLog.action == "template_update", OperationLog.entity_id == str(own["id"]))
        .first()
    )
    assert log is not None and log.entity_type == "template"
    assert "更新测试-写手自己的" in (log.detail or "")

    admin_tpl = _create(admin_client, "更新测试-管理员创建", content="x")
    # 非创建者写手越权、代理越权
    assert staff_client.patch(f"/api/templates/{admin_tpl['id']}", json={"title": "写手越权"}).status_code == 403
    assert agent_client.patch(f"/api/templates/{own['id']}", json={"title": "代理越权"}).status_code == 403
    # 管理员可以改别人的
    assert admin_client.patch(f"/api/templates/{own['id']}", json={"title": "管理员代改"}).status_code == 200
    # 空 patch / 不存在
    assert staff_client.patch(f"/api/templates/{own['id']}", json={}).status_code == 400
    assert staff_client.patch("/api/templates/999999", json={"title": "不存在"}).status_code == 404


def test_delete_permissions_and_physical_removal(admin_client, staff_client, agent_client, db):
    tpl = _create(staff_client, "删除测试-写手创建", content="准备删除")

    assert agent_client.delete(f"/api/templates/{tpl['id']}").status_code == 403
    admin_tpl = _create(admin_client, "删除测试-管理员创建", content="x")
    assert staff_client.delete(f"/api/templates/{admin_tpl['id']}").status_code == 403

    resp = staff_client.delete(f"/api/templates/{tpl['id']}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    assert db.get(OrderTemplate, tpl["id"]) is None
    left = staff_client.get("/api/templates", params={"keyword": "删除测试-写手创建"}).json()
    assert left["total"] == 0

    log = (
        db.query(OperationLog)
        .filter(OperationLog.action == "template_delete", OperationLog.entity_id == str(tpl["id"]))
        .first()
    )
    assert log is not None and log.entity_type == "template"
    assert "删除测试-写手创建" in (log.detail or "")

    assert staff_client.delete("/api/templates/999999").status_code == 404


def test_use_template_counts_and_returns_content(staff_client, agent_client):
    tpl = _create(staff_client, "使用测试-共享模板", content="使用测试正文")

    first = agent_client.post(f"/api/templates/{tpl['id']}/use")
    assert first.status_code == 200
    body = first.json()
    assert body["id"] == tpl["id"]
    assert body["title"] == "使用测试-共享模板"
    assert body["content"] == "使用测试正文"
    assert body["usage_count"] == 1

    second = agent_client.post(f"/api/templates/{tpl['id']}/use").json()
    assert second["usage_count"] == 2

    listed = staff_client.get("/api/templates", params={"keyword": "使用测试-共享模板"}).json()["items"]
    assert listed[0]["usage_count"] == 2

    private = _create(staff_client, "使用测试-私有模板", content="私有正文", is_shared=False)
    assert agent_client.post(f"/api/templates/{private['id']}/use").status_code == 404
    assert agent_client.post("/api/templates/999999/use").status_code == 404


def test_list_orders_by_updated_at_desc(staff_client, db):
    older = _create(staff_client, "排序测试-早创建", content="早")
    newer = _create(staff_client, "排序测试-晚创建", content="晚")
    now = datetime.now()
    db.query(OrderTemplate).filter(OrderTemplate.id == older["id"]).update({"updated_at": now - timedelta(days=1)})
    db.query(OrderTemplate).filter(OrderTemplate.id == newer["id"]).update({"updated_at": now})
    db.commit()

    items = staff_client.get("/api/templates", params={"keyword": "排序测试"}).json()["items"]
    assert [x["id"] for x in items] == [newer["id"], older["id"]]


def test_admin_sees_all_templates(admin_client, db):
    total = db.query(OrderTemplate).count()
    data = admin_client.get("/api/templates").json()
    assert data["total"] == total
    assert len(data["items"]) == min(total, 500)
