"""客户交付分享：HMAC 无状态签名（免登录访问交付包/演示视频）。

token 形如 "{订单号}.{签发秒级时间戳}.{版本}.{签名16位hex}"，
签名 = HMAC-SHA256(JWT_SECRET, "deliver:{订单号}:{时间戳}:{版本}")。
版本来自 orders.deliver_token_version；撤销时递增，旧链接立即失效。
兼容旧版三段 token（版本视为 0），订单版本 > 0 后旧链接自动失效。
有效期由设置 deliver_expire_days 控制（0 = 永久；更换 JWT_SECRET 可整体吊销）。
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time

from ..config import JWT_SECRET

# 交付页可见可下载的分类：只放给客户的东西，不含内部文档
DELIVER_CATEGORIES = ("package", "video")

_ORDER_ID_RE = re.compile(r"^(?:demo)?\d{6}-\d{3,}$")


def _sig(order_id: str, issued: str, version: int) -> str:
    raw = f"deliver:{order_id}:{issued}:{int(version)}"
    return hmac.new(JWT_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]


def make_token(order_id: str, version: int = 0) -> str:
    issued = str(int(time.time()))
    return f"{order_id}.{issued}.{int(version)}.{_sig(order_id, issued, version)}"


def token_order_id(token: str) -> str | None:
    """只做格式提取（不验签），用于加载订单后拿到当前版本再验签。"""
    parts = (token or "").split(".")
    if len(parts) not in (3, 4):
        return None
    oid = parts[0]
    return oid if _ORDER_ID_RE.match(oid or "") else None


def parse_token(token: str, expire_days: int = 0, version: int = 0) -> str | None:
    """校验通过返回订单号；过期、版本不符或签名不符返回 None。"""
    parts = (token or "").split(".")
    if len(parts) == 3:
        oid, issued, sig = parts
        ver = 0
        expected = hmac.new(JWT_SECRET.encode(), f"deliver:{oid}:{issued}".encode(), hashlib.sha256).hexdigest()[:16]
    elif len(parts) == 4:
        oid, issued, ver_s, sig = parts
        if not ver_s.isdigit():
            return None
        ver = int(ver_s)
        expected = _sig(oid, issued, ver)
    else:
        return None
    if not _ORDER_ID_RE.match(oid or "") or not issued.isdigit():
        return None
    if ver != int(version or 0):
        return None
    if not hmac.compare_digest(expected, sig):
        return None
    if expire_days > 0 and time.time() - int(issued) > expire_days * 86400:
        return None
    return oid
