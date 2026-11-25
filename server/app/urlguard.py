"""服务端外发 URL 安全校验：仅允许 http/https，且目标必须是公网全局地址。"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    pass


def assert_safe_url(url: str) -> None:
    if not url or len(url) > 2000:
        raise UnsafeUrlError("URL 为空或过长")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"仅允许 http/https 协议: {parsed.scheme or '(空)'}")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URL 不允许包含账号密码")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("URL 缺少主机名")

    try:
        addrinfos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"无法解析主机名: {host}") from exc

    for info in addrinfos:
        ip = ipaddress.ip_address(info[4][0])
        # is_global 同时覆盖私网、环回、保留、链路本地、组播、未指定以及 100.64/10 等特殊段。
        if not ip.is_global:
            raise UnsafeUrlError(f"禁止访问内网/保留地址: {host} ({ip})")
