"""分析任务 API 集成测试（v0.8b：channel_id 替代 point_id）。"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import numpy as np
from httpx import AsyncClient
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.analysis import AnalysisJob
from app.models.channel import Channel
from app.models.device import Device
from app.models.project import Project
from app.models.sensor import Sensor
from tests.conftest import login_headers


async def _make_channel() -> tuple[int, int, int, str]:
    s = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        proj = Project(name=f"analysis-test-{s}")
        db.add(proj)
        await db.flush()
        device = Device(
            project_id=proj.id,
            device_code=f"GW-A-{s}",
            protocol="http_json",
            config={},
        )
        db.add(device)
        await db.flush()
        await db.flush()
        sensor = Sensor(device_id=device.id, sensor_code=f"S-{s}")
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
        await db.execute(delete(Sensor).where(Sensor.device_id == dev_id))
        await db.execute(delete(Device).where(Device.id == dev_id))
        await db.execute(delete(Project).where(Project.id == proj_id))
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
        # 下载文件名来自实际 artifact_name（v0.8d 起不再写死 job_{id}.npz）
        assert 'filename="fft_' in resp.headers["content-disposition"]
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


async def test_list_plugins(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.get("/api/v1/analysis/plugins", headers=headers)
    assert resp.status_code == 200
    plugins = {p["name"]: p for p in resp.json()["data"]}
    assert "fft" in plugins
    assert "statistics" in plugins
    fft = plugins["fft"]
    assert fft["display_name"] == "FFT 频谱分析"
    assert fft["input_channels"] == 1
    assert fft["result_view"] == "fft"
    assert "sampling_rate" in fft["params_schema"]["properties"]
    assert plugins["statistics"]["result_view"] == "generic"


async def test_submit_statistics_job(client: AsyncClient, admin_user: dict) -> None:
    proj_id, dev_id, channel_id, _ = await _make_channel()
    await _seed_readings(channel_id, freq=5.0, sr=100.0)
    try:
        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        resp = await client.post(
            "/api/v1/analysis/jobs",
            json={"channel_id": channel_id, "plugin": "statistics", "params": {}},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        job_id = resp.json()["data"]["job_id"]
        for _ in range(30):
            resp = await client.get(f"/api/v1/analysis/jobs/{job_id}", headers=headers)
            status = resp.json()["data"]["status"]
            if status in ("success", "failed"):
                break
            await asyncio.sleep(0.2)
        assert status == "success", resp.json()
        summary = resp.json()["data"]["result_summary"]
        assert summary["num_samples"] > 0
        assert "mean" in summary and "rms" in summary
        # statistics 无附件
        assert resp.json()["data"]["result_key"] is None
    finally:
        await _cleanup(proj_id, dev_id, channel_id)


async def _make_channel_pair() -> tuple[int, int, list[int]]:
    """同一子项下两个通道（多通道分析测试用）。"""
    s = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        proj = Project(name=f"analysis-multi-{s}")
        db.add(proj)
        await db.flush()
        device = Device(
            project_id=proj.id, device_code=f"GW-M-{s}", protocol="http_json", config={}
        )
        db.add(device)
        await db.flush()
        await db.flush()
        sensor = Sensor(device_id=device.id, sensor_code=f"S-M-{s}")
        db.add(sensor)
        await db.flush()
        ch1 = Channel(sensor_id=sensor.id, channel_code=f"CH1-{s}", sampling_rate=100)
        ch2 = Channel(sensor_id=sensor.id, channel_code=f"CH2-{s}", sampling_rate=100)
        db.add_all([ch1, ch2])
        await db.commit()
        await db.refresh(ch1)
        await db.refresh(ch2)
        return proj.id, device.id, [ch1.id, ch2.id]


async def _cleanup_channels(proj_id: int, dev_id: int, channel_ids: list[int]) -> None:
    async with AsyncSessionLocal() as db:
        for cid in channel_ids:
            await db.execute(delete(AnalysisJob).where(AnalysisJob.channel_id == cid))
            from app.models.reading import Reading

            await db.execute(delete(Reading).where(Reading.channel_id == cid))
        await db.execute(delete(Channel).where(Channel.id.in_(channel_ids)))
        await db.execute(delete(Sensor).where(Sensor.device_id == dev_id))
        await db.execute(delete(Device).where(Device.id == dev_id))
        await db.execute(delete(Project).where(Project.id == proj_id))
        await db.commit()


async def test_multichannel_plugin_flow(client: AsyncClient, admin_user: dict) -> None:
    from app.plugins.analyzers.base import AnalysisInput, AnalysisOutput, AnalysisPlugin

    # 动态注册一个多通道插件（模拟社区插件通过 entry_points 接入）
    class FakeMulti(AnalysisPlugin):
        name = "fake_multi"
        input_channels = 2
        min_samples = 2

        async def analyze(self, data: AnalysisInput, config: dict) -> AnalysisOutput:
            arrays = data.data
            return AnalysisOutput(
                summary={
                    "channels": sorted(int(k) for k in arrays),
                    "lens": [int(len(v)) for v in arrays.values()],
                }
            )

    from app.plugins.analyzers.registry import AnalyzerRegistry

    AnalyzerRegistry._analyzers["fake_multi"] = FakeMulti
    try:
        proj_id, dev_id, ch_ids = await _make_channel_pair()
        for cid in ch_ids:
            await _seed_readings(cid, freq=5.0, sr=100.0)
        try:
            headers = await login_headers(client, admin_user["username"], admin_user["password"])
            resp = await client.post(
                "/api/v1/analysis/jobs",
                json={
                    "channel_id": ch_ids[0],
                    "plugin": "fake_multi",
                    "params": {"channel_ids": ch_ids},
                },
                headers=headers,
            )
            assert resp.status_code == 201, resp.text
            job_id = resp.json()["data"]["job_id"]
            for _ in range(30):
                resp = await client.get(f"/api/v1/analysis/jobs/{job_id}", headers=headers)
                status = resp.json()["data"]["status"]
                if status in ("success", "failed"):
                    break
                await asyncio.sleep(0.2)
            assert status == "success", resp.json()
            summary = resp.json()["data"]["result_summary"]
            assert sorted(summary["channels"]) == sorted(ch_ids)
            assert all(n >= 1 for n in summary["lens"])
        finally:
            await _cleanup_channels(proj_id, dev_id, ch_ids)
    finally:
        AnalyzerRegistry._analyzers.pop("fake_multi", None)


async def test_multichannel_cross_project_rejected(client: AsyncClient, admin_user: dict) -> None:
    from app.plugins.analyzers.base import AnalysisInput, AnalysisOutput, AnalysisPlugin
    from app.plugins.analyzers.registry import AnalyzerRegistry

    class FakeMulti(AnalysisPlugin):
        name = "fake_multi"
        input_channels = 2
        min_samples = 2

        async def analyze(self, data: AnalysisInput, config: dict) -> AnalysisOutput:
            return AnalysisOutput(summary={})

    AnalyzerRegistry._analyzers["fake_multi"] = FakeMulti
    try:
        proj1, dev1, ch1, _ = await _make_channel()
        proj2, dev2, ch2, _ = await _make_channel()
        try:
            headers = await login_headers(client, admin_user["username"], admin_user["password"])
            resp = await client.post(
                "/api/v1/analysis/jobs",
                json={
                    "channel_id": ch1,
                    "plugin": "fake_multi",
                    "params": {"channel_ids": [ch1, ch2]},
                },
                headers=headers,
            )
            assert resp.status_code == 201, resp.text
            job_id = resp.json()["data"]["job_id"]
            for _ in range(30):
                resp = await client.get(f"/api/v1/analysis/jobs/{job_id}", headers=headers)
                status = resp.json()["data"]["status"]
                if status in ("success", "failed"):
                    break
                await asyncio.sleep(0.2)
            assert status == "failed", resp.json()
            assert "同一子项" in resp.json()["data"]["error"]
        finally:
            await _cleanup(proj1, dev1, ch1)
            await _cleanup(proj2, dev2, ch2)
    finally:
        AnalyzerRegistry._analyzers.pop("fake_multi", None)


async def test_channel_count_mismatch_failed(client: AsyncClient, admin_user: dict) -> None:
    """单通道插件收到 2 个 channel_ids → 任务 failed。"""
    proj_id, dev_id, channel_id, _ = await _make_channel()
    try:
        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        resp = await client.post(
            "/api/v1/analysis/jobs",
            json={
                "channel_id": channel_id,
                "plugin": "statistics",
                "params": {"channel_ids": [channel_id, channel_id + 1]},
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        job_id = resp.json()["data"]["job_id"]
        for _ in range(30):
            resp = await client.get(f"/api/v1/analysis/jobs/{job_id}", headers=headers)
            status = resp.json()["data"]["status"]
            if status in ("success", "failed"):
                break
            await asyncio.sleep(0.2)
        assert status == "failed", resp.json()
        assert "需要 1 个通道" in resp.json()["data"]["error"]
    finally:
        await _cleanup(proj_id, dev_id, channel_id)


# ──────────────── 任务取消测试 ────────────────


async def _submit_job(client, headers, channel_id, plugin="statistics", params=None) -> int:
    resp = await client.post(
        "/api/v1/analysis/jobs",
        json={"channel_id": channel_id, "plugin": plugin, "params": params or {}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["job_id"]


async def test_cancel_pending_job(client: AsyncClient, admin_user: dict) -> None:
    """pending 状态任务可被取消：DB 写 cancelled，revoke 不带 terminate。"""
    proj_id, dev_id, channel_id, _ = await _make_channel()
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    job_id = await _submit_job(client, headers, channel_id)
    # eager 模式下任务已执行完毕，重新写回 pending 以模拟「队列中尚未消费」
    async with AsyncSessionLocal() as db:
        job = await db.get(AnalysisJob, job_id)
        job.status = "pending"
        job.started_at = None
        job.finished_at = None
        job.error = None
        job.result_summary = None
        job.result_key = None
        await db.commit()
    try:
        with patch("app.tasks.celery_app.celery_app.control.revoke") as mock_revoke:
            resp = await client.post(f"/api/v1/analysis/jobs/{job_id}/cancel", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["job_id"] == job_id
        assert body["status"] == "cancelled"
        assert body["previous_status"] == "pending"
        mock_revoke.assert_called_once_with(f"analysis-{job_id}", terminate=False)

        async with AsyncSessionLocal() as db:
            job = await db.get(AnalysisJob, job_id)
        assert job.status == "cancelled"
        assert job.finished_at is not None
    finally:
        await _cleanup(proj_id, dev_id, channel_id)


async def test_cancel_running_job(client: AsyncClient, admin_user: dict) -> None:
    """running 状态任务可被取消：revoke 带 terminate=True。"""
    proj_id, dev_id, channel_id, _ = await _make_channel()
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    job_id = await _submit_job(client, headers, channel_id)
    # 把状态模拟成 running
    async with AsyncSessionLocal() as db:
        job = await db.get(AnalysisJob, job_id)
        job.status = "running"
        job.started_at = datetime.now(UTC)
        await db.commit()
    try:
        with patch("app.tasks.celery_app.celery_app.control.revoke") as mock_revoke:
            resp = await client.post(f"/api/v1/analysis/jobs/{job_id}/cancel", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["previous_status"] == "running"
        mock_revoke.assert_called_once_with(f"analysis-{job_id}", terminate=True)
    finally:
        await _cleanup(proj_id, dev_id, channel_id)


async def test_cancel_success_job_rejected(client: AsyncClient, admin_user: dict) -> None:
    """success 任务不可取消：409。"""
    proj_id, dev_id, channel_id, _ = await _make_channel()
    await _seed_readings(channel_id, freq=10.0, sr=100.0)
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    job_id = await _submit_job(client, headers, channel_id)
    # 等到 success
    for _ in range(30):
        resp = await client.get(f"/api/v1/analysis/jobs/{job_id}", headers=headers)
        if resp.json()["data"]["status"] == "success":
            break
        await asyncio.sleep(0.1)
    try:
        resp = await client.post(f"/api/v1/analysis/jobs/{job_id}/cancel", headers=headers)
        assert resp.status_code == 409
        assert resp.json()["code"] == "ANALYSIS_JOB_NOT_CANCELLABLE"
    finally:
        await _cleanup(proj_id, dev_id, channel_id)


async def test_cancel_failed_job_rejected(client: AsyncClient, admin_user: dict) -> None:
    """failed 任务不可取消：409。"""
    proj_id, dev_id, channel_id, _ = await _make_channel()
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    job_id = await _submit_job(client, headers, channel_id)
    # eager 模式下 statistics 无数据 → 必失败
    for _ in range(30):
        resp = await client.get(f"/api/v1/analysis/jobs/{job_id}", headers=headers)
        if resp.json()["data"]["status"] == "failed":
            break
        await asyncio.sleep(0.1)
    try:
        resp = await client.post(f"/api/v1/analysis/jobs/{job_id}/cancel", headers=headers)
        assert resp.status_code == 409
        assert resp.json()["code"] == "ANALYSIS_JOB_NOT_CANCELLABLE"
    finally:
        await _cleanup(proj_id, dev_id, channel_id)


async def test_cancel_already_cancelled_rejected(client: AsyncClient, admin_user: dict) -> None:
    """二次取消 → 409。"""
    proj_id, dev_id, channel_id, _ = await _make_channel()
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    job_id = await _submit_job(client, headers, channel_id)
    async with AsyncSessionLocal() as db:
        job = await db.get(AnalysisJob, job_id)
        job.status = "cancelled"
        job.finished_at = datetime.now(UTC)
        await db.commit()
    try:
        resp = await client.post(f"/api/v1/analysis/jobs/{job_id}/cancel", headers=headers)
        assert resp.status_code == 409
        assert resp.json()["code"] == "ANALYSIS_JOB_NOT_CANCELLABLE"
    finally:
        await _cleanup(proj_id, dev_id, channel_id)


async def test_cancel_nonexistent(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.post("/api/v1/analysis/jobs/99999999/cancel", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "ANALYSIS_JOB_NOT_FOUND"


async def test_cancel_requires_write_access(client: AsyncClient, admin_user: dict) -> None:
    """无项目写权限的普通用户取消 → 403。"""
    from app.core.constants import Role
    from app.core.security import hash_password
    from app.models.user import User

    proj_id, dev_id, channel_id, _ = await _make_channel()
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    job_id = await _submit_job(client, headers, channel_id)
    # 准备一个无任何项目权限的普通用户
    name = f"reader_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        u = User(
            username=name,
            email=f"{name}@example.com",
            hashed_password=await hash_password("user12345"),
            role=Role.USER.value,
        )
        db.add(u)
        await db.commit()
        user_id = u.id
    try:
        login = await client.post(
            "/api/v1/auth/login",
            data={"username": name, "password": "user12345"},
        )
        user_headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
        resp = await client.post(f"/api/v1/analysis/jobs/{job_id}/cancel", headers=user_headers)
        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == "FORBIDDEN"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AnalysisJob).where(AnalysisJob.id == job_id))
            u = await db.get(User, user_id)
            if u is not None:
                await db.delete(u)
                await db.commit()
        await _cleanup(proj_id, dev_id, channel_id)


async def test_cancel_does_not_overwrite_with_success(
    client: AsyncClient, admin_user: dict
) -> None:
    """协作守卫：analyze() 完成后若 DB 已被置为 cancelled，结果不应被覆盖回 success。"""
    from sqlalchemy import select

    from app.plugins.analyzers.base import AnalysisInput, AnalysisOutput, AnalysisPlugin
    from app.plugins.analyzers.registry import AnalyzerRegistry

    class _CancelSelfPlugin(AnalysisPlugin):
        """模拟「运行中被外部取消」：在 analyze() 内部把当前 job 状态置 cancelled。"""

        name = "_cancel_self"
        input_channels = 1
        min_samples = 1

        async def analyze(self, data: AnalysisInput, config: dict) -> AnalysisOutput:
            # 按 channel_id 反查最近的任务并自取消（模拟外部撤销）
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(AnalysisJob)
                    .where(AnalysisJob.channel_id == data.channel_ids[0])
                    .order_by(AnalysisJob.id.desc())
                    .limit(1)
                )
                job = (await db.execute(stmt)).scalar_one()
                job.status = "cancelled"
                job.finished_at = datetime.now(UTC)
                await db.commit()
            return AnalysisOutput(summary={"would_have_been": "success"})

    AnalyzerRegistry._analyzers["_cancel_self"] = _CancelSelfPlugin
    try:
        proj_id, dev_id, channel_id, _ = await _make_channel()
        await _seed_readings(channel_id, freq=5.0, sr=100.0)
        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        resp = await client.post(
            "/api/v1/analysis/jobs",
            json={"channel_id": channel_id, "plugin": "_cancel_self", "params": {}},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        job_id = resp.json()["data"]["job_id"]
        resp = await client.get(f"/api/v1/analysis/jobs/{job_id}", headers=headers)
        # 终态必须是 cancelled，不被覆盖为 success
        assert resp.json()["data"]["status"] == "cancelled"
        assert resp.json()["data"]["result_summary"] is None
        assert resp.json()["data"]["result_key"] is None
    finally:
        AnalyzerRegistry._analyzers.pop("_cancel_self", None)
        await _cleanup(proj_id, dev_id, channel_id)
