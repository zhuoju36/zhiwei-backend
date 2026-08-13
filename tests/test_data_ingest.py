"""批量数据接入与时序查询集成测试（真实 TimescaleDB）。"""

import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Device, Point, Project
from tests.conftest import login_headers

API_KEY_HEADERS = {"X-API-Key": settings.edge_api_key}


@pytest.fixture
async def point_fixture() -> AsyncGenerator[dict, None]:
    """创建唯一的项目/设备/测点，用后删除。"""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        project = Project(name=f"ingest-test-{suffix}")
        db.add(project)
        await db.flush()
        device = Device(
            project_id=project.id,
            device_code=f"GW-{suffix}",
            device_name="测试网关",
            protocol="http_json",
            config={},
        )
        db.add(device)
        await db.flush()
        point = Point(device_id=device.id, point_code=f"ACC-{suffix}", unit="m/s2")
        db.add(point)
        await db.commit()
        ids = {
            "project_id": project.id,
            "device_id": device.id,
            "point_id": point.id,
            "device_code": device.device_code,
            "point_code": point.point_code,
        }
    yield ids
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, ids["project_id"])
        device = await db.get(Device, ids["device_id"])
        point = (
            await db.execute(select(Point).where(Point.id == ids["point_id"]))
        ).scalar_one_or_none()
        if point:
            await db.delete(point)
        if device:
            await db.delete(device)
        if project:
            await db.delete(project)
        await db.commit()


def make_readings(point_fixture: dict, count: int, base_time: datetime) -> list[dict]:
    return [
        {
            "device_code": point_fixture["device_code"],
            "point_code": point_fixture["point_code"],
            "timestamp": (base_time + timedelta(milliseconds=i * 10)).isoformat(),
            "value": float(i % 100) * 0.01,
            "unit": "m/s2",
        }
        for i in range(count)
    ]


async def test_ingest_and_query(client: AsyncClient, admin_user: dict, point_fixture: dict) -> None:
    base_time = datetime.now(UTC) - timedelta(minutes=5)
    readings = make_readings(point_fixture, 100, base_time)

    resp = await client.post(
        "/api/v1/data/ingest", json={"readings": readings}, headers=API_KEY_HEADERS
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["written"] == 100

    # 用 JWT 查询原始数据回读
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.get(
        "/api/v1/data/timeseries",
        params={
            "point_id": point_fixture["point_id"],
            "start": (base_time - timedelta(minutes=1)).isoformat(),
            "end": (base_time + timedelta(minutes=10)).isoformat(),
            "interval": "raw",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["data"]["data"]) == 100


async def test_timeseries_rejects_api_key(client: AsyncClient, point_fixture: dict) -> None:
    """timeseries 走 JWT 认证，边缘网关的 API Key 不能访问。"""
    base_time = datetime.now(UTC)
    resp = await client.get(
        "/api/v1/data/timeseries",
        params={
            "point_id": point_fixture["point_id"],
            "start": base_time.isoformat(),
            "end": (base_time + timedelta(minutes=1)).isoformat(),
            "interval": "raw",
        },
        headers=API_KEY_HEADERS,
    )
    assert resp.status_code == 401


async def test_ingest_rejects_bad_api_key(client: AsyncClient, point_fixture: dict) -> None:
    readings = make_readings(point_fixture, 1, datetime.now(UTC))
    resp = await client.post(
        "/api/v1/data/ingest",
        json={"readings": readings},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401


async def test_ingest_skips_unknown_codes(client: AsyncClient, point_fixture: dict) -> None:
    base_time = datetime.now(UTC)
    readings = make_readings(point_fixture, 2, base_time)
    readings.append(
        {
            "device_code": "NO-SUCH-DEVICE",
            "point_code": "X",
            "timestamp": base_time.isoformat(),
            "value": 1.0,
        }
    )
    resp = await client.post(
        "/api/v1/data/ingest", json={"readings": readings}, headers=API_KEY_HEADERS
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["written"] == 2


async def test_ingest_triggers_alert(
    client: AsyncClient, admin_user: dict, point_fixture: dict
) -> None:
    """数据接入触发阈值告警：写一条超阈值读数 → 检查 alerts 表出现一条。"""
    from sqlalchemy import delete, update

    from app.models.alert import Alert
    from app.models.point import Point

    # 给 point_fixture 设置 alert_rules（threshold=0.5 warning）
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Point)
            .where(Point.id == point_fixture["point_id"])
            .values(alert_rules=[{"operator": "gt", "threshold": 0.5, "level": "warning"}])
        )
        await db.commit()

    try:
        # 上报一条超阈值读数
        base_time = datetime.now(UTC) - timedelta(minutes=2)
        readings = [
            {
                "device_code": point_fixture["device_code"],
                "point_code": point_fixture["point_code"],
                "timestamp": base_time.isoformat(),
                "value": 0.99,  # 超过 0.5
                "unit": "m/s2",
            }
        ]
        resp = await client.post(
            "/api/v1/data/ingest", json={"readings": readings}, headers=API_KEY_HEADERS
        )
        assert resp.status_code == 200, resp.text

        # 由于 Celery 在 eager 模式下同步执行，告警应已写入
        async with AsyncSessionLocal() as db:
            alerts = (
                (await db.execute(select(Alert).where(Alert.point_id == point_fixture["point_id"])))
                .scalars()
                .all()
            )
            assert len(alerts) == 1
            assert alerts[0].level == "warning"
            assert alerts[0].value == 0.99
            assert alerts[0].is_resolved is False
            assert alerts[0].alert_type == "threshold"

        # 后续上报低值 → open 告警应自动关闭
        readings2 = [
            {
                "device_code": point_fixture["device_code"],
                "point_code": point_fixture["point_code"],
                "timestamp": (base_time + timedelta(seconds=1)).isoformat(),
                "value": 0.1,
                "unit": "m/s2",
            }
        ]
        resp = await client.post(
            "/api/v1/data/ingest", json={"readings": readings2}, headers=API_KEY_HEADERS
        )
        assert resp.status_code == 200

        async with AsyncSessionLocal() as db:
            alerts = (
                (await db.execute(select(Alert).where(Alert.point_id == point_fixture["point_id"])))
                .scalars()
                .all()
            )
            assert len(alerts) == 1
            assert alerts[0].is_resolved is True
            assert alerts[0].ended_at is not None
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Alert).where(Alert.point_id == point_fixture["point_id"]))
            await db.execute(
                update(Point).where(Point.id == point_fixture["point_id"]).values(alert_rules=None)
            )
            await db.commit()


async def test_batch_ingest_performance(
    client: AsyncClient, admin_user: dict, point_fixture: dict
) -> None:
    """性能测试：10000 条批量写入 + 查询回读，写入耗时 < 2s（AGENTS.md 第 8 节）。"""
    base_time = datetime.now(UTC) - timedelta(minutes=30)
    readings = make_readings(point_fixture, 10000, base_time)

    start = time.perf_counter()
    resp = await client.post(
        "/api/v1/data/ingest", json={"readings": readings}, headers=API_KEY_HEADERS
    )
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["written"] == 10000
    assert elapsed < 2.0, f"批量写入 10000 条耗时 {elapsed:.2f}s，超过 2s"

    # 用 JWT 查询回读
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.get(
        "/api/v1/data/timeseries",
        params={
            "point_id": point_fixture["point_id"],
            "start": (base_time - timedelta(minutes=1)).isoformat(),
            "end": (base_time + timedelta(minutes=31)).isoformat(),
            "interval": "raw",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]["data"]
    assert len(data) == 10000
