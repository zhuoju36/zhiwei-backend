"""分析任务 API 集成测试（v0.8b：channel_id 替代 point_id）。"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import numpy as np
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.models.analysis import AnalysisJob
from app.models.channel import Channel
from app.models.device import Device
from app.models.point import Point
from app.models.sensor import Sensor
from app.models.subitem import Subitem
from tests.conftest import login_headers


async def _make_channel() -> tuple[int, int, int, str]:
    s = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        proj = Subitem(name=f"analysis-test-{s}")
        db.add(proj)
        await db.flush()
        device = Device(
            subitem_id=proj.id,
            device_code=f"GW-A-{s}",
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
            channel_type="acceleration",
            unit="m/s2",
            sampling_rate=100,
        )
        db.add(channel)
        await db.commit()
        await db.refresh(channel)
        return proj.id, device.id, channel.id, s


async def _seed_readings(channel_id: int, freq: float, sr: float, duration_s: float = 2.0) -> int:
    """向 readings 写入正弦数据，返回行数。"""
    from app.services.data_service import get_pool

    n = int(sr * duration_s)
    t = np.arange(n) / sr
    values = np.sin(2 * np.pi * freq * t)
    pool = await get_pool()
    now = datetime.now(UTC)
    async with pool.acquire() as conn:
        await conn.executemany(
            """INSERT INTO readings (time, channel_id, value, quality)
               VALUES ($1, $2, $3, 'good')""",
            [(now - timedelta(seconds=n - i), channel_id, float(values[i])) for i in range(n)],
        )
    return n


async def _cleanup(proj_id: int, dev_id: int, ch_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AnalysisJob).where(AnalysisJob.channel_id == ch_id))
        # 先删 readings（FK readings.channel_id → channels.id）
        from app.models.reading import Reading

        await db.execute(delete(Reading).where(Reading.channel_id == ch_id))
        await db.execute(delete(Channel).where(Channel.id == ch_id))
        # 用子查询找该 device 下所有 point，再删 sensor + point
        await db.execute(
            delete(Sensor).where(
                Sensor.point_id.in_(
                    select(Point.id).where(Point.device_id == dev_id).scalar_subquery()
                )
            )
        )
        await db.execute(delete(Point).where(Point.device_id == dev_id))
        await db.execute(delete(Device).where(Device.id == dev_id))
        await db.execute(delete(Subitem).where(Subitem.id == proj_id))
        await db.commit()


async def test_submit_and_get_fft_job(client: AsyncClient, admin_user: dict) -> None:
    proj_id, dev_id, channel_id, _ = await _make_channel()
    seeded = await _seed_readings(channel_id, freq=50.0, sr=100.0)
    try:
        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        resp = await client.post(
            "/api/v1/analysis/jobs",
            json={
                "channel_id": channel_id,
                "plugin": "fft",
                "params": {"sampling_rate": 100.0},
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        job_id = resp.json()["data"]["job_id"]

        for _ in range(30):
            resp = await client.get(f"/api/v1/analysis/jobs/{job_id}", headers=headers)
            assert resp.status_code == 200, resp.text
            status = resp.json()["data"]["status"]
            if status in ("success", "failed"):
                break
            await asyncio.sleep(0.2)
        assert status == "success", resp.json()
        summary = resp.json()["data"]["result_summary"]
        assert summary is not None
        assert abs(summary["dominant_freq"] - 50.0) < 5.0
        assert summary["num_samples"] >= seeded // 2

        resp = await client.get(f"/api/v1/analysis/jobs/{job_id}/result", headers=headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"
        import io

        npz = np.load(io.BytesIO(resp.content))
        assert "frequencies" in npz.files
        assert "magnitudes" in npz.files
    finally:
        await _cleanup(proj_id, dev_id, channel_id)


async def test_submit_unknown_plugin_rejected(client: AsyncClient, admin_user: dict) -> None:
    proj_id, dev_id, channel_id, _ = await _make_channel()
    try:
        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        resp = await client.post(
            "/api/v1/analysis/jobs",
            json={
                "channel_id": channel_id,
                "plugin": "made_up_plugin",
                "params": {},
            },
            headers=headers,
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "PLUGIN_NOT_REGISTERED"
    finally:
        await _cleanup(proj_id, dev_id, channel_id)


async def test_job_list_with_filter(client: AsyncClient, admin_user: dict) -> None:
    proj_id, dev_id, channel_id, _ = await _make_channel()
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    await client.post(
        "/api/v1/analysis/jobs",
        json={"channel_id": channel_id, "plugin": "fft", "params": {"sampling_rate": 100.0}},
        headers=headers,
    )
    try:
        resp = await client.get(f"/api/v1/analysis/jobs?channel_id={channel_id}", headers=headers)
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert all(j["channel_id"] == channel_id for j in items)
        assert any(j["plugin"] == "fft" for j in items)
    finally:
        await _cleanup(proj_id, dev_id, channel_id)
