"""告警抑制（suppression）逻辑测试。

辅助函数以类内 @staticmethod 形式定义（避免 pytest-asyncio auto 模式下
模块级 async 函数与 session loop 交互的边角问题）。
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.alert import Alert
from app.models.channel import Channel
from app.models.device import Device
from app.models.point import Point
from app.models.sensor import Sensor
from app.models.subitem import Subitem
from app.services.alert_service import (
    TriggerEvent,
    close_open_alerts,
    evaluate_thresholds,
    trigger_alert,
)


class _Helpers:
    @staticmethod
    def ev(level: str = "warning", threshold: float = 0.5, suppress: int = 60) -> TriggerEvent:
        return TriggerEvent(
            level=level,
            threshold=threshold,
            operator="gt",
            value=0.99,
            suppress_seconds=suppress,
        )

    @staticmethod
    async def make_channel(db_cleanup: list[int]) -> int:
        s = uuid.uuid4().hex[:8]
        async with AsyncSessionLocal() as db:
            proj = Subitem(name=f"supp-test-{s}")
            db.add(proj)
            await db.flush()
            device = Device(
                subitem_id=proj.id,
                device_code=f"GW-S-{s}",
                protocol="http_json",
                config={},
            )
            db.add(device)
            await db.flush()
            point = Point(device_id=device.id, point_code=f"PT-{s}")
            db.add(point)
            await db.flush()
            sensor = Sensor(point_id=point.id, sensor_code=f"S-{s}")
            db.add(sensor)
            await db.flush()
            channel = Channel(
                sensor_id=sensor.id,
                channel_code=f"ACC-{s}",
                unit="m/s2",
                sampling_rate=100,
            )
            db.add(channel)
            await db.commit()
            await db.refresh(channel)
            db_cleanup.append(channel.id)
            return channel.id

    @staticmethod
    async def cleanup(channel_id: int) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Alert).where(Alert.channel_id == channel_id))
            await db.commit()
        async with AsyncSessionLocal() as db2:
            ch = await db2.get(Channel, channel_id)
            if ch:
                sensor = await db2.get(Sensor, ch.sensor_id)
                point = await db2.get(Point, sensor.point_id) if sensor else None
                device = await db2.get(Device, point.device_id) if point else None
                await db2.delete(ch)
                if sensor:
                    await db2.delete(sensor)
                if point:
                    await db2.delete(point)
                if device:
                    await db2.delete(device)
                    proj = await db2.get(Subitem, device.subitem_id)
                    if proj:
                        await db2.delete(proj)
            await db2.commit()


async def test_suppress_window_reopens_existing_alert() -> None:
    """触发 → 关闭 → 60s 内再触发 → 复用同一条 alert（id 不变，started_at 更新）。"""
    cleanup_ids: list[int] = []
    pid = await _Helpers.make_channel(cleanup_ids)
    try:
        t0 = datetime.now(UTC) - timedelta(seconds=30)
        async with AsyncSessionLocal() as db:
            a1, c1 = await trigger_alert(db, pid, _Helpers.ev(), t0)
            await db.commit()
            assert c1 is True
            aid = a1.id
        async with AsyncSessionLocal() as db:
            closed = await close_open_alerts(db, pid, "warning", t0 + timedelta(seconds=5))
            await db.commit()
            assert closed is not None
            assert closed.id == aid
            assert closed.is_resolved is True
        async with AsyncSessionLocal() as db:
            a2, c2 = await trigger_alert(db, pid, _Helpers.ev(), t0 + timedelta(seconds=30))
            await db.commit()
            assert c2 is True
            assert a2.id == aid
            assert a2.is_resolved is False
            assert a2.started_at == t0 + timedelta(seconds=30)
    finally:
        await _Helpers.cleanup(pid)


async def test_outside_window_creates_new_alert() -> None:
    pid = await _Helpers.make_channel([])
    try:
        t0 = datetime.now(UTC) - timedelta(seconds=120)
        async with AsyncSessionLocal() as db:
            a1, _ = await trigger_alert(db, pid, _Helpers.ev(suppress=60), t0)
            await db.commit()
        async with AsyncSessionLocal() as db:
            await close_open_alerts(db, pid, "warning", t0 + timedelta(seconds=1))
            await db.commit()
        async with AsyncSessionLocal() as db:
            a2, c = await trigger_alert(
                db, pid, _Helpers.ev(suppress=60), t0 + timedelta(seconds=120)
            )
            await db.commit()
            assert c is True
            assert a2.id != a1.id
    finally:
        await _Helpers.cleanup(pid)


async def test_suppress_seconds_zero_disables_reopen() -> None:
    pid = await _Helpers.make_channel([])
    try:
        t0 = datetime.now(UTC)
        async with AsyncSessionLocal() as db:
            a1, _ = await trigger_alert(db, pid, _Helpers.ev(suppress=0), t0)
            await db.commit()
        async with AsyncSessionLocal() as db:
            await close_open_alerts(db, pid, "warning", t0 + timedelta(seconds=1))
            await db.commit()
        async with AsyncSessionLocal() as db:
            a2, c = await trigger_alert(db, pid, _Helpers.ev(suppress=0), t0 + timedelta(seconds=2))
            await db.commit()
            assert c is True
            assert a2.id != a1.id
    finally:
        await _Helpers.cleanup(pid)


async def test_open_alert_update_returns_not_created() -> None:
    pid = await _Helpers.make_channel([])
    try:
        t0 = datetime.now(UTC)
        async with AsyncSessionLocal() as db:
            a1, c1 = await trigger_alert(db, pid, _Helpers.ev(), t0)
            await db.commit()
            assert c1 is True
        async with AsyncSessionLocal() as db:
            a2, c2 = await trigger_alert(db, pid, _Helpers.ev(), t0 + timedelta(seconds=5))
            await db.commit()
            assert c2 is False
            assert a2.id == a1.id
            assert a2.value == 0.99
    finally:
        await _Helpers.cleanup(pid)


def test_evaluate_threads_suppress_seconds_from_rule() -> None:
    """evaluate_thresholds 从 rule 的 suppress_seconds 字段填充。"""
    rules = [
        {"operator": "gt", "threshold": 0.5, "level": "warning", "suppress_seconds": 30},
        {"operator": "gt", "threshold": 1.0, "level": "danger", "suppress_seconds": 120},
    ]
    events = evaluate_thresholds(2.0, rules)
    assert len(events) == 2
    by_level = {e.level: e for e in events}
    assert by_level["warning"].suppress_seconds == 30
    assert by_level["danger"].suppress_seconds == 120
    no_suppress = evaluate_thresholds(
        2.0, [{"operator": "gt", "threshold": 0.5, "level": "warning"}]
    )
    assert no_suppress[0].suppress_seconds == 60
