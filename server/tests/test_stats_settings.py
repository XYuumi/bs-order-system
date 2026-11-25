from __future__ import annotations

import os
from datetime import date

import pytest

from helpers import ADMIN_PASSWORD


def _close_order(admin_client, oid: str):
    for status in ("in_progress", "completed", "closed"):
        resp = admin_client.post(f"/api/orders/{oid}/status", json={"status": status})
        assert resp.status_code == 200, resp.text


def test_week_completed_counts_completion_time(admin_client, order_factory):
    order = order_factory("本周完成口径测试")
    _close_order(admin_client, order["id"])
    overview = admin_client.get("/api/stats/overview").json()
    assert overview["kpis"]["week_completed"] >= 1


def test_settlement_root_agent_has_no_phantom_commission(admin_client, order_factory):
    users = admin_client.get("/api/users").json()["items"]
    agent = next(u for u in users if u["username"] == "agent1")
    admin_client.patch(f"/api/users/{agent['id']}", json={"commission_rate": 10})
    try:
        order = order_factory("根代理提成测试", agent_username="agent1")
        _close_order(admin_client, order["id"])
        month = date.today().strftime("%Y-%m")
        data = admin_client.get("/api/stats/settlement", params={"month": month, "agent_id": agent["id"]}).json()
        assert data["summary"]["own_total"] > 0
        assert data["summary"]["paid"] == 0
        assert data["summary"]["net"] == data["summary"]["own_total"]
    finally:
        admin_client.patch(f"/api/users/{agent['id']}", json={"commission_rate": 0})


def test_writer_perf_rejects_invalid_month(admin_client):
    resp = admin_client.get("/api/stats/writer-perf", params={"month": "2026/10"})
    assert resp.status_code == 422


