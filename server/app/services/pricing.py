"""品质定价：下单时按 基础价 × 品质倍率 快照。"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from ..models import Quality
from .settings_svc import get_setting


def money(v: Decimal | float | str) -> float:
    d = Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(d)


def get_base_prices(db: Session) -> tuple[Decimal, Decimal]:
    def _safe(key: str, default: str) -> Decimal:
        raw = get_setting(db, key, default)
        try:
            value = Decimal(str(raw))
            if not value.is_finite() or value < 0:
                raise ValueError
            return value
        except Exception:  # noqa: BLE001 —— 历史脏配置回退默认值
            return Decimal(default)

    return _safe("owner_base_price", "300"), _safe("agent_base_price", "50")


def compute_prices(db: Session, quality: Quality) -> tuple[float, float, float]:
    """返回 (真实价, 代理价, 倍率)；品质设置了自定义价则优先于 基础价×倍率。"""
    owner_base, agent_base = get_base_prices(db)
    mult = Decimal(str(quality.multiplier))
    owner = (
        float(quality.owner_price_override)
        if quality.owner_price_override is not None
        else money(owner_base * mult)
    )
    agent = (
        float(quality.agent_price_override)
        if quality.agent_price_override is not None
        else money(agent_base * mult)
    )
    return round(owner, 2), round(agent, 2), float(mult)


def get_quality_by_code(db: Session, code: str) -> Quality | None:
    return db.query(Quality).filter(Quality.code == code, Quality.enabled == True).first()  # noqa: E712


def quality_view(q: Quality, owner_base: Decimal | None, agent_base: Decimal, role: str) -> dict:
    mult = float(q.multiplier)
    view = {
        "code": q.code,
        "name": q.name,
        "color": q.color,
        "sort": q.sort,
        "enabled": q.enabled,
    }
    # 价格视野（中间商模式）：管理员见真实价/倍率/写手价；写手见写手价；
    # 代理=大客户：见给客户的默认报价（真实价基准），下单付款额即成交价，写手价不下发。
    if role in ("admin", "staff"):
        view["agent_price"] = (
            float(q.agent_price_override)
            if q.agent_price_override is not None
            else money(agent_base * Decimal(str(q.multiplier)))
        )
    if role in ("admin", "agent"):
        view["multiplier"] = mult
        base = owner_base if owner_base is not None else Decimal("0")
        view["owner_price"] = (
            float(q.owner_price_override)
            if q.owner_price_override is not None
            else money(base * Decimal(str(q.multiplier)))
        )
    if role == "public":
        # 公开报价单面向客户：只给客户价 price（成交价基准）。
        # 写手价是内部成本、倍率可反推毛利，都不下发。
        base = owner_base if owner_base is not None else Decimal("0")
        view["price"] = (
            float(q.owner_price_override)
            if q.owner_price_override is not None
            else money(base * Decimal(str(q.multiplier)))
        )
    if role == "admin":
        view["multiplier"] = mult
        base = owner_base if owner_base is not None else Decimal("0")
        view["owner_price"] = (
            float(q.owner_price_override)
            if q.owner_price_override is not None
            else money(base * Decimal(str(q.multiplier)))
        )
        view["owner_price_override"] = (
            float(q.owner_price_override) if q.owner_price_override is not None else None
        )
        view["agent_price_override"] = (
            float(q.agent_price_override) if q.agent_price_override is not None else None
        )
    return view
