from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from helpers import ADMIN_PASSWORD


def test_quote_page_and_price_visibility(admin_client, app_client):
    token = admin_client.get("/api/quote/link").json()["token"]
    resp = app_client.get(f"/api/quote/{token}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["qualities"]
    # 公开报价单只给客户价 price；写手价、成交价字段名、倍率都不下发
    assert all(
        q.get("price", 0) > 0 and not {"owner_price", "agent_price", "multiplier"} & set(q)
        for q in resp.json()["qualities"]
    )
    bad = app_client.get("/api/quote/not-a-valid-token")
    assert bad.status_code == 404
    assert bad.json()["detail"] == "报价单不存在或已失效"


def test_deliver_link_accept_download_revoke(admin_client, order_factory):
    order = order_factory("交付链接测试订单")
    oid = order["id"]
    upload = admin_client.post(
        f"/api/orders/{oid}/files",
        files={"file": ("demo.mp4", b"fake-mp4-content", "video/mp4")},
        data={"category": "video"},
    )
    assert upload.status_code == 200, upload.text
    file_id = upload.json()["file"]["id"]

    link = admin_client.get(f"/api/orders/{oid}/deliver-link")
    assert link.status_code == 200
    token = link.json()["token"]
    public = TestClient(app)

    view = public.get(f"/api/deliver/{token}")
    assert view.status_code == 200, view.text
    assert view.json()["files"][0]["id"] == file_id

    accepted = public.post(f"/api/deliver/{token}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["already"] is False
    again = public.post(f"/api/deliver/{token}/accept")
    assert again.status_code == 200
    assert again.json()["already"] is True

    download = public.get(f"/api/deliver/{token}/files/{file_id}/download")
    assert download.status_code == 200
    assert download.content == b"fake-mp4-content"

    revoked = admin_client.post(f"/api/orders/{oid}/deliver-link/revoke")
    assert revoked.status_code == 200
    assert public.get(f"/api/deliver/{token}").status_code == 404


def test_rotate_share_tokens(admin_client, app_client):
    old = admin_client.get("/api/quote/link").json()["token"]
    rotated = admin_client.post("/api/share/rotate")
    assert rotated.status_code == 200
    assert app_client.get(f"/api/quote/{old}").status_code == 404
    new = admin_client.get("/api/quote/link").json()["token"]
    assert new != old
    assert app_client.get(f"/api/quote/{new}").status_code == 200


def test_deleted_order_deliver_download_blocked(admin_client, order_factory):
    order = order_factory("删除后交付隔离")
    oid = order["id"]
    upload = admin_client.post(
        f"/api/orders/{oid}/files",
        files={"file": ("demo.mp4", b"fake-mp4-content", "video/mp4")},
        data={"category": "video"},
    )
    file_id = upload.json()["file"]["id"]
    token = admin_client.get(f"/api/orders/{oid}/deliver-link").json()["token"]

    assert admin_client.delete(f"/api/orders/{oid}", headers={"X-Confirm-Password": ADMIN_PASSWORD}).status_code == 200
    try:
        public = TestClient(app)
        assert public.get(f"/api/deliver/{token}").status_code == 404
        assert public.get(f"/api/deliver/{token}/files/{file_id}/download").status_code == 404
    finally:
        admin_client.post(f"/api/orders/{oid}/restore")
