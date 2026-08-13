"""告警业务逻辑：阈值评估、生命周期管理、列表与确认。"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.models.alert import Alert
from app.models.device import Device
from app.models.point import Point
from app.schemas.alert import AlertListQuery

logger = logging.getLogger(__name__)


@dataclass
class TriggerEvent:
    level: str
    threshold: float
    operator: str
    value: float
    message: str | None = None


_OPS = {
    "gt": lambda v, t: v > t,
    "lt": lambda v, t: v < t,
    "ge": lambda v, t: v >= t,
    "le": lambda v, t: v <= t,
    "eq": lambda v, t: v == t,
    "ne": lambda v, t: v != t,
}


def evaluate_thresholds(value: float, rules: list[dict[str, Any]] | None) -> list[TriggerEvent]:
    """对单条读数评估所有规则，返回触发的告警事件列表。"""
    if not rules:
        return []
    events: list[TriggerEvent] = []
    for rule in rules:
        op = rule.get("operator")
        threshold = rule.get("threshold")
        level = rule.get("level")
        if op not in _OPS or threshold is None or level is None:
            continue
        if _OPS[op](value, threshold):
            events.append(
                TriggerEvent(
                    level=level,
                    threshold=float(threshold),
                    operator=op,
                    value=value,
                    message=rule.get("message"),
                )
            )
    return events


async def upsert_alert(
    db: AsyncSession,
    point_id: int,
    event: TriggerEvent,
    timestamp: datetime,
) -> tuple[Alert, bool]:
    """维护按 (point_id, level) 唯一未恢复告警。

    返回 (alert, created)。created=True 表示新插入，False 表示命中已存在或关闭。
    """
    open_alert = (
        await db.execute(
            select(Alert).where(
                Alert.point_id == point_id,
                Alert.level == event.level,
                Alert.is_resolved.is_(False),
            )
        )
    ).scalar_one_or_none()

    if open_alert is None:
        msg = event.message or f"{event.operator} {event.threshold} 触发"
        alert = Alert(
            point_id=point_id,
            alert_type="threshold",
            level=event.level,
            message=msg,
            value=event.value,
            threshold=event.threshold,
            started_at=timestamp,
        )
        db.add(alert)
        await db.flush()
        return alert, True

    # 已存在未恢复告警：更新最新值/阈值（覆盖语义），不重置 started_at
    open_alert.value = event.value
    open_alert.threshold = event.threshold
    await db.flush()
    return open_alert, False


async def close_open_alerts(
    db: AsyncSession, point_id: int, level: str, timestamp: datetime
) -> Alert | None:
    """关闭一条未恢复告警（值回到正常范围）。幂等：没有则 no-op。"""
    open_alert = (
        await db.execute(
            select(Alert).where(
                Alert.point_id == point_id,
                Alert.level == level,
                Alert.is_resolved.is_(False),
            )
        )
    ).scalar_one_or_none()
    if open_alert is None:
        return None
    open_alert.ended_at = timestamp
    open_alert.is_resolved = True
    await db.flush()
    return open_alert


async def list_alerts(db: AsyncSession, query: AlertListQuery) -> tuple[list[Alert], int]:
    stmt = select(Alert)
    count_stmt = select(func.count()).select_from(Alert)

    if query.project_id is not None:
        stmt = (
            select(Alert)
            .join(Point, Point.id == Alert.point_id)
            .join(Device, Point.device_id == Device.id)
            .where(Device.project_id == query.project_id)
        )
        count_stmt = (
            select(func.count())
            .select_from(Alert)
            .join(Point, Point.id == Alert.point_id)
            .join(Device, Point.device_id == Device.id)
            .where(Device.project_id == query.project_id)
        )

    if query.point_id is not None:
        stmt = stmt.where(Alert.point_id == query.point_id)
        count_stmt = count_stmt.where(Alert.point_id == query.point_id)
    if query.level is not None:
        stmt = stmt.where(Alert.level == query.level.value)
        count_stmt = count_stmt.where(Alert.level == query.level.value)
    if query.is_resolved is not None:
        stmt = stmt.where(Alert.is_resolved.is_(query.is_resolved))
        count_stmt = count_stmt.where(Alert.is_resolved.is_(query.is_resolved))
    if query.start is not None:
        stmt = stmt.where(Alert.started_at >= query.start)
        count_stmt = count_stmt.where(Alert.started_at >= query.start)
    if query.end is not None:
        stmt = stmt.where(Alert.started_at <= query.end)
        count_stmt = count_stmt.where(Alert.started_at <= query.end)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = (
        stmt.order_by(Alert.started_at.desc())
        .offset((query.page - 1) * query.size)
        .limit(query.size)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows), total


async def get_alert(db: AsyncSession, alert_id: int) -> Alert:
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise BizException(code="ALERT_NOT_FOUND", message="告警不存在", status_code=404)
    return alert


async def acknowledge_alert(db: AsyncSession, alert_id: int, user_id: int) -> Alert:
    alert = await get_alert(db, alert_id)
    if alert.is_resolved:
        raise BizException(code="ALERT_ALREADY_RESOLVED", message="告警已确认", status_code=409)
    alert.is_resolved = True
    alert.ended_at = alert.ended_at or datetime.now(UTC)
    alert.resolved_by = user_id
    await db.flush()
    return alert


def to_out_dict(alert: Alert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "point_id": alert.point_id,
        "alert_type": alert.alert_type,
        "level": alert.level,
        "message": alert.message,
        "value": alert.value,
        "threshold": alert.threshold,
        "started_at": alert.started_at.isoformat() if alert.started_at else None,
        "ended_at": alert.ended_at.isoformat() if alert.ended_at else None,
        "is_resolved": alert.is_resolved,
        "resolved_by": alert.resolved_by,
    }
