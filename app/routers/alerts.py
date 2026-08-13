"""告警路由：列表、详情、确认。"""

from datetime import datetime

from fastapi import Query

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, AlertLevel
from app.core.middleware import create_router
from app.dependencies import (
    CurrentUser,
    DbSession,
    check_project_access,
    check_project_admin,
)
from app.models.device import Device
from app.models.point import Point
from app.schemas.alert import AlertOut
from app.schemas.base import PageSchema
from app.services.alert_service import (
    acknowledge_alert,
    get_alert,
    list_alerts,
    to_out_dict,
)

router = create_router(prefix="/alerts", tags=["告警"])


@router.get("", response_model=PageSchema[dict])
async def list_alerts_api(
    db: DbSession,
    current_user: CurrentUser,
    project_id: int | None = Query(None, description="按项目筛选"),
    point_id: int | None = Query(None, description="按测点筛选"),
    level: AlertLevel | None = Query(None),
    is_resolved: bool | None = Query(None),
    start: datetime | None = Query(None, description="告警开始时间下界"),
    end: datetime | None = Query(None, description="告警开始时间上界"),
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageSchema[dict]:
    # 权限：project_id 必须可见；point_id 必须属于可见项目
    if project_id is not None:
        await check_project_access(db, current_user, project_id)
    elif point_id is not None:
        point = await db.get(Point, point_id)
        if point is None:
            from app.core.exceptions import BizException

            raise BizException(code="POINT_NOT_FOUND", message="测点不存在", status_code=404)
        device = await db.get(Device, point.device_id)
        await check_project_access(db, current_user, device.project_id)

    from app.schemas.alert import AlertListQuery

    rows, total = await list_alerts(
        db,
        AlertListQuery(
            project_id=project_id,
            point_id=point_id,
            level=level,
            is_resolved=is_resolved,
            start=start,
            end=end,
            page=page,
            size=size,
        ),
    )
    return PageSchema(
        total=total,
        page=page,
        size=size,
        items=[to_out_dict(a) for a in rows],
    )


@router.get("/{alert_id}")
async def get_alert_api(alert_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    alert = await get_alert(db, alert_id)
    point = await db.get(Point, alert.point_id)
    device = await db.get(Device, point.device_id)
    await check_project_access(db, current_user, device.project_id)
    return to_out_dict(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge_alert_api(alert_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    alert = await get_alert(db, alert_id)
    point = await db.get(Point, alert.point_id)
    device = await db.get(Device, point.device_id)
    await check_project_admin(db, current_user, device.project_id)
    updated = await acknowledge_alert(db, alert_id, current_user.id)
    return to_out_dict(updated)
