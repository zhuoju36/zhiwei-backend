"""WS 项目权限校验测试。

使用 FastAPI TestClient + 直接调用 handler（避免跨事件循环的 pytest fixture）。
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token
from app.services import data_service
from app.ws.endpoints import ws_data

_app = FastAPI()
_app.add_api_websocket_route("/ws/data", ws_data)


@pytest.fixture(autouse=True)
def _reset_data_service_state_around_test() -> None:
    """每个 WS 测试前后释放 data_service 全局池与 Redis，避免跨 TestClient 循环污染。"""
    data_service._pool = None
    data_service._redis = None
    data_service._lock = None  # type: ignore[assignment]
    yield
    data_service._pool = None
    data_service._redis = None
    data_service._lock = None  # type: ignore[assignment]


class _FakeUser:
    def __init__(self):
        self.id = 1
        self.username = "fake"
        self.role = "admin"
        self.is_active = True


class _FakeSession:
    """直接调用 handler 时 mock AsyncSessionLocal 返回值：返回活跃 admin 用户。"""

    def __init__(self):
        self._user = _FakeUser()

    async def get(self, _model, _id):
        if _id == 1:
            return self._user
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


def test_ws_invalid_token_rejected_4401() -> None:
    """无效 token 直接关闭。"""
    with TestClient(_app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/data?token=invalid"):
                pass
        assert exc_info.value.code == 4401


def test_ws_missing_token_rejected_4401() -> None:
    with TestClient(_app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/data"):
                pass
        assert exc_info.value.code == 4401


def test_ws_unknown_user_id_rejected_4401() -> None:
    """合法 JWT 但 user_id 不存在 → 4401。直接调用 handler 避免 TestClient 跨循环池问题。"""
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.ws.endpoints import ws_data

    token = create_access_token(user_id=999999, role="user")

    class FakeWS:
        async def accept(self):
            pass

        async def close(self, code: int = 1000, reason: str = ""):
            self.closed_with = (code, reason)

        async def send_text(self, text: str):
            pass

        async def receive_text(self):
            raise RuntimeError("should not receive")

    fake = FakeWS()
    fake.closed_with = None

    class _SessionNoUser:
        async def get(self, _model, _id):
            return None  # user 不存在

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    with patch("app.ws.endpoints.AsyncSessionLocal") as mock_session:
        mock_session.return_value.__aenter__ = AsyncMock(return_value=_SessionNoUser())
        mock_session.return_value.__aexit__ = AsyncMock(return_value=None)
        asyncio.run(ws_data(fake, token=token))

    assert fake.closed_with == (4401, "")


def test_ws_unauthorized_project_sends_error() -> None:
    """合法用户 + 无项目权限：收到 cmd:error，连接保持空闲可继续收发。

    用直接调用 ws_data 内部协程的方式避免 TestClient 的循环生命周期
    干扰；patch check_subitem_access 抛 BizException。
    """
    import asyncio

    from app.core.exceptions import BizException
    from app.ws.endpoints import ws_data

    token = create_access_token(user_id=1, role="admin")

    # 用一个最小的 fake WebSocket 协议
    class FakeWS:
        def __init__(self):
            self.accepted = False
            self.closed_with: tuple[int, str] | None = None
            self.sent: list[str] = []
            self._recv_queue: list[bytes] = [b'{"type":"cmd:subscribe","subitem_id":999}']
            self._closed = False

        async def accept(self):
            self.accepted = True

        async def close(self, code: int = 1000, reason: str = ""):
            self.closed_with = (code, reason)
            self._closed = True

        async def send_text(self, text: str):
            self.sent.append(text)

        async def receive_text(self):
            if self._recv_queue:
                return self._recv_queue.pop(0).decode()
            raise BizException(code="WS_CLOSED", message="test end")

    fake = FakeWS()
    with patch("app.ws.endpoints.check_subitem_access", new_callable=AsyncMock) as mock_check:
        mock_check.side_effect = BizException(code="FORBIDDEN", message="无权", status_code=403)
        with patch("app.ws.endpoints.AsyncSessionLocal") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock(return_value=_FakeSession())
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)
            asyncio.run(ws_data(fake, token=token))

    assert fake.accepted is True
    assert any('"cmd:error"' in t and '"FORBIDDEN"' in t for t in fake.sent)


def test_ws_authorized_user_subs() -> None:
    """合法 admin → 订阅成功。"""
    import asyncio

    from app.ws.endpoints import ws_data

    token = create_access_token(user_id=1, role="admin")

    class FakeWS:
        def __init__(self):
            self.accepted = False
            self.sent: list[str] = []
            self._recv_queue: list[bytes] = [b'{"type":"cmd:subscribe","subitem_id":1}']

        async def accept(self):
            self.accepted = True

        async def close(self, code: int = 1000, reason: str = ""):
            pass

        async def send_text(self, text: str):
            self.sent.append(text)

        async def receive_text(self):
            if self._recv_queue:
                return self._recv_queue.pop(0).decode()
            # 模拟断开，避免无限循环
            from starlette.websockets import WebSocketDisconnect

            raise WebSocketDisconnect()

    fake = FakeWS()
    # admin 全局通过 check_subitem_access（admin 短路），所以不需要 mock
    with patch("app.ws.endpoints.AsyncSessionLocal") as mock_session:
        mock_session.return_value.__aenter__ = AsyncMock(return_value=_FakeSession())
        mock_session.return_value.__aexit__ = AsyncMock(return_value=None)
        asyncio.run(ws_data(fake, token=token))

    assert fake.accepted is True
    assert any('"cmd:subscribed"' in t and '"subitem_id": 1' in t for t in fake.sent)
