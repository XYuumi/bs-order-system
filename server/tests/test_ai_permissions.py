from __future__ import annotations

from starlette.requests import Request

from app.models import Order, User
from app.routers.chat import (
    _parse_date,
    _tool_list_qualities,
    _tool_update_order,
    _tool_update_order_status,
    execute_tool,
)


def _request(headers=None) -> Request:
    return Request({"type": "http", "headers": headers or [], "method": "POST", "path": "/"})


def test_ai_quality_tool_respects_price_visibility(db):
    """中间商模式：管理员见成交价 + 写手价 + 倍率；写手只见写手价；代理只见成交价 + 倍率。"""
    admin = db.query(User).filter(User.username == "admin").one()
    staff = db.query(User).filter(User.username == "staff1").one()
    agent = db.query(User).filter(User.username == "agent1").one()
    admin_q = _tool_list_qualities(db, admin)["qualities"][0]
    staff_q = _tool_list_qualities(db, staff)["qualities"][0]
    agent_q = _tool_list_qualities(db, agent)["qualities"][0]
    assert admin_q["owner_price"] > 0 and admin_q["agent_price"] > 0 and admin_q["multiplier"]
    assert "owner_price" not in staff_q and "multiplier" not in staff_q
    assert staff_q["agent_price"] > 0
    assert "agent_price" not in agent_q  # 写手价是内部成本，代理不可见
    assert agent_q["owner_price"] > 0


def test_ai_status_tool_enforces_role_transitions(db, order_factory):
    """写手可把待开始直接标记完成，但不能把已完结回退。"""
    order = order_factory("AI状态机测试")
    user = db.query(User).filter(User.username == "staff1").one()
    result = _tool_update_order_status(db, user, {
        "order_id": order["id"], "new_status": "completed",
    }, _request())
    assert result.get("success") is True
    result = _tool_update_order_status(db, user, {
        "order_id": order["id"], "new_status": "pending",
    }, _request())
    assert "无权" in result.get("error", "")


def test_ai_sensitive_tool_requires_password(db, order_factory):
    order = order_factory("AI敏感工具测试")
    admin = db.query(User).filter(User.username == "admin").one()
    result = execute_tool("trash_order", {"order_id": order["id"]}, admin, db, _request())
    assert "页面" in result.get("error", "")
    db.expire_all()
    assert db.get(Order, order["id"]).is_deleted is False


def test_ai_quality_change_requires_password(db, order_factory):
    """换品质等价于重算两侧价格，AI 工具必须和 REST 一样要求密码确认。"""
    order = order_factory("AI改品质需密码")
    admin = db.query(User).filter(User.username == "admin").one()
    result = execute_tool(
        "update_order", {"order_id": order["id"], "quality_code": "green"}, admin, db, _request(),
    )
    assert "密码" in result.get("error", "")
    db.expire_all()
    assert db.get(Order, order["id"]).quality.code == "white"


def test_ai_invalid_deadline_is_rejected(db, order_factory):
    """日期解析失败必须报错，不能把原有交付期限静默清空。"""
    from datetime import date

    from app.services.order_svc import default_deadline

    order = order_factory("AI日期校验")
    # 留空创建的订单现在默认一个月后交付
    assert date.fromisoformat(order["deadline"]) == default_deadline()
    admin = db.query(User).filter(User.username == "admin").one()
    result = _tool_update_order(
        db, admin, {"order_id": order["id"], "deadline": "下周"}, _request(),
    )
    assert "无法识别" in result.get("error", "")
    db.expire_all()
    assert db.get(Order, order["id"]).deadline == default_deadline()


def test_parse_date_accepts_common_formats_only():
    assert _parse_date("2026-03-01") is not None
    assert _parse_date("2026/03/01") is not None
    assert _parse_date("2026.03.01") is not None
    assert _parse_date("明天") is None
    assert _parse_date("") is None


def test_ai_unknown_tool_returns_error_instead_of_crashing(db):
    admin = db.query(User).filter(User.username == "admin").one()
    result = execute_tool("not_a_real_tool", {}, admin, db, _request())
    assert "未知工具" in result.get("error", "")
