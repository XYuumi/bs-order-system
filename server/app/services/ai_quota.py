"""AI 用量配额：按用户统计当日 AiUsage，防止单个账号刷爆额度。"""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..config import AI_DAILY_QUOTA
from ..models import AiUsage


def ensure_ai_quota(db: Session, user_id: int | None) -> None:
    if not AI_DAILY_QUOTA or not user_id:
        return
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    used = db.query(AiUsage).filter(
        AiUsage.user_id == user_id,
        AiUsage.created_at >= today,
    ).count()
    if used >= AI_DAILY_QUOTA:
        raise HTTPException(status_code=429, detail=f"今日 AI 调用已达上限（{AI_DAILY_QUOTA} 次），请明天再试")
