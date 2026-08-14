"""测点业务逻辑（v0.8b 起：point = 物理位置，alert_rules 移到 channel）。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.models.device import Device
from app.models.point import Point
from app.schemas.point import PointCreate, PointUpdate


class PointService:
    @staticmethod
    async def get(db: AsyncSession, point_id: int) -> Point:
        point = await db.get(Point, point_id)
        if point is None:
            raise BizException(code="POINT_NOT_FOUND", message="测点不存在", status_code=404)
        return point

    @staticmethod
    async def list_by_device(
        db: AsyncSession, device_id: int, page: int, size: int
    ) -> tuple[list[Point], int]:
        total = (
            await db.execute(
                select(func.count()).select_from(Point).where(Point.device_id == device_id)
            )
        ).scalar_one()
        rows = (
            (
                await db.execute(
                    select(Point)
                    .where(Point.device_id == device_id)
                    .order_by(Point.id)
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    @staticmethod
    async def list_by_subitem(
        db: AsyncSession, subitem_id: int, page: int, size: int
    ) -> tuple[list[Point], int]:
        """通过 JOIN device 一次性查子项下所有测点。"""
        total = (
            await db.execute(
                select(func.count())
                .select_from(Point)
                .join(Device, Device.id == Point.device_id)
                .where(Device.subitem_id == subitem_id)
            )
        ).scalar_one()
        rows = (
            (
                await db.execute(
                    select(Point)
                    .join(Device, Device.id == Point.device_id)
                    .where(Device.subitem_id == subitem_id)
                    .order_by(Point.id)
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    @staticmethod
    async def create(db: AsyncSession, payload: PointCreate) -> Point:
        device = await db.get(Device, payload.device_id)
        if device is None:
            raise BizException(code="DEVICE_NOT_FOUND", message="设备不存在", status_code=404)
        # 同 device 内 point_code 唯一
        existing = (
            await db.execute(
                select(Point).where(
                    Point.device_id == payload.device_id,
                    Point.point_code == payload.point_code,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise BizException(code="POINT_CODE_EXISTS", message="测点编码已存在", status_code=409)
        point = Point(
            device_id=payload.device_id,
            point_code=payload.point_code,
            point_name=payload.point_name,
            point_type=payload.point_type,
            position=payload.position,
        )
        db.add(point)
        await db.flush()
        return point

    @staticmethod
    async def update(db: AsyncSession, point_id: int, payload: PointUpdate) -> Point:
        point = await PointService.get(db, point_id)
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(point, field, value)
        await db.flush()
        return point

    @staticmethod
    async def delete(db: AsyncSession, point_id: int) -> None:
        point = await PointService.get(db, point_id)
        await db.delete(point)
        await db.flush()
