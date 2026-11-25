from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..ratelimit import client_ip, rate_limit
from ..services.oplog import log_op
from ..services.settings_svc import set_setting
from ..services.share_svc import get_or_create_token, invalidate_share_cache, public_rank_data, public_screen_data

router = APIRouter(prefix="/api", tags=["share"])


@router.get("/screen/link")
def screen_link(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """经营大屏分享链接 token（仅管理员，投影/合作方展示用，无金额）。"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可获取经营大屏")
    return {"token": get_or_create_token(db, "screen")}


@router.get("/rank/link")
def rank_link(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """代理业绩榜分享链接 token（招商展示用，无金额）。"""
    return {"token": get_or_create_token(db, "rank")}


@router.post("/share/rotate")
def rotate_share_tokens(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """轮换报价单/大屏/业绩榜公开 token，旧链接立即失效。"""
    tokens = {}
    for key in ("quote_token", "screen_token", "rank_token"):
        tokens[key] = secrets.token_urlsafe(12)
        set_setting(db, key, tokens[key])
    log_op(db, "share_token_rotate", request=request, user=admin, detail={"keys": list(tokens)})
    db.commit()
    invalidate_share_cache()
    return {"ok": True, "tokens": tokens}


@router.get("/screen/{token}")
def screen_view(token: str, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "screen", client_ip(request), 60, 60)
    data = public_screen_data(db, token)
    if data is None:
        raise HTTPException(status_code=404, detail="大屏链接不存在或已失效")
    return data


@router.get("/rank/{token}")
def rank_view(token: str, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "rank", client_ip(request), 60, 60)
    data = public_rank_data(db, token)
    if data is None:
        raise HTTPException(status_code=404, detail="榜单链接不存在或已失效")
    return data
