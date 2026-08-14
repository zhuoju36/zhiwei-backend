"""测点管理路由。"""

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
from app.schemas.base import PageSchema
from app.schemas.point import PointCreate, PointOut, PointUpdate
from app.services.device_service import DeviceService
from app.services.point_service import PointService

router = create_router(prefix="/points", tags=["测点"])


@router.get("", response_model=PageSchema[PointOut])
async def list_points(
    db: DbSession,
    current_user: CurrentUser,
    subitem_id: int | None = Query(None, description="按项目筛选"),
    device_id: int | None = Query(None, description="按设备筛选"),
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageSchema[PointOut]:
    if subitem_id is not None:
        await check_subitem_access(db, current_user, subitem_id)
        points, total = await PointService.list_by_project(db, subitem_id, page, size)
    elif device_id is not None:
        device = await DeviceService.get(db, device_id)
        await check_subitem_access(db, current_user, device.subitem_id)
        points, total = await PointService.list_by_device(db, device_id, page, size)
    else:
        from app.core.exceptions import BizException

        raise BizException(
            code="BAD_REQUEST", message="subitem_id 与 device_id 至少传一个", status_code=400
        )
    return PageSchema(
        total=total,
        page=page,
        size=size,
        items=[PointOut.model_validate(p) for p in points],
    )


@router.post("", response_model=PointOut, status_code=status.HTTP_201_CREATED)
async def create_point(payload: PointCreate, db: DbSession, current_user: CurrentUser) -> PointOut:
    device = await DeviceService.get(db, payload.device_id)
    await check_subitem_write_access(db, current_user, device.subitem_id)
    point = await PointService.create(db, payload)
    return PointOut.model_validate(point)


@router.get("/{point_id}", response_model=PointOut)
async def get_point(point_id: int, db: DbSession, current_user: CurrentUser) -> PointOut:
    point = await PointService.get(db, point_id)
    device = await db.get(Device, point.device_id)
    await check_subitem_access(db, current_user, device.subitem_id)
    return PointOut.model_validate(point)


@router.put("/{point_id}", response_model=PointOut)
async def update_point(
    point_id: int,
    payload: PointUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> PointOut:
    point = await PointService.get(db, point_id)
    device = await db.get(Device, point.device_id)
    await check_subitem_write_access(db, current_user, device.subitem_id)
    updated = await PointService.update(db, point_id, payload)
    return PointOut.model_validate(updated)


@router.delete("/{point_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_point(point_id: int, db: DbSession, admin: AdminUser) -> None:
    await PointService.delete(db, point_id)
