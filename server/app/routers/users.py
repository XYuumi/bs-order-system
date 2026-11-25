from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin, require_staff
from ..models import User
from ..schemas import UserCreateIn, UserUpdateIn
from ..security import gen_api_key, hash_password
from ..services.oplog import log_op
from ..services.order_svc import normalize_project_type

router = APIRouter(prefix="/api", tags=["users"])


def user_view(user: User, *, reveal_key: bool = False) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "role_label": user.role_label or None,
        "api_key": user.api_key if reveal_key else None,
        "is_active": user.is_active,
        "parent_id": user.parent_id,
        "commission_rate": float(user.commission_rate or 0),
        # 下发时归一为项目类型（历史存量可能是旧工种值 code/design/thesis）
        "api_categories": [
            t for t in (normalize_project_type(c) for c in (user.api_categories or "").split(",") if c) if t
        ] or None,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
    }


def _validate_parent(db: Session, target: User, parent_id: int | None) -> User | None:
    """校验上级代理：必须是代理角色、不能是自己、不能形成环。"""
    if parent_id is None:
        return None
    if parent_id == target.id:
        raise HTTPException(status_code=400, detail="上级代理不能是自己")
    parent = db.get(User, parent_id)
    if not parent or parent.role != "agent" or not parent.is_active:
        raise HTTPException(status_code=400, detail="上级代理不存在或不是启用的代理")
    # 沿上级链上溯，防止环
    cursor, depth = parent, 0
    while cursor is not None and depth < 10:
        if cursor.id == target.id:
            raise HTTPException(status_code=400, detail="不能形成上级代理循环")
        cursor = db.get(User, cursor.parent_id) if cursor.parent_id else None
        depth += 1
    return parent


