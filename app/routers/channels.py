"""通道管理路由（挂在 sensor 下）。"""

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
from app.models.sensor import Sensor
from app.schemas.base import PageSchema
from app.schemas.sensor import ChannelCreate, ChannelOut, ChannelUpdate
from app.services.channel_service import ChannelService
from app.services.sensor_service import SensorService

router = create_router(prefix="/channels", tags=["通道"])


@router.get("", response_model=PageSchema[ChannelOut])
async def list_channels(
    db: DbSession,
    current_user: CurrentUser,
    sensor_id: int = Query(..., description="按传感器筛选"),
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageSchema[ChannelOut]:
    sensor = await SensorService.get(db, sensor_id)
    point = await db.get(Point, sensor.point_id)
    device = await db.get(Device, point.device_id)
    await check_subitem_access(db, current_user, device.subitem_id)
    rows, total = await ChannelService.list_by_sensor(db, sensor_id, page, size)
    return PageSchema(
        total=total,
        page=page,
        size=size,
        items=[ChannelOut.model_validate(c) for c in rows],
    )


@router.post("", response_model=ChannelOut, status_code=status.HTTP_201_CREATED)
async def create_channel(
    payload: ChannelCreate, db: DbSession, current_user: CurrentUser
) -> ChannelOut:
    sensor = await SensorService.get(db, payload.sensor_id)
    point = await db.get(Point, sensor.point_id)
    device = await db.get(Device, point.device_id)
    await check_subitem_write_access(db, current_user, device.subitem_id)
    channel = await ChannelService.create(db, payload)
    return ChannelOut.model_validate(channel)


@router.get("/{channel_id}", response_model=ChannelOut)
async def get_channel(channel_id: int, db: DbSession, current_user: CurrentUser) -> ChannelOut:
    channel = await ChannelService.get(db, channel_id)
    sensor = await db.get(Sensor, channel.sensor_id)
    point = await db.get(Point, sensor.point_id)
    device = await db.get(Device, point.device_id)
    await check_subitem_access(db, current_user, device.subitem_id)
    return ChannelOut.model_validate(channel)


@router.put("/{channel_id}", response_model=ChannelOut)
async def update_channel(
    channel_id: int,
    payload: ChannelUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> ChannelOut:
    channel = await ChannelService.get(db, channel_id)
    sensor = await db.get(Sensor, channel.sensor_id)
    point = await db.get(Point, sensor.point_id)
    device = await db.get(Device, point.device_id)
    await check_subitem_write_access(db, current_user, device.subitem_id)
    updated = await ChannelService.update(db, channel_id, payload)
    return ChannelOut.model_validate(updated)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(channel_id: int, db: DbSession, admin: AdminUser) -> None:
    await ChannelService.delete(db, channel_id)
