from __future__ import annotations

import os
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.routers import health as health_router

# main.py 的接线由父会话完成；若路由尚未接入，测试里补挂一次，保证本文件可独立验证。
if not any(getattr(route, "path", "") == "/api/admin/health" for route in app.routes):
    app.include_router(health_router.router)

EXPECTED_KEYS = ["db", "redis", "uploads", "backups", "ws", "disk"]
GB = 1024 ** 3


def _fetch(client):
    resp = client.get("/api/admin/health")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _by_key(data):
    return {item["key"]: item for item in data["checks"]}


def test_health_requires_admin(agent_client):
    assert agent_client.get("/api/admin/health").status_code == 403
    assert TestClient(app).get("/api/admin/health").status_code == 401


def test_health_payload(admin_client):
    data = _fetch(admin_client)
    # Redis 未配置属于单机默认形态，不再强制 degraded；其他项（备份/磁盘）可能按环境告警。
    assert data["status"] in {"ok", "degraded"}
    assert data["checked_at"]
    assert isinstance(data["uptime_seconds"], int) and data["uptime_seconds"] >= 0
    assert data["version"]

    cards = _by_key(data)
    assert list(cards) == EXPECTED_KEYS
    for item in data["checks"]:
        assert set(item) >= {"key", "label", "status", "detail"}
        assert item["status"] in {"ok", "warn", "fail"}
        assert item["label"] and item["detail"]
        assert item["latency_ms"] >= 0

    assert cards["db"]["status"] == "ok"
    assert "SELECT 1" in cards["db"]["detail"]
    assert cards["redis"]["status"] == "ok"
    assert "单机可选" in cards["redis"]["detail"]
    assert cards["ws"]["status"] == "ok"


def test_check_failure_never_500(admin_client, monkeypatch):
    def boom():
        raise RuntimeError("模拟数据库探活异常")

    monkeypatch.setattr(health_router, "_check_db", boom)
    data = _fetch(admin_client)
    db = _by_key(data)["db"]
    assert db["status"] == "fail"
    assert "模拟数据库探活异常" in db["detail"]
    assert data["status"] == "degraded"


def test_upload_and_disk_thresholds(admin_client, monkeypatch, tmp_path):
    monkeypatch.setattr(health_router, "UPLOAD_DIR", tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"x" * 2048)
    monkeypatch.setattr(
        health_router,
        "_disk_usage",
        lambda _path: SimpleNamespace(total=100 * GB, used=90 * GB, free=10 * GB),
    )
    data = _fetch(admin_client)
    cards = _by_key(data)
    assert cards["uploads"]["status"] == "ok"
    assert "0.00 GB" in cards["uploads"]["detail"]
    assert cards["disk"]["status"] == "warn"
    assert "85%" in cards["disk"]["detail"]

    monkeypatch.setattr(
        health_router,
        "_disk_usage",
        lambda _path: SimpleNamespace(total=100 * GB, used=99.5 * GB, free=int(0.5 * GB)),
    )
    data = _fetch(admin_client)
    cards = _by_key(data)
    assert cards["uploads"]["status"] == "warn"
    assert "低于 1 GB" in cards["uploads"]["detail"]
    assert cards["disk"]["status"] == "fail"
    assert "95%" in cards["disk"]["detail"]


def test_backup_recency(admin_client, monkeypatch, tmp_path):
    monkeypatch.setattr(health_router, "BACKUP_DIR", tmp_path)
    data = _fetch(admin_client)
    assert _by_key(data)["backups"]["status"] == "warn"
    assert "暂无备份" in _by_key(data)["backups"]["detail"]

    fresh = tmp_path / "bs-backup-20260101-000000.json.enc"
    fresh.write_bytes(b"x")
    assert _by_key(_fetch(admin_client))["backups"]["status"] == "ok"

    past = time.time() - 8 * 86400
    os.utime(fresh, (past, past))
    data = _fetch(admin_client)
    backups = _by_key(data)["backups"]
    assert backups["status"] == "warn"
    assert "超过 7 天" in backups["detail"]
