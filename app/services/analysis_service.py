"""分析任务业务逻辑：任务生命周期与查询。"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.models.analysis import AnalysisJob
from app.plugins.analyzers.registry import AnalyzerRegistry


def validate_plugin(name: str) -> None:
    if name not in AnalyzerRegistry.names():
        raise BizException(
            code="PLUGIN_NOT_REGISTERED",
            message=f"未注册的分析插件: {name}；可用: {AnalyzerRegistry.names()}",
            status_code=422,
        )


async def create_job(
    db: AsyncSession, channel_id: int, plugin: str, params: dict[str, Any], submitted_by: int | None
) -> AnalysisJob:
    job = AnalysisJob(
        channel_id=channel_id,
        plugin=plugin,
        params=params,
        submitted_by=submitted_by,
        status="pending",
    )
    db.add(job)
    await db.flush()
    return job


async def get_job(db: AsyncSession, job_id: int) -> AnalysisJob:
    job = await db.get(AnalysisJob, job_id)
    if job is None:
        raise BizException(code="ANALYSIS_JOB_NOT_FOUND", message="任务不存在", status_code=404)
    return job


async def list_jobs(
    db: AsyncSession,
    *,
    channel_id: int | None = None,
    plugin: str | None = None,
    status: str | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[AnalysisJob], int]:
    stmt = select(AnalysisJob)
    count_stmt = select(func.count()).select_from(AnalysisJob)
    if channel_id is not None:
        stmt = stmt.where(AnalysisJob.channel_id == channel_id)
        count_stmt = count_stmt.where(AnalysisJob.channel_id == channel_id)
    if plugin is not None:
        stmt = stmt.where(AnalysisJob.plugin == plugin)
        count_stmt = count_stmt.where(AnalysisJob.plugin == plugin)
    if status is not None:
        stmt = stmt.where(AnalysisJob.status == status)
        count_stmt = count_stmt.where(AnalysisJob.status == status)
    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(AnalysisJob.id.desc()).offset((page - 1) * size).limit(size)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows), total


async def mark_running(db: AsyncSession, job_id: int) -> None:
    job = await get_job(db, job_id)
    job.status = "running"
    job.started_at = datetime.now(UTC)
    await db.flush()


async def mark_success(
    db: AsyncSession, job_id: int, result_key: str | None, result_summary: dict[str, Any] | None
) -> None:
    job = await get_job(db, job_id)
    job.status = "success"
    job.result_key = result_key
    # 摘要中可能包含 _internal_* 字段，移除
    if result_summary:
        result_summary = {k: v for k, v in result_summary.items() if not k.startswith("_internal_")}
    job.result_summary = result_summary
    job.finished_at = datetime.now(UTC)
    await db.flush()


async def mark_failed(db: AsyncSession, job_id: int, error: str) -> None:
    job = await get_job(db, job_id)
    job.status = "failed"
    job.error = error[:2000]
    job.finished_at = datetime.now(UTC)
    await db.flush()
