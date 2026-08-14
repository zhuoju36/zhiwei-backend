"""告警 API 集成测试（v0.8b：channel_id 替代 point_id）。"""

import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
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
    trigger_alert,
)
from tests.conftest import login_headers


async def _make_channel_with_alert_rules(
    rules: list[dict] | None = None,
) -> tuple[int, int, int]:
    """创建 subitem → device → point → sensor → channel 链路，并设置 channel 的 alert_rules。"""
    s = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        proj = Subitem(name=f"alert-test-{s}")
        db.add(proj)
        await db.flush()
        device = Device(
            subitem_id=proj.id,
            device_code=f"GW-{s}",
            protocol="http_json",
            config={},
        )
        db.add(device)
        await db.flush()
        point = Point(device_id=device.id, point_code=f"P-{s}")
        db.add(point)
        await db.flush()
        sensor = Sensor(point_id=point.id, sensor_code=f"S-{s}")
        db.add(sensor)
        await db.flush()
        channel = Channel(
            sensor_id=sensor.id,
            channel_code=f"ACC-{s}",
            channel_type="acceleration",
            unit="m/s2",
            sampling_rate=100,
            alert_rules=rules,
        )
        db.add(channel)
        await db.commit()
        await db.refresh(channel)
        return proj.id, device.id, channel.id


async def _cleanup_channel(proj_id: int, dev_id: int, ch_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Alert).where(Alert.channel_id == ch_id))
        await db.execute(delete(Channel).where(Channel.id == ch_id))
        await db.execute(
            delete(Sensor).where(
                Sensor.point_id.in_(
                    __import__("sqlalchemy")
                    .select(Point.id)
                    .where(Point.device_id == dev_id)
                    .scalar_subquery()
                )
            )
        )
        await db.execute(delete(Point).where(Point.device_id == dev_id))
        await db.execute(delete(Device).where(Device.id == dev_id))
        await db.execute(delete(Subitem).where(Subitem.id == proj_id))
        await db.commit()


async def test_alert_lifecycle_upsert_and_close(client: AsyncClient, admin_user: dict) -> None:
    _, _, cid = await _make_channel_with_alert_rules(
        [{"operator": "gt", "threshold": 0.5, "level": "warning", "suppress_seconds": 0}]
    )
    try:
        # 触发
        async with AsyncSessionLocal() as db:
            alert, created = await trigger_alert(
                db,
                cid,
                TriggerEvent(
                    level="warning", threshold=0.5, operator="gt", value=0.6, suppress_seconds=0
                ),
                datetime.now(UTC),
            )
            await db.commit()
            assert created is True
            alert_id = alert.id

        # 再次触发 -> 命中已存在，created=False
        async with AsyncSessionLocal() as db:
            _, created = await trigger_alert(
                db,
                cid,
                TriggerEvent(
                    level="warning", threshold=0.5, operator="gt", value=0.7, suppress_seconds=0
                ),
                datetime.now(UTC),
            )
            await db.commit()
            assert created is False

        # 列表（按 channel_id 过滤）
        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        resp = await client.get(f"/api/v1/alerts?channel_id={cid}", headers=headers)
        assert resp.status_code == 200, resp.text
        page = resp.json()["data"]
        assert page["total"] >= 1
        open_alerts = [a for a in page["items"] if not a["is_resolved"]]
        assert len(open_alerts) >= 1

        resp = await client.get(f"/api/v1/alerts/{alert_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["level"] == "warning"

        resp = await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["is_resolved"] is True

        resp = await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=headers)
        assert resp.status_code == 409
        assert resp.json()["code"] == "ALERT_ALREADY_RESOLVED"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Alert).where(Alert.channel_id == cid))
            await db.commit()


async def test_alert_filter_by_level_and_resolved(client: AsyncClient, admin_user: dict) -> None:
    from app.core.constants import AlertLevel

    _, _, cid = await _make_channel_with_alert_rules(
        [{"operator": "gt", "threshold": 1, "level": "warning", "suppress_seconds": 0}]
    )
    try:
        async with AsyncSessionLocal() as db:
            await trigger_alert(
                db,
                cid,
                TriggerEvent(
                    level="warning", threshold=1, operator="gt", value=2, suppress_seconds=0
                ),
                datetime.now(UTC),
            )
            await trigger_alert(
                db,
                cid,
                TriggerEvent(
                    level="danger", threshold=5, operator="gt", value=10, suppress_seconds=0
                ),
                datetime.now(UTC),
            )
            await db.commit()

        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        resp = await client.get(
            f"/api/v1/alerts?channel_id={cid}&level={AlertLevel.WARNING.value}",
            headers=headers,
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert all(a["level"] == "warning" for a in items)
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Alert).where(Alert.channel_id == cid))
            await db.commit()


async def test_alerts_list_requires_filter(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.get("/api/v1/alerts", headers=headers)
    assert resp.status_code == 200


async def test_dashboard_stats(client: AsyncClient, admin_user: dict) -> None:
    subitem_id, _, cid = await _make_channel_with_alert_rules(
        [{"operator": "gt", "threshold": 5, "level": "danger", "suppress_seconds": 0}]
    )
    try:
        async with AsyncSessionLocal() as db:
            await trigger_alert(
                db,
                cid,
                TriggerEvent(
                    level="danger", threshold=5, operator="gt", value=10, suppress_seconds=0
                ),
                datetime.now(UTC),
            )
            await db.commit()

        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        resp = await client.get(f"/api/v1/dashboard/stats?subitem_id={subitem_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["active_alerts"] >= 1
        assert data["alerts_24h"] >= 1
        assert "by_level" in data

        resp = await client.get(
            f"/api/v1/dashboard/recent-alerts?subitem_id={subitem_id}&limit=5",
            headers=headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Alert).where(Alert.channel_id == cid))
            await db.commit()
