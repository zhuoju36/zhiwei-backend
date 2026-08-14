"""告警路由：列表、详情、确认。"""

from datetime import datetime

from fastapi import Query

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, AlertLevel
from app.core.middleware import create_router
from app.dependencies import (
    CurrentUser,
    DbSession,
    check_subitem_access,
    check_subitem_admin,
)
from app.models.channel import Channel
from app.schemas.alert import AlertOut
from app.schemas.base import PageSchema
from app.services import alert_service
from app.services.data_service import check_channel_subitem

router = create_router(prefix="/alerts", tags=["告警"])


@router.get("", response_model=PageSchema[dict])
async def list_alerts_api(
    db: DbSession,
    current_user: CurrentUser,
    subitem_id: int | None = Query(None, description="按子项筛选"),
    channel_id: int | None = Query(None, description="按通道筛选"),
    level: AlertLevel | None = Query(None),
    is_resolved: bool | None = Query(None),
    start: datetime | None = Query(None, description="告警开始时间下界"),
    end: datetime | None = Query(None, description="告警开始时间上界"),
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageSchema[dict]:
    if subitem_id is not None:
        await check_subitem_access(db, current_user, subitem_id)
    elif channel_id is not None:
        subitem_id = await check_channel_subitem(channel_id)
        await check_subitem_access(db, current_user, subitem_id)

    rows, total = await alert_service.list_alerts(
        db,
        subitem_id=subitem_id,
        channel_id=channel_id,
        level=level,
        is_resolved=is_resolved,
        start=start,
        end=end,
        page=page,
        size=size,
    )
    return PageSchema(
        total=total,
        page=page,
        size=size,
        items=[alert_service.to_out_dict(a) for a in rows],
    )


@router.get("/{alert_id}")
async def get_alert_api(alert_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    alert = await alert_service.get_alert(db, alert_id)
    channel = await db.get(Channel, alert.channel_id)
    subitem_id = await check_channel_subitem(channel.id)
    await check_subitem_access(db, current_user, subitem_id)
    return alert_service.to_out_dict(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge_alert_api(alert_id: int, db: DbSession, current_user: CurrentUser) -> dict:
    alert = await alert_service.get_alert(db, alert_id)
    channel = await db.get(Channel, alert.channel_id)
    subitem_id = await check_channel_subitem(channel.id)
    await check_subitem_admin(db, current_user, subitem_id)
    updated = await alert_service.acknowledge_alert(db, alert_id, current_user.id)
    return alert_service.to_out_dict(updated)
