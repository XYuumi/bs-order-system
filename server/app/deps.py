from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from .database import get_db
from .models import User
from .ratelimit import client_ip, rate_limit
from .security import decode_token, verify_password


def require_password_confirm(request: Request, user: User) -> None:
    """敏感操作二次确认：请求头 X-Confirm-Password 必须是当前用户登录密码。

    只对失败尝试计数，避免管理员连续批量操作时被误限流；错密码 10 次/分钟。
    """
    pwd = request.headers.get("x-confirm-password", "")
    if not pwd or not verify_password(pwd, user.password_hash):
        rate_limit(request, "confirm_fail", f"{user.id}:{client_ip(request)}", limit=10, window_seconds=60)
        raise HTTPException(status_code=403, detail="敏感操作需要密码确认（X-Confirm-Password）")


def get_current_user(request: Request, db=Depends(get_db)) -> User:
    token = request.cookies.get("token")
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")

    import jwt as pyjwt

    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub") or 0)
    except (pyjwt.InvalidTokenError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="登录凭证无效，请重新登录")

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="账号不存在或已禁用")
    # 旧 token 无 ver 字段按 0 处理；改密/停用/退出所有设备后版本递增，旧 token 立即失效。
    if int(payload.get("ver", 0) or 0) != int(user.token_version or 0):
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return user


def require(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="没有执行该操作的权限")
        return user

    return dependency


require_admin = require("admin")
require_staff = require("admin", "staff")


def api_key_user(request: Request, db=Depends(get_db)) -> User:
    """开放 API（/api/v1）认证：X-API-Key 头。管理员（全权限视图）/ 写手（全订单）/ 代理（自己订单）均可持有 Key。"""
    key = request.headers.get("x-api-key", "").strip()
    if not key:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            key = auth[7:].strip()
    if not key:
        raise HTTPException(status_code=401, detail="缺少 API Key（X-API-Key 请求头）")

    user = (
        db.query(User)
        .filter(User.api_key == key, User.is_active == True)  # noqa: E712
        .first()
    )
    if not user:
        raise HTTPException(status_code=401, detail="API Key 无效")
    return user
