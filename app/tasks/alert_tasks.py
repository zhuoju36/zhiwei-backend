"""告警检查任务（运行在 Celery alerts 队列）。

设计：
- check_threshold_batch 接收一批 readings（每条含 channel_id / value / timestamp / quality）
- 批量查 channel 的 alert_rules
- 评估每条 reading；触发 trigger_alert 或关闭 open alert
- 对新增/关闭的 alert 通过 Redis Pub/Sub 推送到对应子项频道（type=data:alert）

注：测试环境（pytest + asyncio 默认 loop）需要 nest_asyncio 允许在已运行
loop 内调用 asyncio.run()；由 tests/conftest.py 的 eager_celery fixture 启用。
uvicorn 进程使用 uvloop，模块顶层不做 nest_asyncio.apply()。

任务用 @celery_app.task 显式绑定到本项目的 celery_app 实例，避免 .delay() 走
默认 celery app 的 broker（默认是 amqp://，与 redis broker 冲突）。
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from app.database import AsyncSessionLocal
from app.services import alert_service
from app.services.data_service import get_redis
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _publish_alert(subitem_id: int, alert_payload: dict[str, Any]) -> None:
    try:
        rds = await get_redis()
        await rds.publish(
            f"subitem:{subitem_id}",
            json.dumps({"type": "data:alert", "payload": alert_payload}),
        )
    except Exception:
        logger.exception("告警推送失败")


async def _open_levels(session, channel_id: int) -> set[str]:
    from sqlalchemy import select

    from app.models.alert import Alert

    rows = (
        (
            await session.execute(
                select(Alert.level).where(
                    Alert.channel_id == channel_id, Alert.is_resolved.is_(False)
                )
            )
        )
        .scalars()
        .all()
    )
    return {lvl for lvl in rows if lvl is not None}


async def _process_readings(readings: list[dict[str, Any]]) -> None:
    """核心处理：在 Celery 异步任务或 eager 测试模式下调用的纯异步函数。"""
    if not readings:
        return

    channel_ids = sorted({r["channel_id"] for r in readings if r.get("channel_id") is not None})
    if not channel_ids:
        return

    from sqlalchemy import select

    from app.models.channel import Channel
    from app.models.device import Device
    from app.models.point import Point
    from app.models.sensor import Sensor

    async with AsyncSessionLocal() as db:
        # 批量取 alert_rules 与 device→subitem 映射（一次 JOIN）
        rows = (
            await db.execute(
                select(Channel.id, Channel.alert_rules, Device.subitem_id)
                .join(Sensor, Sensor.id == Channel.sensor_id)
                .join(Point, Point.id == Sensor.point_id)
                .join(Device, Device.id == Point.device_id)
                .where(Channel.id.in_(channel_ids))
            )
        ).all()
        meta = {cid: (rules or [], subitem_id) for cid, rules, subitem_id in rows}

        for reading in readings:
            cid = reading.get("channel_id")
            value = reading.get("value")
            ts_raw = reading.get("timestamp")
            if cid is None or value is None:
                continue
            rules, subitem_id = meta.get(cid, ([], None))
            if subitem_id is None or not rules:
                continue
            ts = _parse_ts(ts_raw)

            events = alert_service.evaluate_thresholds(float(value), rules)
            triggered_levels = {e.level for e in events}
            # 关闭当前 open 但已不再触发的告警（按 level）
            open_levels = await _open_levels(db, cid)
            for lvl in open_levels - triggered_levels:
                closed = await alert_service.close_open_alerts(db, cid, lvl, ts)
                if closed is not None:
                    await db.commit()
                    await _publish_alert(
                        subitem_id,
                        {
                            "alert_id": closed.id,
                            "channel_id": cid,
                            "level": lvl,
                            "status": "resolved",
                            "ended_at": closed.ended_at.isoformat(),
                        },
                    )

            # 对触发的 level trigger（含抑制窗口重开语义）
            for event in events:
                alert, created = await alert_service.trigger_alert(db, cid, event, ts)
                await db.commit()
                await _publish_alert(
                    subitem_id,
                    {
                        "alert_id": alert.id,
                        "channel_id": cid,
                        "level": event.level,
                        "value": event.value,
                        "threshold": event.threshold,
                        "message": alert.message,
                        "status": "triggered" if created else "updated",
                        "started_at": alert.started_at.isoformat(),
                    },
                )
                # 新建/重开时多渠道通知
                if created:
                    try:
                        from app.notifications.base import AlertPayload
                        from app.services.notification_service import dispatch_alert

                        payload: AlertPayload = {
                            "alert_id": alert.id,
                            "channel_id": cid,
                            "subitem_id": subitem_id,
                            "level": event.level,
                            "value": event.value,
                            "threshold": event.threshold,
                            "message": alert.message,
                            "started_at": alert.started_at.isoformat(),
                            "device_code": reading.get("device_code", ""),
                            "channel_code": reading.get("channel_code", ""),
                        }
                        await dispatch_alert(payload)
                    except Exception:
                        logger.exception("告警通知分发失败")


def _parse_ts(ts_raw: Any) -> datetime:
    if isinstance(ts_raw, datetime):
        return ts_raw
    if isinstance(ts_raw, str):
        return datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    return datetime.now()


@celery_app.task(
    bind=True,
    queue="alerts",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def check_threshold_batch(self, readings: list[dict[str, Any]]) -> dict[str, int]:
    """Celery 任务入口（同步上下文）；内部跑 async。"""
    processed = len(readings or [])

    async def _runner() -> None:
        await _process_readings(readings or [])

    try:
        asyncio.run(_runner())
    except Exception as exc:
        logger.exception("告警批处理失败: %s", exc)
        raise self.retry(exc=exc) from exc
    return {"processed": processed}
