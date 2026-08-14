"""WebSocket 连接管理器单元测试：注册、Redis 广播、断连清理。"""

import asyncio

import pytest

from app.ws.manager import ConnectionManager


class _FakePubSub:
    def __init__(self, messages: list[dict]) -> None:
        self._messages = messages
        self.subscribed: str | None = None

    async def psubscribe(self, pattern: str) -> None:
        self.subscribed = pattern

    async def listen(self):
        for m in self._messages:
            yield m


class _FakeRedis:
    def __init__(self, messages: list[dict]) -> None:
        self._pubsub_obj = _FakePubSub(messages)
        self.closed = False

    def pubsub(self) -> _FakePubSub:
        return self._pubsub_obj

    async def aclose(self) -> None:
        self.closed = True


class _FakeWS:
    def __init__(self, fail_send: bool = False) -> None:
        self.sent: list[str] = []
        self.fail_send = fail_send

    async def send_text(self, data: str) -> None:
        if self.fail_send:
            raise RuntimeError("send failed")
        self.sent.append(data)


@pytest.mark.asyncio
async def test_connect_disconnect_registry() -> None:
    m = ConnectionManager()
    ws = _FakeWS()
    await m.connect(ws, 1)  # type: ignore[arg-type]
    await m.connect(ws, 1)  # type: ignore[arg-type]
    assert len(m.active_connections[1]) == 2
    await m.disconnect(ws, 1)  # type: ignore[arg-type]
    assert len(m.active_connections[1]) == 1
    # 不存在的连接静默
    await m.disconnect(_FakeWS(), 1)  # type: ignore[arg-type]
    assert len(m.active_connections[1]) == 1


@pytest.mark.asyncio
async def test_broadcast_listener_delivers_to_project() -> None:
    message = {
        "type": "pmessage",
        "channel": "project:3",
        "data": '{"type":"data:alert","payload":{}}',
    }
    fake_redis = _FakeRedis([message])
    m = ConnectionManager()
    m._redis = fake_redis  # type: ignore[assignment]

    ws1, ws2 = _FakeWS(), _FakeWS()
    await m.connect(ws1, 3)  # type: ignore[arg-type]
    await m.connect(ws2, 3)  # type: ignore[arg-type]

    task = asyncio.create_task(m._broadcast_listener())
    await asyncio.sleep(0.05)  # 等监听协程消费
    task.cancel()

    assert fake_redis._pubsub_obj.subscribed == "project:*"
    assert ws1.sent == [message["data"]]
    assert ws2.sent == [message["data"]]
    assert len(m.active_connections[3]) == 2  # 正常连接保留


@pytest.mark.asyncio
async def test_broadcast_listener_removes_failed_connection() -> None:
    message = {
        "type": "pmessage",
        "channel": "project:5",
        "data": "hello",
    }
    fake_redis = _FakeRedis([message])
    m = ConnectionManager()
    m._redis = fake_redis  # type: ignore[assignment]

    good, bad = _FakeWS(), _FakeWS(fail_send=True)
    await m.connect(good, 5)  # type: ignore[arg-type]
    await m.connect(bad, 5)  # type: ignore[arg-type]

    task = asyncio.create_task(m._broadcast_listener())
    await asyncio.sleep(0.05)
    task.cancel()

    # 发送失败的连接被清理，正常连接保留
    assert bad not in m.active_connections[5]
    assert good in m.active_connections[5]


@pytest.mark.asyncio
async def test_close_cancels_listener_and_closes_redis() -> None:
    fake_redis = _FakeRedis([])
    m = ConnectionManager()
    m._redis = fake_redis  # type: ignore[assignment]
    m._listener_task = asyncio.create_task(m._broadcast_listener())
    await asyncio.sleep(0.02)
    await m.close()
    assert fake_redis.closed
