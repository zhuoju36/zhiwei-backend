"""分析任务（Celery analysis 队列）。

执行流程：
1. mark_running
2. 从 sensor_raw 拉取时序数据 → np.ndarray
3. AnalyzerRegistry.get(plugin).analyze(point_id, time_range, data, params)
4. 把完整频谱/幅值数组打包为 NPZ 存 MinIO
5. mark_success(result_key, summary)
"""

import asyncio
import io
import logging
from typing import Any

import nest_asyncio
import numpy as np

from app.database import AsyncSessionLocal
from app.plugins.analyzers.registry import AnalyzerRegistry
from app.services import analysis_service
from app.services.data_service import get_pool
from app.tasks.celery_app import celery_app
from app.utils import minio_client

# Celery worker 使用默认 asyncio loop，与 SQLAlchemy / asyncpg / redis 池的
# greenlet 跨 loop 绑定冲突；nest_asyncio 让 asyncio.run() 在已有循环里复用。
nest_asyncio.apply()

logger = logging.getLogger(__name__)


async def _fetch_samples(point_id: int, start_iso: str | None, end_iso: str | None) -> np.ndarray:
    """从 sensor_raw 拉取等间隔采样的值数组。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if start_iso and end_iso:
            rows = await conn.fetch(
                """
                SELECT value FROM sensor_raw
                WHERE point_id = $1 AND time BETWEEN $2 AND $3
                ORDER BY time ASC
                """,
                point_id,
                start_iso,
                end_iso,
            )
        else:
            rows = await conn.fetch(
                "SELECT value FROM sensor_raw WHERE point_id = $1 ORDER BY time ASC",
                point_id,
            )
    return np.asarray([r["value"] for r in rows], dtype=np.float64)


async def _run(job_id: int) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        job = await analysis_service.get_job(db, job_id)
        point_id = job.point_id
        plugin_name = job.plugin
        params = dict(job.params or {})

    await minio_client.init()
    async with AsyncSessionLocal() as db:
        await analysis_service.mark_running(db, job_id)
        await db.commit()

    cls = AnalyzerRegistry.get(plugin_name)
    if cls is None:
        async with AsyncSessionLocal() as db:
            await analysis_service.mark_failed(db, job_id, f"plugin not found: {plugin_name}")
            await db.commit()
        return {"status": "failed", "reason": "plugin_not_found"}

    start_iso = params.get("start")
    end_iso = params.get("end")
    samples = await _fetch_samples(point_id, start_iso, end_iso)
    if len(samples) < 2:
        async with AsyncSessionLocal() as db:
            await analysis_service.mark_failed(db, job_id, "样本数不足")
            await db.commit()
        return {"status": "failed", "reason": "insufficient_samples"}

    plugin = cls()
    result = await plugin.analyze(
        point_id=point_id,
        time_range=(start_iso or "", end_iso or ""),
        data=samples,
        config=params,
    )

    # 上传 NPZ（含完整频谱/幅值）
    key = f"analysis/{point_id}/{job_id}.npz"
    npz_buf = io.BytesIO()
    freqs = np.asarray(result.pop("_internal_frequencies"))
    mags = np.asarray(result.pop("_internal_magnitudes"))
    np.savez(
        npz_buf, frequencies=freqs, magnitudes=mags, sampling_rate=float(params["sampling_rate"])
    )
    await minio_client.put_bytes(key, npz_buf.getvalue(), content_type="application/octet-stream")

    async with AsyncSessionLocal() as db:
        await analysis_service.mark_success(db, job_id, key, result)
        await db.commit()
    return {"status": "success", "result_key": key}


@celery_app.task(
    bind=True,
    queue="analysis",
    max_retries=2,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
)
def run_analysis_job(self, job_id: int) -> dict[str, Any]:
    try:
        return asyncio.run(_run(job_id))
    except Exception as exc:
        logger.exception("分析任务失败: job_id=%s", job_id)
        raise self.retry(exc=exc) from exc
