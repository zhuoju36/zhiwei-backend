"""传感器管理路由（挂在 point 下）。"""

from fastapi import Query, status

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.middleware import create_router
from app.dependencies import (
    AdminUser,
    CurrentUser,
    DbSession,
    check_subitem_access,
    check_subitem_write_access,
)
from app.models.device import Device
from app.models.point import Point
from app.schemas.base import PageSchema
from app.schemas.sensor import SensorCreate, SensorOut, SensorUpdate
from app.services.point_service import PointService
from app.services.sensor_service import SensorService

router = create_router(prefix="/sensors", tags=["传感器"])


@router.get("", response_model=PageSchema[SensorOut])
async def list_sensors(
    db: DbSession,
    current_user: CurrentUser,
    point_id: int = Query(..., description="按测点筛选"),
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageSchema[SensorOut]:
    point = await PointService.get(db, point_id)
    device = await db.get(Device, point.device_id)
    await check_subitem_access(db, current_user, device.subitem_id)
    rows, total = await SensorService.list_by_point(db, point_id, page, size)
    return PageSchema(
        total=total,
        page=page,
        size=size,
        items=[SensorOut.model_validate(s) for s in rows],
    )


@router.post("", response_model=SensorOut, status_code=status.HTTP_201_CREATED)
async def create_sensor(
    payload: SensorCreate, db: DbSession, current_user: CurrentUser
) -> SensorOut:
    point = await PointService.get(db, payload.point_id)
    device = await db.get(Device, point.device_id)
    await check_subitem_write_access(db, current_user, device.subitem_id)
    sensor = await SensorService.create(db, payload)
    return SensorOut.model_validate(sensor)


@router.get("/{sensor_id}", response_model=SensorOut)
async def get_sensor(sensor_id: int, db: DbSession, current_user: CurrentUser) -> SensorOut:
    sensor = await SensorService.get(db, sensor_id)
    point = await db.get(Point, sensor.point_id)
    device = await db.get(Device, point.device_id)
    await check_subitem_access(db, current_user, device.subitem_id)
    return SensorOut.model_validate(sensor)


@router.put("/{sensor_id}", response_model=SensorOut)
async def update_sensor(
    sensor_id: int,
    payload: SensorUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> SensorOut:
    sensor = await SensorService.get(db, sensor_id)
    point = await db.get(Point, sensor.point_id)
    device = await db.get(Device, point.device_id)
    await check_subitem_write_access(db, current_user, device.subitem_id)
    updated = await SensorService.update(db, sensor_id, payload)
    return SensorOut.model_validate(updated)


@router.delete("/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sensor(sensor_id: int, db: DbSession, admin: AdminUser) -> None:
    await SensorService.delete(db, sensor_id)
