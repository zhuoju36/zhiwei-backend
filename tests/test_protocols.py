"""协议适配器注册表与 HTTP JSON 适配器单元测试。"""

import httpx
import pytest

from app.plugins.protocols.base import ProtocolConfig, RawReading
from app.plugins.protocols.http_json_adapter import HttpJsonAdapter
from app.plugins.protocols.registry import AdapterRegistry


def test_registry_discovers_http_json() -> None:
    assert "http_json" in AdapterRegistry.names()
    cls = AdapterRegistry.get("http_json")
    assert cls is HttpJsonAdapter


def test_registry_unknown_returns_none() -> None:
    assert AdapterRegistry.get("no_such_protocol") is None


async def test_http_json_read_batch() -> None:
    payload = [
        {"device_code": "GW-001", "channel_code": "ACC-X", "value": 0.5, "unit": "m/s2"},
        {"device_code": "GW-001", "channel_code": "ACC-Y", "value": -0.2},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    adapter = HttpJsonAdapter(ProtocolConfig(host="http://mock", extra={"path": "/readings"}))
    adapter._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mock"
    )

    readings = await adapter.read_batch()
    assert len(readings) == 2
    assert all(isinstance(r, RawReading) for r in readings)
    assert readings[0].device_code == "GW-001"
    assert readings[0].value == 0.5
    assert readings[1].quality == "good"
    await adapter.disconnect()


async def test_http_json_http_error_raises_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = HttpJsonAdapter(ProtocolConfig(host="http://mock"))
    adapter._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mock"
    )
    with pytest.raises(ConnectionError):
        await adapter.read_batch()
