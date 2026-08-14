"""设备管理路由。"""

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
from app.schemas.base import PageSchema
from app.schemas.device import DeviceCreate, DeviceOut, DeviceUpdate
from app.services.device_service import DeviceService

router = create_router(prefix="/devices", tags=["设备"])


@router.get("", response_model=PageSchema[DeviceOut])
async def list_devices(
    db: DbSession,
    current_user: CurrentUser,
    subitem_id: int = Query(..., description="子项 ID"),
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageSchema[DeviceOut]:
    await check_subitem_access(db, current_user, subitem_id)
    devices, total = await DeviceService.list_by_subitem(db, subitem_id, page, size)
    return PageSchema(
        total=total,
        page=page,
        size=size,
        items=[DeviceOut.model_validate(d) for d in devices],
    )


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
async def create_device(
    payload: DeviceCreate, db: DbSession, current_user: CurrentUser
) -> DeviceOut:
    await check_subitem_write_access(db, current_user, payload.subitem_id)
    device = await DeviceService.create(db, payload)
    return DeviceOut.model_validate(device)


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(device_id: int, db: DbSession, current_user: CurrentUser) -> DeviceOut:
    device = await DeviceService.get(db, device_id)
    await check_subitem_access(db, current_user, device.subitem_id)
    return DeviceOut.model_validate(device)


@router.put("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: int,
    payload: DeviceUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> DeviceOut:
    device = await DeviceService.get(db, device_id)
    await check_subitem_write_access(db, current_user, device.subitem_id)
    updated = await DeviceService.update(db, device_id, payload)
    return DeviceOut.model_validate(updated)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: int, db: DbSession, admin: AdminUser) -> None:
    await DeviceService.delete(db, device_id)
