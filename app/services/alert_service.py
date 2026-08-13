"""告警业务逻辑：阈值评估、生命周期管理、列表与确认。"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    suppress_seconds: int = 60


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
                    suppress_seconds=int(rule.get("suppress_seconds", 60)),
                )
            )
    return events


async def trigger_alert(
    db: AsyncSession,
    point_id: int,
    event: TriggerEvent,
    timestamp: datetime,
) -> tuple[Alert, bool]:
    """维护按 (point_id, level) 唯一活跃告警，含抑制窗口。

    流程：
    1. 命中未恢复告警 → 更新 value/threshold，返回 (alert, created=False)
    2. 否则查找抑制窗口（suppress_seconds）内最近一条已恢复告警 →
       重开（is_resolved=false, ended_at=null, started_at=timestamp），返回 (alert, created=True)
    3. 否则插入新告警，返回 (alert, created=True)

    返回 (alert, created)。created=True 表示"业务上是一次新告警事件"
    （新建或重开），调用方应触发通知 / WS 推送。
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

    if open_alert is not None:
        open_alert.value = event.value
        open_alert.threshold = event.threshold
        await db.flush()
        return open_alert, False

    # 抑制窗口：在最近 suppress_seconds 秒内关闭的告警，复用并重开
    if event.suppress_seconds > 0:
        threshold_ts = timestamp - timedelta(seconds=event.suppress_seconds)
        recent = (
            await db.execute(
                select(Alert)
                .where(
                    Alert.point_id == point_id,
                    Alert.level == event.level,
                    Alert.is_resolved.is_(True),
                    Alert.ended_at.is_not(None),
                    Alert.ended_at >= threshold_ts,
                )
                .order_by(Alert.ended_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if recent is not None:
            recent.is_resolved = False
            recent.ended_at = None
            recent.started_at = timestamp
            recent.value = event.value
            recent.threshold = event.threshold
            if event.message is not None:
                recent.message = event.message
            await db.flush()
            return recent, True

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


# v0.2 别名：保留以便旧测试/调用点兼容；内部直接走 trigger_alert（无抑制）。
async def upsert_alert(
    db: AsyncSession,
    point_id: int,
    event: TriggerEvent,
    timestamp: datetime,
) -> tuple[Alert, bool]:
    """v0.2 接口：抑制窗口为 0 时的简化版本。"""
    no_suppress = TriggerEvent(
        level=event.level,
        threshold=event.threshold,
        operator=event.operator,
        value=event.value,
        message=event.message,
        suppress_seconds=0,
    )
    return await trigger_alert(db, point_id, no_suppress, timestamp)


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
