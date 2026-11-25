from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from helpers import ADMIN_PASSWORD, AGENT_PASSWORD, STAFF_PASSWORD, TEMP_PASSWORD

# 必须在导入 app 之前固定测试库与安全配置。
os.environ["DB_NAME"] = "bs_order_system_test"
os.environ["REDIS_URL"] = ""
os.environ["COOKIE_SECURE"] = "false"
os.environ["AI_DAILY_QUOTA"] = "0"
os.environ["TRUST_PROXY_HEADERS"] = "false"

SERVER_DIR = Path(__file__).resolve().parents[1]
os.environ["UPLOAD_DIR"] = str(SERVER_DIR / "data" / "test-uploads")
os.environ["BACKUP_DIR"] = str(SERVER_DIR / "backups-test")

sys.path.insert(0, str(SERVER_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Quality, Setting, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services.settings_svc import DEFAULT_SETTINGS  # noqa: E402

QUALITIES = [
    ("white", "白色", "#9ca3af", 1, 1),
    ("green", "绿色", "#22c55e", 2, 2),
    ("blue", "蓝色", "#3b82f6", 3, 3),
    ("purple", "紫色", "#a855f7", 4, 4),
    ("orange", "橙色", "#f97316", 5, 5),
    ("red", "红色", "#ef4444", 6, 6),
]

PASSWORDS = {
    "admin": ADMIN_PASSWORD,
    "staff1": STAFF_PASSWORD,
    "agent1": AGENT_PASSWORD,
    "agent2": AGENT_PASSWORD,
    "locked": TEMP_PASSWORD,
}


@pytest.fixture(scope="session", autouse=True)
def database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        for code, name, color, mult, sort in QUALITIES:
            db.add(Quality(code=code, name=name, color=color, multiplier=mult, sort=sort))
        for key, value in DEFAULT_SETTINGS.items():
            db.add(Setting(key=key, value=value))
        users = [
            ("admin", "管理员", "admin"),
            ("staff1", "测试写手", "staff"),
            ("agent1", "代理一", "agent"),
            ("agent2", "代理二", "agent"),
            ("locked", "锁定用户", "agent"),
        ]
        for username, display, role in users:
            db.add(User(
                username=username,
                password_hash=hash_password(PASSWORDS[username]),
                display_name=display,
                role=role,
            ))
        db.commit()
    finally:
        db.close()
    yield
    # 清理测试库
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="session")
def app_client():
    return TestClient(app)


def _login(client: TestClient, username: str, password: str) -> TestClient:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return client


@pytest.fixture(scope="session")
def admin_client(app_client):
    return _login(app_client, "admin", PASSWORDS["admin"])


@pytest.fixture(scope="session")
def staff_client():
    return _login(TestClient(app), "staff1", PASSWORDS["staff1"])


@pytest.fixture(scope="session")
def agent_client():
    return _login(TestClient(app), "agent1", PASSWORDS["agent1"])


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def order_factory(admin_client):
    created = []

    def make(title: str = "测试订单", quality: str = "white", category: str = "code", **extra):
        payload = {"title": title, "quality_code": quality, "category": category, **extra}
        resp = admin_client.post("/api/orders", json=payload)
        assert resp.status_code == 200, resp.text
        order = resp.json()["order"]
        created.append(order["id"])
        return order

    yield make

    for oid in created:
        admin_client.delete(f"/api/orders/{oid}", headers={"X-Confirm-Password": ADMIN_PASSWORD})


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """每个测试清空进程内限流窗口：套件全程 <60s，否则新增加的用例会挤爆
    order_create 等共享限流桶，导致与限流无关的用例偶发 429。"""
    import app.ratelimit as ratelimit

    ratelimit._MEMORY.clear()
    yield
    ratelimit._MEMORY.clear()


@pytest.fixture(scope="session", autouse=True)
def cleanup_uploads():
    yield
    for folder in (SERVER_DIR / "data" / "test-uploads", SERVER_DIR / "backups-test"):
        shutil.rmtree(folder, ignore_errors=True)
