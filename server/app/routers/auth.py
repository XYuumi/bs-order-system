from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import COOKIE_SECURE, JWT_EXPIRE_DAYS
from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..ratelimit import client_ip, rate_limit
from ..schemas import ChangePasswordIn, LoginIn
from ..security import create_token, decode_token, gen_api_key, hash_password, verify_password
from ..services.oplog import log_op

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 10


def _lock_config(db) -> tuple[int, int]:
    """登录锁定阈值/时长（settings 可配，非法值回退默认）。"""
    from ..services.settings_svc import get_setting

    try:
        threshold = max(int(get_setting(db, "login_lock_threshold") or MAX_FAILED_LOGINS), 1)
    except ValueError:
        threshold = MAX_FAILED_LOGINS
    try:
        minutes = max(int(get_setting(db, "login_lock_minutes") or LOCK_MINUTES), 1)
    except ValueError:
        minutes = LOCK_MINUTES
    return threshold, minutes


class LoginIn2FA(LoginIn):
    totp_code: str | None = Field(default=None, max_length=8)


class TotpDisableIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


def _set_token_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "token", token,
        max_age=JWT_EXPIRE_DAYS * 24 * 3600,
        httponly=True, samesite="lax", secure=COOKIE_SECURE, path="/",
    )


def _issue_login(response: Response, user: User, request: Request, db: Session) -> dict:
    token = create_token(user.id, user.username, user.role, user.token_version)
    user.last_login_at = datetime.now()
    user.failed_logins = 0
    user.locked_until = None
    log_op(db, "login", request=request, user=user)
    db.commit()
    _set_token_cookie(response, token)
    return {"user": user_brief(user)}


