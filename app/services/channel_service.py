"""通道业务逻辑。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.models.channel import Channel
from app.models.sensor import Sensor
from app.schemas.sensor import ChannelCreate, ChannelUpdate


class ChannelService:
    @staticmethod
    async def get(db: AsyncSession, channel_id: int) -> Channel:
        channel = await db.get(Channel, channel_id)
        if channel is None:
            raise BizException(code="CHANNEL_NOT_FOUND", message="通道不存在", status_code=404)
        return channel

    @staticmethod
    async def list_by_sensor(
        db: AsyncSession, sensor_id: int, page: int, size: int
    ) -> tuple[list[Channel], int]:
        total = (
            await db.execute(
                select(func.count()).select_from(Channel).where(Channel.sensor_id == sensor_id)
            )
        ).scalar_one()
        rows = (
            (
                await db.execute(
                    select(Channel)
                    .where(Channel.sensor_id == sensor_id)
                    .order_by(Channel.id)
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    @staticmethod
    async def list_by_device(
        db: AsyncSession, device_id: int, page: int, size: int
    ) -> tuple[list[Channel], int]:
        """按 device 列出全部 channel（JOIN point → sensor → channel）。"""
        from app.models.point import Point

        total = (
            await db.execute(
                select(func.count())
                .select_from(Channel)
                .join(Sensor, Sensor.id == Channel.sensor_id)
                .join(Point, Point.id == Sensor.point_id)
                .where(Point.device_id == device_id)
            )
        ).scalar_one()
        rows = (
            (
                await db.execute(
                    select(Channel)
                    .join(Sensor, Sensor.id == Channel.sensor_id)
                    .join(Point, Point.id == Sensor.point_id)
                    .where(Point.device_id == device_id)
                    .order_by(Channel.id)
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    @staticmethod
    async def create(db: AsyncSession, payload: ChannelCreate) -> Channel:
        sensor = await db.get(Sensor, payload.sensor_id)
        if sensor is None:
            raise BizException(code="SENSOR_NOT_FOUND", message="传感器不存在", status_code=404)
        existing = (
            await db.execute(
                select(Channel).where(
                    Channel.sensor_id == payload.sensor_id,
                    Channel.channel_code == payload.channel_code,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise BizException(
                code="CHANNEL_CODE_EXISTS", message="通道编码已存在", status_code=409
            )
        rules_dump = [r.model_dump() for r in payload.alert_rules] if payload.alert_rules else None
        channel = Channel(
            sensor_id=payload.sensor_id,
            channel_code=payload.channel_code,
            channel_type=payload.channel_type,
            unit=payload.unit,
            sampling_rate=payload.sampling_rate,
            position_offset=payload.position_offset,
            axis=payload.axis,
            alert_rules=rules_dump,
        )
        db.add(channel)
        await db.flush()
        return channel

    @staticmethod
    async def update(db: AsyncSession, channel_id: int, payload: ChannelUpdate) -> Channel:
        channel = await ChannelService.get(db, channel_id)
        data = payload.model_dump(exclude_unset=True)
        if "alert_rules" in data and data["alert_rules"] is not None:
            data["alert_rules"] = [r if isinstance(r, dict) else r for r in data["alert_rules"]]
        for field, value in data.items():
            setattr(channel, field, value)
        await db.flush()
        return channel

    @staticmethod
    async def delete(db: AsyncSession, channel_id: int) -> None:
        channel = await ChannelService.get(db, channel_id)
        await db.delete(channel)
        await db.flush()
