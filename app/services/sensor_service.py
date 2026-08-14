"""传感器业务逻辑。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.models.point import Point
from app.models.sensor import Sensor
from app.schemas.sensor import SensorCreate, SensorUpdate


class SensorService:
    @staticmethod
    async def get(db: AsyncSession, sensor_id: int) -> Sensor:
        sensor = await db.get(Sensor, sensor_id)
        if sensor is None:
            raise BizException(code="SENSOR_NOT_FOUND", message="传感器不存在", status_code=404)
        return sensor

    @staticmethod
    async def list_by_point(
        db: AsyncSession, point_id: int, page: int, size: int
    ) -> tuple[list[Sensor], int]:
        total = (
            await db.execute(
                select(func.count()).select_from(Sensor).where(Sensor.point_id == point_id)
            )
        ).scalar_one()
        rows = (
            (
                await db.execute(
                    select(Sensor)
                    .where(Sensor.point_id == point_id)
                    .order_by(Sensor.id)
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    @staticmethod
    async def create(db: AsyncSession, payload: SensorCreate) -> Sensor:
        point = await db.get(Point, payload.point_id)
        if point is None:
            raise BizException(code="POINT_NOT_FOUND", message="测点不存在", status_code=404)
        existing = (
            await db.execute(
                select(Sensor).where(
                    Sensor.point_id == payload.point_id,
                    Sensor.sensor_code == payload.sensor_code,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise BizException(
                code="SENSOR_CODE_EXISTS", message="传感器编码已存在", status_code=409
            )
        sensor = Sensor(
            point_id=payload.point_id,
            sensor_code=payload.sensor_code,
            model=payload.model,
            manufacturer=payload.manufacturer,
            install_date=payload.install_date,
            last_calibration=payload.last_calibration,
            metadata_=payload.metadata,
        )
        db.add(sensor)
        await db.flush()
        return sensor

    @staticmethod
    async def update(db: AsyncSession, sensor_id: int, payload: SensorUpdate) -> Sensor:
        sensor = await SensorService.get(db, sensor_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            if field == "metadata":
                sensor.metadata_ = value
            else:
                setattr(sensor, field, value)
        await db.flush()
        return sensor

    @staticmethod
    async def delete(db: AsyncSession, sensor_id: int) -> None:
        sensor = await SensorService.get(db, sensor_id)
        await db.delete(sensor)
        await db.flush()
