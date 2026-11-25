from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Setting

DEFAULT_SETTINGS = {
    "owner_base_price": "300",     # 管理员真实基础单价（白色品质 1x）
    "agent_base_price": "50",      # 代理基础单价（白色品质 1x）
    "site_name": "毕设接单管理系统",
    "deepseek_api_key": "",
    "deepseek_base_url": "https://api.deepseek.com",
    "deepseek_model": "deepseek-flash",
    "deepseek_timeout": "180",
    "webhook_url": "",
    # 订单详情防截图水印开关（1 开 / 0 关，默认开）
    "watermark_enabled": "1",
    # 论文初稿最少修改次数：达到后才能提交终稿（每次修改自动留档）
    "paper_draft_min_revisions": "5",
}

SECRET_KEYS = {"deepseek_api_key"}


def get_setting(db: Session, key: str, default: str | None = None) -> str | None:
    row = db.get(Setting, key)
    if row is not None and row.value is not None and row.value != "":
        return row.value
    if default is not None:
        return default
    return DEFAULT_SETTINGS.get(key, "")


def get_settings_map(db: Session, keys: list[str] | None = None) -> dict[str, str]:
    rows = db.query(Setting).all()
    stored = {r.key: r.value for r in rows if r.value not in (None, "")}
    result = dict(DEFAULT_SETTINGS)
    result.update(stored)
    if keys:
        result = {k: v for k, v in result.items() if k in keys}
    return result


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
