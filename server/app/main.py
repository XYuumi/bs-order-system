from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import ALLOWED_ORIGINS, COOKIE_SECURE, UPLOAD_DIR
from .routers import ai_ops, announcements, api_v1, auth, chat, excel, files, health, logs, messages, notifications, orders, paper, settings, share, stats, status_reverts, suggestions, templates, users
from .ws import ws_endpoint

# 过期分片上传会话的清理间隔（秒）
CHUNK_CLEANUP_INTERVAL_SECONDS = 6 * 3600

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动/关闭钩子。

    用 lifespan 取代已废弃的 @app.on_event（FastAPI 0.109+ 弃用，0.11x 移除）。
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    from .config import INSECURE_JWT_SECRET

    if INSECURE_JWT_SECRET:
        logging.getLogger("uvicorn.error").warning(
            "安全警告：JWT_SECRET 仍为默认值或长度不足 32 位，任何拿到源码/默认配置的人"
            "都可以伪造管理员 token。请在生产 .env 中配置强随机 JWT_SECRET。"
        )
    from .redis_client import init_redis
    from .ws import startup_realtime

    await init_redis()
    await startup_realtime()
    # 幂等建缺失表（老库升级补 notification 等新表；已存在的表不受影响）
    from .database import engine
    from .models import Base

    Base.metadata.create_all(bind=engine)
    # 幂等补列：create_all 不会给已有表加列，老库升级（如 v1.25 的 orders.project_type）在此自动补齐
    try:
        from .services.schema_upgrade import ensure_columns

        ensure_columns(engine)
    except Exception as exc:  # noqa: BLE001 —— 升级失败不阻断启动，但必须留下日志
        logging.getLogger("uvicorn.error").warning(f"自动补列失败，请手工执行 sql/ 下的迁移脚本: {exc}")
    # 清理过期的分片上传会话：启动时一次，之后定时执行。只靠启动清理的话，服务长期不重启时，
    # 中断的大文件上传会把临时分片一直留在磁盘上（单个会话最大可达数 GB）。
    from .services.files_svc import cleanup_expired_chunks

    async def _purge_expired_chunks() -> None:
        while True:
            await asyncio.sleep(CHUNK_CLEANUP_INTERVAL_SECONDS)
            try:
                await run_in_threadpool(cleanup_expired_chunks)
            except Exception:  # noqa: BLE001 —— 清理失败不影响服务，但要留下日志
                logging.getLogger("uvicorn.error").warning("清理过期分片上传失败", exc_info=True)

    try:
        await run_in_threadpool(cleanup_expired_chunks)
    except Exception:  # noqa: BLE001 —— 清理失败不影响启动
        pass
    chunk_cleaner = asyncio.create_task(_purge_expired_chunks())
    try:
        yield
    finally:
        chunk_cleaner.cancel()
        from .redis_client import close_redis
        from .ws import shutdown_realtime

        await shutdown_realtime()
        await close_redis()


app = FastAPI(
    title="毕设接单管理系统",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _split_host_port(host: str) -> tuple[str, str]:
    """拆 Host 头为 (hostname, port)；兼容 IPv6 的 [addr]:port，无端口时 port 为空串。"""
    if host.startswith("["):
        end = host.find("]")
        if end == -1:
            return host, ""
        rest = host[end + 1:]
        return host[1:end], rest[1:] if rest.startswith(":") else ""
    if host.count(":") == 1:
        name, _, port = host.partition(":")
        return name, port
    return host, ""


def _same_origin(request: Request, value: str) -> bool:
    try:
        parsed = urlparse(value)
        if not parsed.hostname:
            return False
        host = (request.headers.get("host") or "").lower()
        if not host:
            return False
        # 两侧对称归一化：缺省端口按 scheme 补默认值，避免标准端口部署时
        # Origin 无端口而构造侧补了 ":443"/":80" 导致同源被误判为跨站。
        host_name, host_port = _split_host_port(host)
        default_port = "443" if (parsed.scheme or request.url.scheme) == "https" else "80"
        origin_port = str(parsed.port) if parsed.port else default_port
        return parsed.hostname.lower() == host_name.lower() and origin_port == (host_port or default_port)
    except ValueError:
        return False


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # 浏览器 Cookie 鉴权的写请求做 Origin 校验；API Key/脚本请求（无 Origin）放行。
    if (
        request.method not in _SAFE_METHODS
        and not request.url.path.startswith("/api/v1/")
        and not request.headers.get("x-api-key")
        and not request.headers.get("authorization", "").lower().startswith("bearer ")
    ):
        origin = request.headers.get("origin") or request.headers.get("referer") or ""
        if origin and origin not in ALLOWED_ORIGINS and not _same_origin(request, origin):
            return JSONResponse({"detail": "跨站请求被拒绝"}, status_code=403)

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' ws: wss:; "
        "font-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'self'",
    )
    if COOKIE_SECURE:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(orders.router)
app.include_router(paper.router)
app.include_router(status_reverts.router)
app.include_router(files.router)
app.include_router(logs.router)
app.include_router(stats.router)
app.include_router(settings.router)
app.include_router(notifications.router)
app.include_router(suggestions.router)
app.include_router(messages.router)
app.include_router(announcements.router)

# WebSocket 实时推送（站内通知/私信）
app.websocket("/ws")(ws_endpoint)
app.include_router(chat.router)
app.include_router(share.router)
app.include_router(templates.router)
app.include_router(excel.router)
app.include_router(health.router)
app.include_router(api_v1.router)
app.include_router(ai_ops.router)


APP_VERSION = "1.25.2"


@app.get("/api/health")
def health():
    """运维探活（公开、无敏感信息）。"""
    return {"ok": True, "version": APP_VERSION}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """保留业务 404 的 detail；只有真正未匹配的前端路由才落 SPA。"""
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail else "请求失败"
    if exc.status_code == 404 and not request.url.path.startswith("/api"):
        if detail == "Not Found":
            return await spa_fallback(request)
    return JSONResponse({"detail": detail}, status_code=exc.status_code)


# ---- 生产模式：托管前端构建产物（web/dist），单端口运行 ----

WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"

if WEB_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    async def spa_fallback(request: Request):
        candidate = (WEB_DIST / request.url.path.lstrip("/")).resolve()
        if candidate.is_file() and candidate.is_relative_to(WEB_DIST.resolve()):
            return FileResponse(candidate)
        # 入口 HTML 不缓存（带 ETag 协商）：前端产物就地升级后浏览器普通刷新即可拿到新版本
        return FileResponse(WEB_DIST / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/{full_path:path}")
    async def spa_root(full_path: str, request: Request):
        # API 路径绝不能被 SPA 兜底成 200 HTML，否则客户端会把 HTML 当 JSON 解析。
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse({"detail": "接口不存在"}, status_code=404)
        if full_path.startswith("assets/"):
            return JSONResponse({"detail": "静态资源不存在"}, status_code=404)
        return await spa_fallback(request)
else:
    async def spa_fallback(request: Request):
        return JSONResponse({"detail": "前端未构建（web/dist 不存在）"}, status_code=404)


# 启动/关闭逻辑见文件顶部的 lifespan。