from __future__ import annotations

import pytest

from app.services.deliver import make_token, parse_token
from app.services.pricing import quality_view
from app.services.receipt_svc import amount_to_cn
from app.urlguard import UnsafeUrlError, assert_safe_url


@pytest.mark.parametrize("amount,expected", [
    (0, "零元整"),
    (100050, "壹拾万零伍拾元整"),
    (1000001, "壹佰万零壹元整"),
    (100000001, "壹亿零壹元整"),
    (10500, "壹万零伍佰元整"),
    (0.05, "零元零伍分"),
    (1234.56, "壹仟贰佰叁拾肆元伍角陆分"),
])
def test_amount_to_cn(amount, expected):
    assert amount_to_cn(amount) == expected


def test_quality_view_public_shows_customer_price_only():
    """公开报价单：只给客户价 price（成交价基准 × 倍率，自定义真实价优先），不下发写手价与倍率。"""
    class Q:
        code = "white"
        name = "白色"
        color = "#fff"
        multiplier = 1
        sort = 1
        enabled = True
        owner_price_override = None
        agent_price_override = None

    q = Q()
    view = quality_view(q, 300, 50, "public")
    assert view["price"] == 300
    assert not {"agent_price", "owner_price", "multiplier"} & set(view)

    q.owner_price_override = 280.0
    assert quality_view(q, 300, 50, "public")["price"] == 280.0


def test_deliver_token_versioning():
    token_v0 = make_token("260101-001", 0)
    token_v1 = make_token("260101-001", 1)
    assert parse_token(token_v0, version=0) == "260101-001"
    assert parse_token(token_v0, version=1) is None
    assert parse_token(token_v1, version=1) == "260101-001"


def test_url_guard_blocks_loopback():
    with pytest.raises(UnsafeUrlError):
        assert_safe_url("http://127.0.0.1:8000/internal")
