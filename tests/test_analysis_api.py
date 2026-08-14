"""分析任务 API 集成测试。"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import numpy as np
from httpx import AsyncClient
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.analysis import AnalysisJob
from app.models.device import Device
from app.models.point import Point
from app.models.subitem import Subitem
from tests.conftest import login_headers


async def _make_point() -> tuple[int, int, int, str]:
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
        point = Point(
            device_id=device.id,
            point_code=f"PT-{s}",
            unit="m/s2",
            sampling_rate=100,
        )
        db.add(point)
        await db.commit()
        await db.refresh(point)
        return proj.id, device.id, point.id, s


async def _seed_sensor_raw(point_id: int, freq: float, sr: float, duration_s: float = 2.0) -> int:
    """向 sensor_raw 写入正弦数据，返回行数。"""
    from app.services.data_service import get_pool

    n = int(sr * duration_s)
    t = np.arange(n) / sr
    values = np.sin(2 * np.pi * freq * t)
    pool = await get_pool()
    now = datetime.now(UTC)
    async with pool.acquire() as conn:
        # 间隔 10ms 模拟 100Hz
        await conn.executemany(
            """INSERT INTO sensor_raw (time, device_id, point_id, value, quality)
               VALUES ($1, $2, $3, $4, 'good')""",
            [(now - timedelta(seconds=n - i), 0, point_id, float(values[i])) for i in range(n)],
        )
    return n


async def test_submit_and_get_fft_job(client: AsyncClient, admin_user: dict) -> None:
    subitem_id, device_id, point_id, _ = await _make_point()
    seeded = await _seed_sensor_raw(point_id, freq=50.0, sr=100.0)
    try:
        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        # 提交
        resp = await client.post(
            "/api/v1/analysis/jobs",
            json={
                "point_id": point_id,
                "plugin": "fft",
                "params": {"sampling_rate": 100.0},
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        job_id = resp.json()["data"]["job_id"]

        # 轮询直到 success
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

        # 拉取 NPZ 结果
        resp = await client.get(f"/api/v1/analysis/jobs/{job_id}/result", headers=headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"
        import io

        npz = np.load(io.BytesIO(resp.content))
        assert "frequencies" in npz.files
        assert "magnitudes" in npz.files
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AnalysisJob).where(AnalysisJob.point_id == point_id))
            await db.execute(delete(Point).where(Point.id == point_id))
            await db.execute(delete(Device).where(Device.id == device_id))
            await db.execute(delete(Subitem).where(Subitem.id == subitem_id))
            await db.commit()


async def test_submit_unknown_plugin_rejected(client: AsyncClient, admin_user: dict) -> None:
    subitem_id, device_id, point_id, _ = await _make_point()
    try:
        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        resp = await client.post(
            "/api/v1/analysis/jobs",
            json={
                "point_id": point_id,
                "plugin": "made_up_plugin",
                "params": {},
            },
            headers=headers,
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "PLUGIN_NOT_REGISTERED"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Point).where(Point.id == point_id))
            await db.execute(delete(Device).where(Device.id == device_id))
            await db.execute(delete(Subitem).where(Subitem.id == subitem_id))
            await db.commit()


async def test_job_list_with_filter(client: AsyncClient, admin_user: dict) -> None:
    subitem_id, device_id, point_id, _ = await _make_point()
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    # 创建 job
    await client.post(
        "/api/v1/analysis/jobs",
        json={"point_id": point_id, "plugin": "fft", "params": {"sampling_rate": 100.0}},
        headers=headers,
    )
    try:
        resp = await client.get(f"/api/v1/analysis/jobs?point_id={point_id}", headers=headers)
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert all(j["point_id"] == point_id for j in items)
        assert any(j["plugin"] == "fft" for j in items)
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AnalysisJob).where(AnalysisJob.point_id == point_id))
            await db.execute(delete(Point).where(Point.id == point_id))
            await db.execute(delete(Device).where(Device.id == device_id))
            await db.execute(delete(Subitem).where(Subitem.id == subitem_id))
            await db.commit()
