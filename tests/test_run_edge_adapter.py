"""边缘网关参考脚本契约测试：run_edge_adapter 构造的 ingest payload 必须与
服务端 ReadingIn 契约一致（v0.8b 后按 device_code + channel_code 寻址）。

防止契约演进（如 RawReading 字段改名）时边缘脚本漏改——此前的
point_code → channel_code 重构就曾漏掉 run_edge_adapter。
"""

from datetime import UTC, datetime

import httpx
import pytest

from app.plugins.protocols.base import RawReading
from app.schemas.data import ReadingIn
from scripts.run_edge_adapter import build_adapter, push_ingest


class _FakeClient:
    """记录最后一次 POST 的 payload，模拟 httpx.AsyncClient.post。"""

    def __init__(self) -> None:
        self.payload: dict | None = None

    async def post(self, url: str, json: dict, headers: dict) -> httpx.Response:
        self.payload = json
        return httpx.Response(200, json={"written": 1})


@pytest.mark.asyncio
async def test_push_ingest_payload_matches_readingin_contract() -> None:
    reading = RawReading(
        device_code="GW-001",
        channel_code="ACC-X",
        timestamp=datetime(2026, 8, 14, 12, 0, 0, tzinfo=UTC),
        value=0.35,
        unit="m/s2",
        quality="good",
        extra={"seq": 1},
    )
    client = _FakeClient()
    await push_ingest(client, "http://api", "edge-secret-key", [reading])

    assert client.payload is not None
    item = client.payload["readings"][0]
    # 反序列化成功即契约一致
    validated = ReadingIn.model_validate(item)
    assert validated.device_code == "GW-001"
    assert validated.channel_code == "ACC-X"
    assert validated.value == 0.35
    assert validated.extra == {"seq": 1}


def test_build_adapter_accepts_flat_config() -> None:
    """Device.config 为扁平结构（host/port/registers...），适配器从 extra 读取。"""
    adapter = build_adapter("modbus_tcp", "GW-001", {"host": "127.0.0.1", "port": 5020})
    assert adapter.config.host == "127.0.0.1"
    assert adapter.config.port == 5020
    # register_map 已不使用（无适配器读取），extra 承载完整配置
    assert adapter.config.register_map == {}
    assert adapter.config.extra == {"host": "127.0.0.1", "port": 5020, "device_code": "GW-001"}
