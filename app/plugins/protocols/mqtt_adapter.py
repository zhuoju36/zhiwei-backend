"""MQTT 协议适配器（基于 aiomqtt）。

后台订阅协程持续接收 broker 转发的 JSON 消息，写入内部 asyncio.Queue；
read_batch 把队列里累积的全部消息一次性取出并解析为 RawReading。

期望 payload：
    {"device_code": "...", "channel_code": "...", "value": 1.23, "unit": "...",
     "timestamp": "ISO8601 可选", "quality": "good"}

设备配置示例（存入 devices.config JSONB）：

    {
      "host": "broker.local",
      "port": 1883,
      "username": "edge",
      "password": "secret",
      "topic": "shm/+/+/value",
      "queue_max": 1000,
      "device_code": "GW-MQTT-01",
      "use_tls": false
    }
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import aiomqtt

from app.plugins.protocols.base import ProtocolAdapter, ProtocolConfig, RawReading

logger = logging.getLogger(__name__)


class MqttAdapter(ProtocolAdapter):
    name = "mqtt"
    version = "1.0.0"
    supports_batch = True

    def __init__(self, config: ProtocolConfig):
        super().__init__(config)
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=int(config.extra.get("queue_max", 1000))
        )
        self._listener_task: asyncio.Task[None] | None = None
        self._client: aiomqtt.Client | None = None

    async def connect(self) -> None:
        kwargs: dict[str, Any] = {
            "hostname": self.config.host,
            "port": self.config.port or 1883,
        }
        username = self.config.extra.get("username")
        password = self.config.extra.get("password")
        if username:
            kwargs["username"] = username
            kwargs["password"] = password
        if self.config.extra.get("use_tls"):
            kwargs["tls_context"] = None  # 默认 TLS；具体证书按需扩展

        self._client = aiomqtt.Client(**kwargs)
        topic = self.config.extra.get("topic", "#")
        self._listener_task = asyncio.create_task(self._listen(topic))
        # 给客户端一点点连接时间（aiomqtt 异步无 connect 显式步骤，靠 __aenter__）
        await asyncio.sleep(0)
        self._connected = True

    async def _listen(self, topic: str) -> None:
        assert self._client is not None
        try:
            async with self._client as client:
                await client.subscribe(topic)
                async for message in client.messages:
                    try:
                        payload = json.loads(message.payload)
                        if isinstance(payload, dict):
                            self._enqueue(payload)
                        else:
                            logger.warning("MQTT 跳过非字典 payload: %r", payload)
                    except json.JSONDecodeError:
                        logger.warning("MQTT payload 非 JSON: %r", message.payload)
                    except asyncio.QueueFull:
                        logger.warning("MQTT 队列已满，丢弃消息")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("MQTT 订阅协程异常")

    def _enqueue(self, payload: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("MQTT 队列已满，丢弃 payload: %s", payload.get("channel_code"))

    async def read_batch(self) -> list[RawReading]:
        readings: list[RawReading] = []
        while True:
            try:
                payload = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            reading = self._parse(payload)
            if reading is not None:
                readings.append(reading)
        return readings

    @staticmethod
    def _parse(payload: dict[str, Any]) -> RawReading | None:
        try:
            device_code = payload["device_code"]
            channel_code = payload["channel_code"]
            value = float(payload["value"])
        except (KeyError, TypeError, ValueError):
            logger.warning("MQTT payload 缺字段或值无效: %s", payload)
            return None
        ts_raw = payload.get("timestamp")
        if isinstance(ts_raw, str):
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                ts = datetime.now(UTC)
        else:
            ts = datetime.now(UTC)
        return RawReading(
            device_code=device_code,
            channel_code=channel_code,
            timestamp=ts,
            value=value,
            unit=str(payload.get("unit", "")),
            quality=str(payload.get("quality", "good")),
            extra={
                k: v
                for k, v in payload.items()
                if k not in {"device_code", "channel_code", "value", "unit", "timestamp", "quality"}
            },
        )

    async def disconnect(self) -> None:
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except (asyncio.CancelledError, Exception):
                pass
        self._listener_task = None
        self._client = None
        # 清空队列
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._connected = False