@router.get("/users")
def list_users(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    return {"items": [user_view(u) for u in users]}


@router.post("/users")
def create_user(
    body: UserCreateIn,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    if body.role != "agent" and (body.parent_id or body.commission_rate):
        raise HTTPException(status_code=400, detail="只有代理角色可以设置上级与抽成")
    api_cats = None
    if body.role == "agent" and body.api_categories is not None and len(body.api_categories) > 0:
        # 旧工种值归一为项目类型（code/design→program, thesis→thesis）
        api_cats = ",".join(sorted({
            t for t in (normalize_project_type(c) for c in body.api_categories) if t
        })) or None
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name or body.username,
        role=body.role,
        api_key=gen_api_key() if body.role in ("admin", "agent", "staff") else None,
        parent_id=body.parent_id if body.role == "agent" else None,
        commission_rate=body.commission_rate or 0,
        api_categories=api_cats,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="用户名已存在")
    # flush 之后 user.id 才存在；在此之前校验环等于拿 None 和自己比较，永远通过。
    try:
        _validate_parent(db, user, user.parent_id)
    except HTTPException:
        db.rollback()
        raise
    log_op(
        db, "user_create", request=request, user=admin,
        entity_type="user", entity_id=user.id,
        detail={"username": user.username, "role": user.role},
    )
    db.commit()
    return {"user": user_view(user)}


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdateIn,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    changes: dict = {}
    revoke_sessions = False
    if body.display_name is not None:
        changes["display_name"] = body.display_name
    if body.role is not None:
        if user.id == admin.id and body.role != "admin":
            raise HTTPException(status_code=400, detail="不能修改自己的角色")
        if body.role != user.role:
            revoke_sessions = True
        changes["role"] = body.role
        if body.role in ("admin", "agent", "staff") and not user.api_key:
            user.api_key = gen_api_key()
        if body.role != "agent":
            user.parent_id = None
            user.commission_rate = 0
            user.api_categories = None
    if body.is_active is not None:
        if user.id == admin.id and not body.is_active:
            raise HTTPException(status_code=400, detail="不能禁用自己的账号")
        if not body.is_active and user.is_active:
            revoke_sessions = True
        changes["is_active"] = body.is_active
    if body.password:
        try:
            user.password_hash = hash_password(body.password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        changes["password"] = "******"
        revoke_sessions = True

    # 上级代理 / 抽成比例
    fields = body.model_fields_set
    if "parent_id" in fields or "commission_rate" in fields:
        if (body.role if body.role is not None else user.role) != "agent":
            raise HTTPException(status_code=400, detail="只有代理角色可以设置上级与抽成")
        if "parent_id" in fields:
            _validate_parent(db, user, body.parent_id)
            user.parent_id = body.parent_id
            changes["parent_id"] = body.parent_id
        if "commission_rate" in fields and body.commission_rate is not None:
            user.commission_rate = body.commission_rate
            changes["commission_rate"] = body.commission_rate

    # API 可拉取项目类型（独立于上级/抽成，可单独设置）
    if "api_categories" in fields:
        if (body.role if body.role is not None else user.role) != "agent":
            raise HTTPException(status_code=400, detail="只有代理角色可以设置 API 拉取类型")
        # 旧工种值（code/design/thesis）归一为项目类型后保存；历史存量读取时同样归一
        cats = sorted({t for t in (normalize_project_type(c) for c in (body.api_categories or [])) if t})
        user.api_categories = ",".join(cats) if cats else None
        changes["api_categories"] = cats or "全部"

    if not changes:
        raise HTTPException(status_code=400, detail="没有需要修改的字段")

    for field, value in changes.items():
        if field in ("display_name", "role", "is_active"):
            setattr(user, field, value)

    if revoke_sessions and user.api_key:
        # 改密/改角色/禁用时同时轮换长期 API Key，否则旧 Key 在会话吊销后仍可用。
        user.api_key = gen_api_key()
        changes["api_key"] = "rotated"
    log_op(db, "user_update", request=request, user=admin, entity_type="user", entity_id=user.id, detail=changes)
    if revoke_sessions:
        user.token_version = int(user.token_version or 0) + 1
    db.commit()
    if revoke_sessions:
        from ..ws import force_logout_user

        force_logout_user(user.id)
    return {"user": user_view(user)}


@router.get("/users/{user_id}/api-key")
def get_api_key(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """查看任意用户的 API Key。

    Key 是长期凭据，必须与重置同级保护：密码二次确认 + 操作审计。
    """
    from ..deps import require_password_confirm

    require_password_confirm(request, admin)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.role not in ("admin", "agent", "staff"):
        raise HTTPException(status_code=400, detail="该角色不使用 API Key")
    created = False
    if not user.api_key:
        user.api_key = gen_api_key()
        created = True
    log_op(
        db, "api_key_view", request=request, user=admin,
        entity_type="user", entity_id=user.id, detail={"created": created},
    )
    db.commit()
    return {"api_key": user.api_key}


@router.post("/users/{user_id}/reset-api-key")
def reset_api_key(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from ..deps import require_password_confirm

    require_password_confirm(request, admin)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.role not in ("admin", "agent", "staff"):
        raise HTTPException(status_code=400, detail="仅管理员/代理/写手角色使用 API Key")
    user.api_key = gen_api_key()
    log_op(db, "api_key_reset", request=request, user=admin, entity_type="user", entity_id=user.id)
    db.commit()
    return {"api_key": user.api_key}


# ---- 代理/写手自助查看与重置自己的 Key ----

@router.get("/me/api-key")
def my_api_key(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ("admin", "agent", "staff"):
        raise HTTPException(status_code=403, detail="仅管理员/代理/写手角色使用 API Key")
    if not user.api_key:
        user.api_key = gen_api_key()
        db.commit()
    return {"api_key": user.api_key}


@router.post("/me/api-key/reset")
def my_api_key_reset(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from ..deps import require_password_confirm

    require_password_confirm(request, user)
    if user.role not in ("admin", "agent", "staff"):
        raise HTTPException(status_code=403, detail="仅管理员/代理/写手角色使用 API Key")
    user.api_key = gen_api_key()
    log_op(db, "api_key_reset_self", request=request, user=user, entity_type="user", entity_id=user.id)
    db.commit()
    return {"api_key": user.api_key}