@router.post("/login")
def login(body: LoginIn2FA, request: Request, response: Response, db: Session = Depends(get_db)):
    # 同一 IP 总限速放宽（共享出口/脚本），同一账号仍保持 10 次/分钟的暴力破解保护。
    rate_limit(request, "login_ip", client_ip(request), limit=60, window_seconds=60)
    rate_limit(request, "login_user", body.username.strip().lower(), limit=10, window_seconds=60)

    user = db.query(User).filter(User.username == body.username).first()

    # 失败锁定：N 次失败锁 M 分钟（settings 可配，窗口内再尝试直接拒绝）
    lock_threshold, lock_minutes = _lock_config(db)
    if user and user.locked_until and user.locked_until > datetime.now():
        remain = int((user.locked_until - datetime.now()).total_seconds() // 60) + 1
        raise HTTPException(status_code=423, detail=f"失败次数过多，账号已锁定，请 {remain} 分钟后再试")

    if not user or not verify_password(body.password, user.password_hash):
        if user:
            user.failed_logins = (user.failed_logins or 0) + 1
            if user.failed_logins >= lock_threshold:
                user.locked_until = datetime.now() + timedelta(minutes=lock_minutes)
                user.failed_logins = 0
        log_op(db, "login_failed", request=request, detail={"username": body.username})
        db.commit()
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")

    # TOTP 两步验证：已启用但未带码 → 提示前端进入第二步（不下发 token）
    if user.totp_secret:
        import pyotp

        code = (body.totp_code or "").strip()
        if not code:
            return {"totp_required": True, "user": None}
        if not pyotp.TOTP(user.totp_secret).verify(code, valid_window=1):
            user.failed_logins = (user.failed_logins or 0) + 1
            if user.failed_logins >= lock_threshold:
                user.locked_until = datetime.now() + timedelta(minutes=lock_minutes)
                user.failed_logins = 0
            log_op(db, "totp_failed", request=request, detail={"username": body.username})
            db.commit()
            raise HTTPException(status_code=401, detail="动态码不正确")

    return _issue_login(response, user, request, db)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """普通登出也递增会话版本，避免已泄露的 JWT 在 7 天有效期内继续可用。"""
    user.token_version = int(user.token_version or 0) + 1
    log_op(db, "logout", request=request, user=user)
    db.commit()
    from ..ws import force_logout_user

    force_logout_user(user.id)
    response.delete_cookie("token", path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"user": user_brief(user)}


@router.get("/session")
def session_probe(request: Request, db: Session = Depends(get_db)):
    """公开页/登录页探测会话：未登录返回 200 + user=null，避免控制台 401 噪声。"""
    import jwt as pyjwt

    token = request.cookies.get("token") or ""
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    if not token:
        return {"user": None}
    try:
        payload = decode_token(token)
        user = db.get(User, int(payload.get("sub") or 0))
        if (
            user and user.is_active
            and int(payload.get("ver", 0) or 0) == int(user.token_version or 0)
        ):
            return {"user": user_brief(user)}
    except Exception:  # noqa: BLE001
        pass
    return {"user": None}


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rate_limit(request, "change_pwd", f"{user.id}:{client_ip(request)}", limit=5, window_seconds=60)
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    if body.old_password == body.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与原密码相同")
    try:
        user.password_hash = hash_password(body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # 改密后吊销所有设备（含当前会话）与长期 API Key，强制重新登录。
    user.token_version = int(user.token_version or 0) + 1
    key_rotated = bool(user.api_key)
    if key_rotated:
        user.api_key = gen_api_key()
    log_op(db, "change_password", request=request, user=user, entity_type="user", entity_id=user.id,
           detail={"api_key_rotated": key_rotated})
    db.commit()
    from ..ws import force_logout_user

    force_logout_user(user.id)
    response.delete_cookie("token", path="/")
    return {"ok": True, "relogin": True, "api_key_rotated": key_rotated}


@router.post("/logout-all")
def logout_all(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """退出所有设备：递增会话版本，旧 Cookie/WS 全部失效。"""
    user.token_version = int(user.token_version or 0) + 1
    key_rotated = bool(user.api_key)
    if key_rotated:
        user.api_key = gen_api_key()
    log_op(db, "logout_all", request=request, user=user, detail={"api_key_rotated": key_rotated})
    db.commit()
    from ..ws import force_logout_user

    force_logout_user(user.id)
    response.delete_cookie("token", path="/")
    return {"ok": True, "api_key_rotated": key_rotated}


# ============================== TOTP 两步验证（个人中心自助开关） ==============================

class TotpEnableIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


@router.post("/totp/setup")
def totp_setup(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """生成待确认密钥 + 二维码（data URL），认证器扫码或手输。"""
    import io as _io

    import pyotp
    import qrcode

    if user.totp_secret:
        raise HTTPException(status_code=400, detail="已开启两步验证，如需更换请先关闭")
    secret = pyotp.random_base32()
    user.totp_pending = secret
    db.commit()

    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=user.username, issuer_name="毕设接单管理系统")
    buf = _io.BytesIO()
    qrcode.make(uri).save(buf, format="PNG")
    qr_data = "data:image/png;base64," + __import__("base64").b64encode(buf.getvalue()).decode()
    return {"secret": secret, "otpauth_uri": uri, "qr": qr_data}


@router.post("/totp/enable")
def totp_enable(
    body: TotpEnableIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import pyotp

    if not user.totp_pending:
        raise HTTPException(status_code=400, detail="请先生成密钥（setup）")
    if not pyotp.TOTP(user.totp_pending).verify(body.code.strip(), valid_window=1):
        raise HTTPException(status_code=400, detail="动态码不正确，请重试")
    user.totp_secret = user.totp_pending
    user.totp_pending = None
    log_op(db, "totp_enable", request=request, user=user)
    db.commit()
    return {"ok": True, "enabled": True}


@router.post("/totp/disable")
def totp_disable(
    request: Request,
    body: TotpDisableIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    password: str | None = Query(default=None),
):
    """关闭两步验证需要登录密码确认（优先 body，兼容旧版 query）。"""
    rate_limit(request, "totp", f"{user.id}:{client_ip(request)}", limit=10, window_seconds=60)
    pwd = (body.password if body else "") or (password or "")
    if not pwd or not verify_password(pwd, user.password_hash):
        raise HTTPException(status_code=400, detail="密码不正确")
    user.totp_secret = None
    user.totp_pending = None
    log_op(db, "totp_disable", request=request, user=user)
    db.commit()
    return {"ok": True, "enabled": False}


def user_brief(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "role_label": user.role_label or None,
        "has_api_key": bool(user.api_key),
        "last_login_at": user.last_login_at,
        "totp_enabled": bool(user.totp_secret),
    }
