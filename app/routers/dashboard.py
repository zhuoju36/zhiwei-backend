"""大屏聚合统计路由。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.middleware import create_router
from app.dependencies import CurrentUser, DbSession, check_subitem_access
from app.models.alert import Alert
from app.models.device import Device
from app.models.point import Point
from app.services.alert_service import to_out_dict

router = create_router(prefix="/dashboard", tags=["大屏"])


@router.get("/stats")
async def get_stats(
    db: DbSession,
    current_user: CurrentUser,
    subitem_id: int | None = None,
) -> dict:
    """聚合统计：活跃告警、近 24h 告警、按级别分布。"""
    base = select(Alert)
    count_active = select(func.count()).select_from(Alert).where(Alert.is_resolved.is_(False))
    count_24h = (
        select(func.count())
        .select_from(Alert)
        .where(Alert.started_at >= datetime.now(UTC) - timedelta(hours=24))
    )
    if subitem_id is not None:
        await check_subitem_access(db, current_user, subitem_id)
        join_clause = Alert.point_id == Point.id
        dev_join = Point.device_id == Device.id
        base = (
            base.join(Point, join_clause)
            .join(Device, dev_join)
            .where(Device.subitem_id == subitem_id)
        )
        count_active = (
            count_active.join(Point, join_clause)
            .join(Device, dev_join)
            .where(Device.subitem_id == subitem_id)
        )
        count_24h = (
            count_24h.join(Point, join_clause)
            .join(Device, dev_join)
            .where(
                Device.subitem_id == subitem_id,
                Alert.started_at >= datetime.now(UTC) - timedelta(hours=24),
            )
        )

    active = (await db.execute(count_active)).scalar_one()
    last24 = (await db.execute(count_24h)).scalar_one()

    # 按 level 分布（仅活跃）
    level_stmt = (
        select(Alert.level, func.count()).where(Alert.is_resolved.is_(False)).group_by(Alert.level)
    )
    if subitem_id is not None:
        level_stmt = (
            level_stmt.join(Point, Point.id == Alert.point_id)
            .join(Device, Point.device_id == Device.id)
            .where(Device.subitem_id == subitem_id)
        )
    by_level_rows = (await db.execute(level_stmt)).all()
    by_level = {level or "unknown": cnt for level, cnt in by_level_rows}

    return {
        "active_alerts": active,
        "alerts_24h": last24,
        "by_level": by_level,
        "subitem_id": subitem_id,
    }


@router.get("/recent-alerts")
async def recent_alerts(
    db: DbSession,
    current_user: CurrentUser,
    subitem_id: int | None = None,
    limit: int = 10,
) -> list[dict]:
    """最近 N 条告警（不论已恢复/未恢复）。"""
    if subitem_id is not None:
        await check_subitem_access(db, current_user, subitem_id)
    stmt = select(Alert).order_by(Alert.started_at.desc()).limit(limit)
    if subitem_id is not None:
        stmt = (
            select(Alert)
            .join(Point, Point.id == Alert.point_id)
            .join(Device, Point.device_id == Device.id)
            .where(Device.subitem_id == subitem_id)
            .order_by(Alert.started_at.desc())
            .limit(limit)
        )
    rows = (await db.execute(stmt)).scalars().all()
    return [to_out_dict(a) for a in rows]
