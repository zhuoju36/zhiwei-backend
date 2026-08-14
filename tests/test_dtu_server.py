"""DTU 监听接入集成测试：TcpServerManager 接收 RTU 帧 → 入库。

模拟 DTU 客户端连接监听端口并推送 Modbus RTU 响应帧，
验证经 batch_ingest 链路写入 readings（真实 DB/Redis）。
"""

import asyncio
import uuid

import pytest
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.dtus.server import TcpServerManager
from app.models.channel import Channel
from app.models.device import Device
from app.models.project import Project
from app.models.sensor import Sensor
from app.services.data_service import get_pool
from tests.test_modbus_rtu_framer import rtu_response


async def _make_dtu_chain() -> tuple[int, int, int]:
    """建 project → device(modbus_rtu_over_tcp, port=0) → sensor → channel。"""
    s = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        sub = Project(name=f"dtu-test-{s}")
        db.add(sub)
        await db.flush()
        device = Device(
            project_id=sub.id,
            device_code=f"GW-DTU-{s}",
            protocol="modbus_rtu_over_tcp",
            config={
                "host": "127.0.0.1",
                "port": 0,  # 随机端口
                "slave_id": 1,
                "device_code": f"GW-DTU-{s}",
                "registers": [
                    {
                        "address": 0,
                        "count": 1,
                        "data_type": "uint16",
                        "channel_code": "TEMP",
                        "scale": 0.1,
                        "unit": "°C",
                    },
                ],
            },
        )
        db.add(device)
        await db.flush()
        await db.flush()
        sensor = Sensor(device_id=device.id, sensor_code=f"S-{s}")
        db.add(sensor)
        await db.flush()
        channel = Channel(sensor_id=sensor.id, channel_code="TEMP", unit="°C", sampling_rate=1)
        db.add(channel)
        await db.commit()
        await db.refresh(channel)
        return sub.id, device.id, channel.id


async def _cleanup(proj_id: int, dev_id: int, ch_id: int) -> None:
    async with AsyncSessionLocal() as db:
        from app.models.reading import Reading

        await db.execute(delete(Reading).where(Reading.channel_id == ch_id))
        await db.execute(delete(Channel).where(Channel.id == ch_id))
        await db.execute(delete(Sensor).where(Sensor.device_id == dev_id))
        await db.execute(delete(Device).where(Device.id == dev_id))
        await db.execute(delete(Project).where(Project.id == proj_id))
        await db.commit()


async def _count_readings(channel_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT count(*) FROM readings WHERE channel_id = $1", channel_id
        )


@pytest.mark.asyncio
async def test_dtu_frame_received_and_ingested() -> None:
    sub_id, dev_id, ch_id = await _make_dtu_chain()
    manager = TcpServerManager(batch_size=10, flush_interval_s=0.2)
    try:
        await manager.start()
        assert len(manager._listeners) == 1
        port = manager._listeners[0]["port"]
        assert port > 0

        # 模拟 DTU 客户端推送一帧（读保持寄存器响应，TEMP = 0x0190 * 0.1 = 40.0）
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(rtu_response(1, [0x0190]))
        await writer.drain()
        writer.close()

        # 等待消费者攒批入库
        count = 0
        for _ in range(50):
            count = await _count_readings(ch_id)
            if count:
                break
            await asyncio.sleep(0.1)
        assert count == 1

        # 校验值
        pool = await get_pool()
        async with pool.acquire() as conn:
            value = await conn.fetchval("SELECT value FROM readings WHERE channel_id = $1", ch_id)
        assert abs(value - 40.0) < 1e-6
    finally:
        await manager.stop()
        await _cleanup(sub_id, dev_id, ch_id)
