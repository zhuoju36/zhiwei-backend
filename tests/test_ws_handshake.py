"""WebSocket 握手与订阅流程测试（防止前端反馈的 500 复现）。

修复要点：/ws/data 在 token 校验通过后立即 accept（Starlette 要求），
然后再进入 receive_text() 循环。

使用最小 FastAPI app（仅含 ws 路由）测试，避免触发完整 lifespan
造成跨事件循环问题。
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.ws.endpoints import router as ws_router

app = FastAPI()
app.include_router(ws_router)


def _get_token(client: TestClient) -> str:
    """通过完整应用登录获取 token（TestClient 必须支持 login，单独走 login 路由）。"""
    from app.main import full_app

    with TestClient(full_app) as c:
        resp = c.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123456"})
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]["access_token"]


def test_ws_handshake_then_subscribe() -> None:
    """验证修复后的完整握手：accept → send subscribe → 收到 cmd:subscribed。"""
    with TestClient(app) as client:
        # 直接构造一个有效 JWT（避免依赖完整应用）
        from app.core.security import create_access_token

        token = create_access_token(user_id=1, role="admin")
        with client.websocket_connect(f"/ws/data?token={token}") as ws:
            ws.send_text(json.dumps({"type": "cmd:subscribe", "project_id": 1}))
            ack = json.loads(ws.receive_text())
            assert ack["type"] == "cmd:subscribed"
            assert ack["project_id"] == 1


def test_ws_invalid_token_rejected() -> None:
    """无效 token 应被关闭连接，不进入主流程。"""
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/data?token=invalid"):
                pass
        assert exc_info.value.code == 4401


def test_ws_missing_token_rejected() -> None:
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/data"):
                pass
