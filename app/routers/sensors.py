"""传感器管理路由（v0.9 起挂在 device 下，原 point 与 sensor 合一）。"""

from fastapi import Query, status

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.exceptions import BizException
from app.core.middleware import create_router
from app.dependencies import (
    AdminUser,
    CurrentUser,
    DbSession,
    check_project_access,
    check_project_write_access,
)
from app.models.device import Device
from app.schemas.base import PageSchema
from app.schemas.sensor import SensorCreate, SensorOut, SensorUpdate
from app.services.device_service import DeviceService
from app.services.sensor_service import SensorService

router = create_router(prefix="/sensors", tags=["传感器"])


@router.get("", response_model=PageSchema[SensorOut])
async def list_sensors(
    db: DbSession,
    current_user: CurrentUser,
    device_id: int | None = Query(None, description="按设备筛选"),
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageSchema[SensorOut]:
    if device_id is None:
        raise BizException(code="BAD_REQUEST", message="device_id 必传", status_code=400)
    device = await DeviceService.get(db, device_id)
    await check_project_access(db, current_user, device.project_id)
    rows, total = await SensorService.list_by_device(db, device_id, page, size)
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
    device = await DeviceService.get(db, payload.device_id)
    await check_project_write_access(db, current_user, device.project_id)
    sensor = await SensorService.create(db, payload)
    return SensorOut.model_validate(sensor)


@router.get("/{sensor_id}", response_model=SensorOut)
async def get_sensor(sensor_id: int, db: DbSession, current_user: CurrentUser) -> SensorOut:
    sensor = await SensorService.get(db, sensor_id)
    device = await db.get(Device, sensor.device_id)
    await check_project_access(db, current_user, device.project_id)
    return SensorOut.model_validate(sensor)


@router.put("/{sensor_id}", response_model=SensorOut)
async def update_sensor(
    sensor_id: int,
    payload: SensorUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> SensorOut:
    sensor = await SensorService.get(db, sensor_id)
    device = await db.get(Device, sensor.device_id)
    await check_project_write_access(db, current_user, device.project_id)
    updated = await SensorService.update(db, sensor_id, payload)
    return SensorOut.model_validate(updated)


@router.delete("/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sensor(sensor_id: int, db: DbSession, admin: AdminUser) -> None:
    await SensorService.delete(db, sensor_id)
