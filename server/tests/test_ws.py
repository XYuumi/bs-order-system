from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app


def test_websocket_requires_valid_session(admin_client):
    token = admin_client.cookies.get("token")
    assert token
    with TestClient(app).websocket_connect("/ws", headers={"cookie": f"token={token}"}) as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        ws.send_text("ping")
        assert ws.receive_json()["type"] == "pong"


def test_websocket_rejects_invalid_token():
    with TestClient(app) as client:
        try:
            with client.websocket_connect("/ws", headers={"cookie": "token=invalid"}):
                raise AssertionError("无效 token 不应建立连接")
        except WebSocketDisconnect as exc:
            assert exc.code == 4401
