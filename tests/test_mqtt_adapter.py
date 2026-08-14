"""MQTT 适配器单元测试。"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.plugins.protocols.base import ProtocolConfig
from app.plugins.protocols.mqtt_adapter import MqttAdapter


def _good_payload() -> dict:
    return {
        "device_code": "GW-MQTT",
        "channel_code": "ACC-X",
        "value": 0.42,
        "unit": "m/s2",
        "quality": "good",
        "timestamp": "2026-08-13T12:00:00+00:00",
    }


def test_parse_valid_payload() -> None:
    reading = MqttAdapter._parse(_good_payload())
    assert reading is not None
    assert reading.device_code == "GW-MQTT"
    assert reading.channel_code == "ACC-X"
    assert reading.value == 0.42
    assert reading.unit == "m/s2"
    assert reading.quality == "good"
    assert reading.timestamp == datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)
    # extra 中不应包含必填字段
    assert "device_code" not in reading.extra


def test_parse_missing_device_code() -> None:
    p = _good_payload()
    del p["device_code"]
    assert MqttAdapter._parse(p) is None


def test_parse_missing_channel_code() -> None:
    p = _good_payload()
    del p["channel_code"]
    assert MqttAdapter._parse(p) is None


def test_parse_invalid_value() -> None:
    p = _good_payload()
    p["value"] = "not-a-number"
    assert MqttAdapter._parse(p) is None


def test_parse_invalid_timestamp_falls_back_to_now() -> None:
    p = _good_payload()
    p["timestamp"] = "not-a-timestamp"
    reading = MqttAdapter._parse(p)
    assert reading is not None
    assert isinstance(reading.timestamp, datetime)


async def test_read_batch_drains_queue() -> None:
    """read_batch 把队列里全部消息一次取出。"""
    adapter = MqttAdapter(ProtocolConfig(host="broker", extra={"device_code": "GW"}))
    await adapter._queue.put(_good_payload())
    await adapter._queue.put({**_good_payload(), "channel_code": "ACC-Y", "value": 0.5})
    readings = await adapter.read_batch()
    assert len(readings) == 2
    assert readings[0].channel_code == "ACC-X"
    assert readings[1].channel_code == "ACC-Y"
    assert adapter._queue.empty()


async def test_read_batch_empty_queue_returns_empty() -> None:
    adapter = MqttAdapter(ProtocolConfig(host="broker"))
    assert await adapter.read_batch() == []


async def test_enqueue_full_queue_drops() -> None:
    """队列满时 put_nowait 抛 QueueFull，_enqueue 应捕获并记日志。"""
    adapter = MqttAdapter(ProtocolConfig(host="broker", extra={"queue_max": 1}))
    await adapter._queue.put({"a": 1})
    adapter._enqueue({"a": 2})  # 不应抛异常，应被日志丢弃
    assert adapter._queue.qsize() == 1


async def test_disconnect_cancels_listener_and_clears_queue() -> None:
    adapter = MqttAdapter(ProtocolConfig(host="broker"))
    fake_task = MagicMock()
    fake_task.done.return_value = False
    adapter._listener_task = fake_task

    await adapter._queue.put({"x": 1})

    async def fake_await():
        return None

    fake_task.__await__ = lambda self: fake_await().__await__()
    with patch.object(asyncio.Task, "cancel", lambda self: None):
        await adapter.disconnect()
    assert adapter._listener_task is None
    assert adapter._client is None
    assert adapter._queue.empty()
