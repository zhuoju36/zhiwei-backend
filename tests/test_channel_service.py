"""通道服务单元测试（真实 DB）：list_by_device / create 校验 / update / delete。"""

import uuid

import pytest
from sqlalchemy import delete, select

from app.core.exceptions import BizException
from app.database import AsyncSessionLocal
from app.models.channel import Channel
from app.models.device import Device
from app.models.project import Project
from app.models.sensor import Sensor
from app.schemas.sensor import ChannelCreate, ChannelUpdate
from app.services.channel_service import ChannelService


async def _make_chain() -> tuple[int, int, int, int]:
    """建 project → device → sensor → channel 链。

    返回 (project_id, device_id, sensor_id, channel_id)。
    """
    s = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        project = Project(name=f"ch-svc-{s}")
        db.add(project)
        await db.flush()
        device = Device(
            project_id=project.id, device_code=f"GW-{s}", protocol="http_json", config={}
        )
        db.add(device)
        await db.flush()
        sensor = Sensor(device_id=device.id, sensor_code=f"S-{s}")
        db.add(sensor)
        await db.flush()
        channel = Channel(sensor_id=sensor.id, channel_code="ACC-X", sampling_rate=100)
        db.add(channel)
        await db.commit()
        await db.refresh(channel)
        return project.id, device.id, sensor.id, channel.id


async def _cleanup(proj_id: int, dev_id: int) -> None:
    async with AsyncSessionLocal() as db:
        sensors = (
            (await db.execute(select(Sensor).where(Sensor.device_id == dev_id))).scalars().all()
        )
        for sn in sensors:
            await db.execute(delete(Channel).where(Channel.sensor_id == sn.id))
        await db.execute(delete(Sensor).where(Sensor.device_id == dev_id))
        await db.execute(delete(Device).where(Device.id == dev_id))
        await db.execute(delete(Project).where(Project.id == proj_id))
        await db.commit()


@pytest.mark.asyncio
async def test_list_by_device() -> None:
    proj_id, dev_id, sensor_id, ch_id = await _make_chain()
    # 再补一个通道
    async with AsyncSessionLocal() as db:
        db.add(Channel(sensor_id=sensor_id, channel_code="ACC-Y"))
        await db.commit()
    try:
        async with AsyncSessionLocal() as db:
            rows, total = await ChannelService.list_by_device(db, dev_id, 1, 20)
        assert total == 2
        assert {r.channel_code for r in rows} == {"ACC-X", "ACC-Y"}
    finally:
        await _cleanup(proj_id, dev_id)


@pytest.mark.asyncio
async def test_create_channel_and_duplicate_rejected() -> None:
    proj_id, dev_id, sensor_id, _ = await _make_chain()
    try:
        async with AsyncSessionLocal() as db:
            ch = await ChannelService.create(
                db,
                ChannelCreate(
                    sensor_id=sensor_id,
                    channel_code="TEMP",
                    unit="°C",
                    sampling_rate=1,
                    alert_rules=[
                        {
                            "operator": "gt",
                            "threshold": 30.0,
                            "level": "warning",
                        }
                    ],
                ),
            )
            assert ch.channel_code == "TEMP"
            assert ch.unit == "°C"
            assert ch.alert_rules[0]["threshold"] == 30.0
            # 同 sensor 重复 channel_code → 409
            with pytest.raises(BizException) as exc:
                await ChannelService.create(
                    db, ChannelCreate(sensor_id=sensor_id, channel_code="TEMP")
                )
            assert exc.value.code == "CHANNEL_CODE_EXISTS"
            # 传感器不存在 → 404
            with pytest.raises(BizException) as exc2:
                await ChannelService.create(db, ChannelCreate(sensor_id=999999, channel_code="X"))
            assert exc2.value.code == "SENSOR_NOT_FOUND"
    finally:
        await _cleanup(proj_id, dev_id)


@pytest.mark.asyncio
async def test_update_and_delete_channel() -> None:
    proj_id, dev_id, sensor_id, ch_id = await _make_chain()
    try:
        async with AsyncSessionLocal() as db:
            updated = await ChannelService.update(
                db, ch_id, ChannelUpdate(unit="m/s2", sampling_rate=200)
            )
            assert updated.unit == "m/s2"
            assert updated.sampling_rate == 200
            assert updated.channel_code == "ACC-X"  # 未更新字段保持

            await ChannelService.delete(db, ch_id)
            with pytest.raises(BizException) as exc:
                await ChannelService.get(db, ch_id)
            assert exc.value.code == "CHANNEL_NOT_FOUND"
    finally:
        await _cleanup(proj_id, dev_id)
