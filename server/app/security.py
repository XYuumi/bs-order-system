from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import JWT_EXPIRE_DAYS, JWT_SECRET

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > 72:
        raise ValueError("密码过长（bcrypt 最多 72 字节）")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        raw = password.encode("utf-8")
        if len(raw) > 72:
            return False
        return bcrypt.checkpw(raw, password_hash.encode("ascii"))
    except ValueError:
        return False


def create_token(user_id: int, username: str, role: str, token_version: int = 0) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "ver": int(token_version or 0),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """校验并解析 JWT，失败抛出 jwt.InvalidTokenError 系异常。

    PyJWT 不会强制要求 exp 字段存在，缺 exp 的 token 永不过期；
    这里显式 require exp/iat/sub，避免伪造或残缺 token 长期有效。
    """
    return jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[ALGORITHM],
        options={"require": ["exp", "iat", "sub"]},
    )


def gen_api_key() -> str:
    return "bsk_" + secrets.token_hex(20)