def test_settings_numeric_validation(admin_client):
    resp = admin_client.put(
        "/api/settings",
        json={"owner_base_price": "nan"},
        headers={"X-Confirm-Password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 400


def test_settings_invalid_webhook_url_returns_400(admin_client):
    """非法的通知网址：返回 400 与明确原因，而不是 500。"""
    resp = admin_client.put("/api/settings", json={"webhook_url": "ftp://example.com/hook"})
    assert resp.status_code == 400, resp.text
    assert "http" in resp.json()["detail"]


def test_quality_update_requires_password(admin_client):
    resp = admin_client.put("/api/qualities/white", json={"name": "白色"})
    assert resp.status_code == 403
    ok = admin_client.put(
        "/api/qualities/white",
        json={"name": "白色"},
        headers={"X-Confirm-Password": ADMIN_PASSWORD},
    )
    assert ok.status_code == 200


def test_watermark_toggle_roundtrip(admin_client):
    """水印开关：默认开启，可关闭，公开配置端点下发布尔值。"""
    pub = admin_client.get("/api/settings/public").json()
    assert pub["watermark_enabled"] is True

    resp = admin_client.put("/api/settings", json={"watermark_enabled": "0"})
    assert resp.status_code == 200, resp.text
    assert admin_client.get("/api/settings/public").json()["watermark_enabled"] is False
    assert admin_client.get("/api/settings").json()["settings"]["watermark_enabled"] == "0"

    # 杂乱真值归一化为 1
    admin_client.put("/api/settings", json={"watermark_enabled": "yes"})
    assert admin_client.get("/api/settings/public").json()["watermark_enabled"] is True

    admin_client.put("/api/settings", json={"watermark_enabled": "1"})
    assert admin_client.get("/api/settings/public").json()["watermark_enabled"] is True


def test_backup_is_encrypted_and_protected(admin_client):
    created = admin_client.post("/api/admin/backup")
    assert created.status_code == 200, created.text
    info = created.json()
    assert info["encrypted"] is True
    assert info["name"].endswith(".enc")

    listed = admin_client.get("/api/admin/backups").json()["items"]
    assert any(x["name"] == info["name"] and x["encrypted"] for x in listed)

    assert admin_client.get(f"/api/admin/backups/{info['name']}/download").status_code == 403
    download = admin_client.get(
        f"/api/admin/backups/{info['name']}/download",
        headers={"X-Confirm-Password": ADMIN_PASSWORD},
    )
    assert download.status_code == 200
    assert download.content[:5] == b"gAAAA"

    assert admin_client.delete(f"/api/admin/backups/{info['name']}").status_code == 403
    assert admin_client.delete(
        f"/api/admin/backups/{info['name']}",
        headers={"X-Confirm-Password": ADMIN_PASSWORD},
    ).status_code == 200


def test_backup_helpers_only_touch_open_file_objects(tmp_path):
    """加密与写明文只作用于调用方已打开的文件对象：传入路径不会被打开，磁盘上不会多出任何文件。"""
    import io
    import json

    from cryptography.fernet import Fernet

    from app.services import backup_svc

    target = tmp_path / "escape.tmp"
    with pytest.raises(AttributeError):
        backup_svc._encrypt_stream(io.BytesIO(b"plain"), str(target))
    with pytest.raises(AttributeError):
        backup_svc._write_backup_json(None, [], "2026-01-01", str(target))
    assert not target.exists()
    # 下载 / 恢复 / 删除 / 同步按用户给的文件名取文件，仍由 _safe_path 限制在备份目录内
    with pytest.raises(ValueError):
        backup_svc._safe_path("..")

    plain = io.BytesIO("订单数据".encode("utf-8"))
    token = io.BytesIO()
    backup_svc._encrypt_stream(plain, token)
    assert Fernet(backup_svc._fernet_key()).decrypt(token.getvalue()) == plain.getvalue()

    dumped = io.BytesIO()
    assert backup_svc._write_backup_json(None, [], "2026-01-01", dumped) == 0
    assert json.loads(dumped.getvalue()) == {"format": 2, "created_at": "2026-01-01", "tables": {}}


def test_backup_roundtrip_after_streaming_rewrite(admin_client):
    """流式写入 + 分块加密后的备份能被 Fernet 正常解密并恢复出数据表。"""
    from app.services import backup_svc

    info = admin_client.post("/api/admin/backup").json()
    payload = backup_svc.read_backup_payload(info["name"])
    assert payload["format"] == 2
    assert "orders" in payload["tables"]
    # 备份目录里只留成品：明文与密文临时文件都不得残留
    assert all(p.name.startswith(backup_svc.FILE_PREFIX + "-") for p in backup_svc.BACKUP_DIR.iterdir())


def test_backup_now_removes_temp_files_when_failing(monkeypatch):
    """写出明文后加密中途失败：半截密文临时文件与明文都不残留，也不留下本次的成品文件。"""
    from app.services import backup_svc

    backup_dir = backup_svc.BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in backup_dir.iterdir()}

    def fail(src, dst):
        dst.write(b"partial ciphertext")
        raise RuntimeError("加密失败")

    monkeypatch.setattr(backup_svc, "_encrypt_stream", fail)
    with pytest.raises(RuntimeError, match="加密失败"):
        backup_svc.backup_now()
    assert {p.name for p in backup_dir.iterdir()} == before


@pytest.mark.skipif(os.name == "nt", reason="Windows 的临时文件在关闭前保留文件名")
def test_backup_plaintext_has_no_name_on_disk(monkeypatch):
    """明文只写进匿名临时文件（链接数为 0）：加密期间备份目录里只多出一份密文临时文件，看不到明文。"""
    from app.services import backup_svc

    backup_dir = backup_svc.BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in backup_dir.iterdir()}
    seen = {}
    real_encrypt = backup_svc._encrypt_stream

    def spy(src, dst):
        seen["plain_nlink"] = os.fstat(src.fileno()).st_nlink
        seen["new_files"] = {p.name for p in backup_dir.iterdir()} - before
        real_encrypt(src, dst)

    monkeypatch.setattr(backup_svc, "_encrypt_stream", spy)
    info = backup_svc.backup_now()
    assert seen["plain_nlink"] == 0
    (new_file,) = seen["new_files"]  # 恰好一个：本次的密文临时文件
    assert new_file.startswith(f".{info['name']}.") and new_file.endswith(".tmp")
    backup_svc._safe_path(info["name"]).unlink()
