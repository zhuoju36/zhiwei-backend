"""分析任务（Celery analysis 队列）。

执行流程：
1. mark_running
2. 按插件声明拉取通道数据（input_channels=1 单通道 / N 多通道，多通道限同子项）
3. plugin.analyze(AnalysisInput, config) -> AnalysisOutput
4. summary 写回 analysis_jobs.result_summary；artifact 上传 MinIO
5. mark_success
"""

import asyncio
import logging
from typing import Any

import nest_asyncio
import numpy as np
from celery.exceptions import Ignore
from sqlalchemy import select

from app.core.exceptions import BizException
from app.database import AsyncSessionLocal
from app.models.channel import Channel
from app.models.device import Device
from app.models.sensor import Sensor
from app.plugins.analyzers.base import AnalysisInput
from app.plugins.analyzers.registry import AnalyzerRegistry
from app.services import analysis_service
from app.services.data_service import get_pool
from app.tasks.celery_app import celery_app
from app.utils import minio_client

# Celery worker 使用默认 asyncio loop，与 SQLAlchemy / asyncpg / redis 池的
# greenlet 跨 loop 绑定冲突；nest_asyncio 让 asyncio.run() 在已有循环里复用。
nest_asyncio.apply()

logger = logging.getLogger(__name__)


async def _fetch_samples(channel_id: int, start_iso: str | None, end_iso: str | None) -> np.ndarray:
    """从 readings 拉取某通道的等间隔采样值数组。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if start_iso and end_iso:
            rows = await conn.fetch(
                """
                SELECT value FROM readings
                WHERE channel_id = $1 AND time BETWEEN $2 AND $3
                ORDER BY time ASC
                """,
                channel_id,
                start_iso,
                end_iso,
            )
        else:
            rows = await conn.fetch(
                "SELECT value FROM readings WHERE channel_id = $1 ORDER BY time ASC",
                channel_id,
            )
    return np.asarray([r["value"] for r in rows], dtype=np.float64)


async def _resolve_channels(db, channel_ids: list[int]) -> tuple[list[Channel], int]:
    """加载通道行，校验同属一个子项（多通道分析不允许跨子项）。"""
    stmt = (
        select(Channel, Device.project_id)
        .join(Sensor, Sensor.id == Channel.sensor_id)
        .join(Device, Device.id == Sensor.device_id)
        .where(Channel.id.in_(channel_ids))
    )
    rows = (await db.execute(stmt)).all()
    if len(rows) != len(channel_ids):
        raise ValueError("通道不存在")
    channels = [r[0] for r in rows]
    project_ids = {r[1] for r in rows}
    if len(project_ids) > 1:
        raise ValueError("多通道分析要求所有通道属于同一子项")
    return channels, project_ids.pop()


async def _run(job_id: int) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        job = await analysis_service.get_job(db, job_id)
        channel_id = job.channel_id
        plugin_name = job.plugin
        params = dict(job.params or {})

    await minio_client.init()
    try:
        async with AsyncSessionLocal() as db:
            await analysis_service.mark_running(db, job_id)
            await db.commit()
    except BizException as exc:
        if exc.code == "ANALYSIS_JOB_NOT_RUNNING":
            # 任务被外部取消，Celery 不重试、不计入失败
            logger.info("job %s 在 worker 接手前已被取消", job_id)
            raise Ignore() from exc
        raise

    cls = AnalyzerRegistry.get(plugin_name)
    if cls is None:
        async with AsyncSessionLocal() as db:
            await analysis_service.mark_failed(db, job_id, f"plugin not found: {plugin_name}")
            await db.commit()
        return {"status": "failed", "reason": "plugin_not_found"}
    plugin = cls()

    # 解析参与分析的通道（多通道插件从 params.channel_ids 读取）
    channel_ids: list[int] = list(params.get("channel_ids") or [channel_id])
    if len(channel_ids) != plugin.input_channels:
        err = f"插件 {plugin_name} 需要 {plugin.input_channels} 个通道，收到 {len(channel_ids)}"
        async with AsyncSessionLocal() as db:
            await analysis_service.mark_failed(db, job_id, err)
            await db.commit()
        return {"status": "failed", "reason": "channel_count_mismatch"}

    try:
        async with AsyncSessionLocal() as db:
            channels, _ = await _resolve_channels(db, channel_ids)
    except ValueError as exc:
        async with AsyncSessionLocal() as db:
            await analysis_service.mark_failed(db, job_id, str(exc))
            await db.commit()
        return {"status": "failed", "reason": "bad_channels"}

    start_iso = params.get("start")
    end_iso = params.get("end")
    time_range = (start_iso or "", end_iso or "")
    sampling_rate = float(channels[0].sampling_rate or 1.0)

    # 拉取数据
    if plugin.input_channels == 1:
        samples = await _fetch_samples(channel_ids[0], start_iso, end_iso)
        if samples.size < plugin.min_samples:
            async with AsyncSessionLocal() as db:
                await analysis_service.mark_failed(
                    db, job_id, f"样本数不足: {samples.size} < {plugin.min_samples}"
                )
                await db.commit()
            return {"status": "failed", "reason": "insufficient_samples"}
        data: Any = samples
    else:
        samples_map: dict[int, np.ndarray] = {}
        for cid in channel_ids:
            arr = await _fetch_samples(cid, start_iso, end_iso)
            if arr.size < plugin.min_samples:
                async with AsyncSessionLocal() as db:
                    await analysis_service.mark_failed(
                        db, job_id, f"通道 {cid} 样本数不足: {arr.size} < {plugin.min_samples}"
                    )
                    await db.commit()
                return {"status": "failed", "reason": "insufficient_samples"}
            samples_map[cid] = arr
        data = samples_map

    try:
        output = await plugin.analyze(
            AnalysisInput(
                channel_ids=channel_ids,
                time_range=time_range,
                sampling_rate=sampling_rate,
                data=data,
            ),
            params,
        )
    except Exception as exc:
        logger.exception("分析插件执行失败: job_id=%s plugin=%s", job_id, plugin_name)
        async with AsyncSessionLocal() as db:
            await analysis_service.mark_failed(db, job_id, str(exc))
            await db.commit()
        return {"status": "failed", "error": str(exc)}

    # 协作取消守卫：analyze() 返回后再次检查 DB 状态，
    # 若运行期间被外部置为 cancelled，则跳过附件上传与结果回写
    async with AsyncSessionLocal() as db:
        fresh = await analysis_service.get_job(db, job_id)
        if fresh.status == "cancelled":
            logger.info("job %s 已被取消，跳过结果回写", job_id)
            return {"status": "cancelled", "reason": "revoked_after_finish"}

    # 附件上传 MinIO
    result_key: str | None = None
    if output.artifact is not None:
        result_key = f"analysis/{job_id}/{output.artifact_name}"
        await minio_client.put_bytes(result_key, output.artifact, content_type=output.artifact_type)

    async with AsyncSessionLocal() as db:
        # 二次守卫：上传期间可能仍被取消
        fresh = await analysis_service.get_job(db, job_id)
        if fresh.status == "cancelled":
            logger.info("job %s 在附件上传期间被取消，清理已上传文件", job_id)
            return {"status": "cancelled", "reason": "revoked_during_upload"}
        await analysis_service.mark_success(db, job_id, result_key, output.summary)
        await db.commit()
    return {"status": "success", "result_key": result_key}


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
