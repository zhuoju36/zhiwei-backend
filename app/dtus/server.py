"""DTU 监听服务器：TcpServerManager + 进程入口。

数据链路：DTU → asyncio TCP server → Modbus RTU 帧解析 → ReadingIn 缓冲队列
        → batch_ingest（COPY 直写 readings + Redis 实时推送 + Celery 告警）

设计要点：
- 一监听端口 = 一台设备（Device.config.port 为监听端口，host 默认 0.0.0.0）
- 字节流缓冲 + 粘包/半包切分在连接处理层；适配器只管"帧 → RawReading"
- 缓冲队列 + 攒批 flush：天然提供批量写入与优雅停机排空
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.device import Device
from app.plugins.protocols.base import ProtocolConfig, RawReading
from app.plugins.protocols.modbus_rtu_tcp import ModbusRtuOverTcpAdapter, split_rtu_frames
from app.schemas.data import ReadingIn
from app.services.data_service import batch_ingest, get_pool

logger = logging.getLogger(__name__)


def _to_reading_in(r: RawReading) -> ReadingIn:
    """RawReading → ReadingIn（dtu 进程直接复用 data_service 的接入链路）。"""
    try:
        from app.core.constants import Quality

        quality = Quality(r.quality)
    except ValueError:
        quality = Quality.GOOD
    return ReadingIn(
        device_code=r.device_code,
        channel_code=r.channel_code,
        timestamp=r.timestamp,
        value=r.value,
        unit=r.unit,
        quality=quality,
        extra=r.extra,
    )


class TcpServerManager:
    """管理所有 DTU 监听端口、连接与入库消费者。"""

    def __init__(self, batch_size: int = 100, flush_interval_s: float = 0.5) -> None:
        self._batch_size = batch_size
        self._flush_interval_s = flush_interval_s
        self._servers: list[asyncio.Server] = []
        self._queue: asyncio.Queue[ReadingIn] = asyncio.Queue()
        self._consumer_task: asyncio.Task | None = None
        self._stopping = False
        self._listeners: list[dict[str, Any]] = []  # 日志用：{port, device_code, adapter}

    async def start(self) -> None:
        """从 DB 拉取监听型设备并启动各端口监听。"""
        await get_pool()  # 预热 asyncpg 池（batch_ingest 依赖）
        devices = await self._load_listen_devices()
        if not devices:
            logger.warning("没有 protocol=modbus_rtu_over_tcp 的设备，DTU 监听未启动")
            return
        for device in devices:
            await self._start_listener(device)
        self._consumer_task = asyncio.create_task(self._consumer())
        for info in self._listeners:
            logger.info("DTU 监听已启动: port=%s device_code=%s", info["port"], info["device_code"])

    async def _load_listen_devices(self) -> list[Device]:
        async with AsyncSessionLocal() as db:
            rows = (
                (await db.execute(select(Device).where(Device.protocol == "modbus_rtu_over_tcp")))
                .scalars()
                .all()
            )
            return list(rows)

    async def _start_listener(self, device: Device) -> None:
        config = dict(device.config or {})
        config.setdefault("device_code", device.device_code)
        raw_port = config.get("port")
        if raw_port is None:
            logger.warning("设备 %s 未配置监听 port，跳过", device.device_code)
            return
        port = int(raw_port)
        host = str(config.get("host", "0.0.0.0"))
        adapter = ModbusRtuOverTcpAdapter(ProtocolConfig(host=host, port=port, extra=config))
        server = await asyncio.start_server(
            lambda r, w: self._handle_conn(adapter, r, w), host, port
        )
        # port=0 时由内核分配随机端口，取实际监听端口（测试/调试用）
        actual_port = port
        if server.sockets:
            actual_port = server.sockets[0].getsockname()[1]
        self._servers.append(server)
        self._listeners.append(
            {"port": actual_port, "device_code": device.device_code, "adapter": adapter}
        )

    async def _handle_conn(self, adapter: ModbusRtuOverTcpAdapter, reader, writer) -> None:
        peer = writer.get_extra_info("peername")
        buffer = bytearray()
        logger.info("DTU 连接建立: %s (device=%s)", peer, adapter._device_code)
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buffer.extend(chunk)
                frames, buffer = split_rtu_frames(bytes(buffer))
                if not frames:
                    continue
                for frame in frames:
                    for reading in adapter._decode_frame(frame):
                        self._queue.put_nowait(_to_reading_in(reading))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("DTU 连接处理异常: %s", peer)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.info("DTU 连接关闭: %s", peer)

    async def _consumer(self) -> None:
        """攒批消费：每 flush_interval 秒或攒满 batch_size 调一次 batch_ingest。"""
        loop = asyncio.get_running_loop()
        while True:
            batch: list[ReadingIn] = []
            deadline = loop.time() + self._flush_interval_s
            while len(batch) < self._batch_size and loop.time() < deadline:
                try:
                    item = await asyncio.wait_for(
                        self._queue.get(), timeout=max(deadline - loop.time(), 0.01)
                    )
                except TimeoutError:
                    break
                batch.append(item)
            if batch:
                try:
                    written = await batch_ingest(batch)
                    logger.debug("DTU 批次入库 %d 条（写入 %d）", len(batch), written)
                except Exception:
                    logger.exception("DTU 批次入库失败（%d 条丢弃）", len(batch))
            if self._stopping and self._queue.empty():
                break

    async def stop(self) -> None:
        """优雅停机：停 accept → 排空缓冲队列 → 取消消费者。"""
        self._stopping = True
        for server in self._servers:
            server.close()
        for server in self._servers:
            await server.wait_closed()
        if self._consumer_task is not None:
            await self._consumer_task
        logger.info("DTU 监听已停止")


async def _run() -> None:
    manager = TcpServerManager(
        batch_size=settings.dtu_batch_size, flush_interval_s=settings.dtu_flush_interval_s
    )
    await manager.start()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass
    await stop_event.wait()
    await manager.stop()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
