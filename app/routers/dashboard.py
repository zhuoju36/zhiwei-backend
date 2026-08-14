"""大屏聚合统计路由。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.middleware import create_router
from app.dependencies import CurrentUser, DbSession, check_project_access
from app.models.alert import Alert
from app.models.channel import Channel
from app.models.device import Device
from app.models.sensor import Sensor
from app.services.alert_service import to_out_dict

router = create_router(prefix="/dashboard", tags=["大屏"])


def _project_alert_select(project_id: int):
    """返回按 project_id 过滤的 Alert 查询（带完整 JOIN 链）。

    注意：JOIN 链是 Alert → Channel → Sensor → Device。
    """
    return (
        select(Alert)
        .join(Channel, Channel.id == Alert.channel_id)
        .join(Sensor, Sensor.id == Channel.sensor_id)
        .join(Device, Device.id == Sensor.device_id)
        .where(Device.project_id == project_id)
    )


@router.get("/stats")
async def get_stats(
    db: DbSession,
    current_user: CurrentUser,
    project_id: int | None = None,
) -> dict:
    """聚合统计：活跃告警、近 24h 告警、按级别分布。"""
    if project_id is not None:
        await check_project_access(db, current_user, project_id)

    count_active = select(func.count()).select_from(Alert).where(Alert.is_resolved.is_(False))
    count_24h = (
        select(func.count())
        .select_from(Alert)
        .where(Alert.started_at >= datetime.now(UTC) - timedelta(hours=24))
    )
    level_stmt = (
        select(Alert.level, func.count()).where(Alert.is_resolved.is_(False)).group_by(Alert.level)
    )
    recent_stmt = select(Alert).order_by(Alert.started_at.desc()).limit(10)

    if project_id is not None:
        sub = _project_alert_select(project_id).subquery()
        count_active = select(func.count()).select_from(sub).where(sub.c.is_resolved.is_(False))
        count_24h = (
            select(func.count())
            .select_from(sub)
            .where(sub.c.started_at >= datetime.now(UTC) - timedelta(hours=24))
        )
        level_stmt = (
            select(sub.c.level, func.count())
            .where(sub.c.is_resolved.is_(False))
            .group_by(sub.c.level)
        )
        recent_stmt = (
            select(Alert)
            .join(Channel, Channel.id == Alert.channel_id)
            .join(Sensor, Sensor.id == Channel.sensor_id)
            .join(Device, Device.id == Sensor.device_id)
            .where(Device.project_id == project_id)
            .order_by(Alert.started_at.desc())
            .limit(10)
        )

    active = (await db.execute(count_active)).scalar_one()
    last24 = (await db.execute(count_24h)).scalar_one()
    by_level_rows = (await db.execute(level_stmt)).all()
    by_level = {level or "unknown": cnt for level, cnt in by_level_rows}
    recent_rows = (await db.execute(recent_stmt)).scalars().all()

    return {
        "active_alerts": active,
        "alerts_24h": last24,
        "by_level": by_level,
        "recent_alerts": [to_out_dict(a) for a in recent_rows],
        "project_id": project_id,
    }


@router.get("/recent-alerts")
async def recent_alerts(
    db: DbSession,
    current_user: CurrentUser,
    project_id: int | None = None,
    limit: int = 10,
) -> list[dict]:
    """最近 N 条告警（不论已恢复/未恢复）。"""
    if project_id is not None:
        await check_project_access(db, current_user, project_id)
    stmt = select(Alert).order_by(Alert.started_at.desc()).limit(limit)
    if project_id is not None:
        stmt = (
            select(Alert)
            .join(Channel, Channel.id == Alert.channel_id)
            .join(Sensor, Sensor.id == Channel.sensor_id)
            .join(Device, Device.id == Sensor.device_id)
            .where(Device.project_id == project_id)
            .order_by(Alert.started_at.desc())
            .limit(limit)
        )
    rows = (await db.execute(stmt)).scalars().all()
    return [to_out_dict(a) for a in rows]
