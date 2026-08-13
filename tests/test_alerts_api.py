"""告警 API 集成测试。"""

import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.alert import Alert
from app.models.device import Device
from app.models.point import Point
from app.models.project import Project
from app.services.alert_service import (
    TriggerEvent,
    upsert_alert,
)
from tests.conftest import login_headers


async def _make_point_with_alert_rules(
    rules: list[dict] | None = None,
) -> tuple[int, int, int]:
    s = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        proj = Project(name=f"alert-test-{s}")
        db.add(proj)
        await db.flush()
        device = Device(
            project_id=proj.id,
            device_code=f"GW-{s}",
            protocol="http_json",
            config={},
        )
        db.add(device)
        await db.flush()
        point = Point(
            device_id=device.id,
            point_code=f"PT-{s}",
            unit="m/s2",
            alert_rules=rules,
        )
        db.add(point)
        await db.commit()
        await db.refresh(point)
        return proj.id, device.id, point.id


async def _cleanup_alerts(point_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Alert).where(Alert.point_id == point_id))
        await db.commit()


async def test_alert_lifecycle_upsert_and_close(client: AsyncClient, admin_user: dict) -> None:
    _, _, pid = await _make_point_with_alert_rules(
        [{"operator": "gt", "threshold": 0.5, "level": "warning"}]
    )
    try:
        # 触发
        async with AsyncSessionLocal() as db:
            alert, created = await upsert_alert(
                db,
                pid,
                TriggerEvent(level="warning", threshold=0.5, operator="gt", value=0.6),
                datetime.now(UTC),
            )
            await db.commit()
            assert created is True
            alert_id = alert.id

        # 再次触发 -> 命中已存在，created=False
        async with AsyncSessionLocal() as db:
            _, created = await upsert_alert(
                db,
                pid,
                TriggerEvent(level="warning", threshold=0.5, operator="gt", value=0.7),
                datetime.now(UTC),
            )
            await db.commit()
            assert created is False

        # 列表（不传 project_id -> 用 point_id 过滤）
        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        resp = await client.get(f"/api/v1/alerts?point_id={pid}", headers=headers)
        assert resp.status_code == 200, resp.text
        page = resp.json()["data"]
        assert page["total"] >= 1
        open_alerts = [a for a in page["items"] if not a["is_resolved"]]
        assert len(open_alerts) >= 1

        # 详情
        resp = await client.get(f"/api/v1/alerts/{alert_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["level"] == "warning"

        # 确认
        resp = await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["is_resolved"] is True

        # 重复确认 -> 409
        resp = await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=headers)
        assert resp.status_code == 409
        assert resp.json()["code"] == "ALERT_ALREADY_RESOLVED"
    finally:
        await _cleanup_alerts(pid)


async def test_alert_filter_by_level_and_resolved(client: AsyncClient, admin_user: dict) -> None:
    from app.core.constants import AlertLevel

    _, _, pid = await _make_point_with_alert_rules()
    try:
        async with AsyncSessionLocal() as db:
            await upsert_alert(
                db,
                pid,
                TriggerEvent(level="warning", threshold=1, operator="gt", value=2),
                datetime.now(UTC),
            )
            await upsert_alert(
                db,
                pid,
                TriggerEvent(level="danger", threshold=5, operator="gt", value=10),
                datetime.now(UTC),
            )
            await db.commit()

        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        resp = await client.get(
            f"/api/v1/alerts?point_id={pid}&level={AlertLevel.WARNING.value}",
            headers=headers,
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert all(a["level"] == "warning" for a in items)
    finally:
        await _cleanup_alerts(pid)


async def test_alerts_list_requires_filter(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    # 不带 project_id / point_id，列表应能查询（admin 可见全量）
    resp = await client.get("/api/v1/alerts", headers=headers)
    assert resp.status_code == 200


async def test_dashboard_stats(client: AsyncClient, admin_user: dict) -> None:
    project_id, _, pid = await _make_point_with_alert_rules()
    try:
        async with AsyncSessionLocal() as db:
            await upsert_alert(
                db,
                pid,
                TriggerEvent(level="danger", threshold=5, operator="gt", value=10),
                datetime.now(UTC),
            )
            await db.commit()

        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        resp = await client.get(f"/api/v1/dashboard/stats?project_id={project_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["active_alerts"] >= 1
        assert data["alerts_24h"] >= 1
        assert "by_level" in data

        resp = await client.get(
            f"/api/v1/dashboard/recent-alerts?project_id={project_id}&limit=5",
            headers=headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)
    finally:
        await _cleanup_alerts(pid)
