"""测点业务逻辑。"""

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
    async def list_by_project(
        db: AsyncSession, project_id: int, page: int, size: int
    ) -> tuple[list[Point], int]:
        """通过 JOIN device 一次性查项目下所有测点。"""
        total = (
            await db.execute(
                select(func.count())
                .select_from(Point)
                .join(Device, Device.id == Point.device_id)
                .where(Device.project_id == project_id)
            )
        ).scalar_one()
        rows = (
            (
                await db.execute(
                    select(Point)
                    .join(Device, Device.id == Point.device_id)
                    .where(Device.project_id == project_id)
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
        rules_dump = [r.model_dump() for r in payload.alert_rules] if payload.alert_rules else None
        point = Point(
            device_id=payload.device_id,
            point_code=payload.point_code,
            point_name=payload.point_name,
            point_type=payload.point_type,
            unit=payload.unit,
            position=payload.position,
            alert_rules=rules_dump,
            sampling_rate=payload.sampling_rate,
        )
        db.add(point)
        await db.flush()
        return point

    @staticmethod
    async def update(db: AsyncSession, point_id: int, payload: PointUpdate) -> Point:
        point = await PointService.get(db, point_id)
        data = payload.model_dump(exclude_unset=True)
        if "alert_rules" in data and data["alert_rules"] is not None:
            data["alert_rules"] = [r if isinstance(r, dict) else r for r in data["alert_rules"]]
        for field, value in data.items():
            setattr(point, field, value)
        await db.flush()
        return point

    @staticmethod
    async def delete(db: AsyncSession, point_id: int) -> None:
        point = await PointService.get(db, point_id)
        await db.delete(point)
        await db.flush()

    @staticmethod
    async def list_alert_rules_batch(
        db: AsyncSession, point_ids: list[int]
    ) -> dict[int, list[dict]]:
        """批量取测点的 alert_rules（供告警任务使用，避免 N+1）。"""
        if not point_ids:
            return {}
        rows = (
            await db.execute(select(Point.id, Point.alert_rules).where(Point.id.in_(point_ids)))
        ).all()
        return {pid: (rules or []) for pid, rules in rows}
