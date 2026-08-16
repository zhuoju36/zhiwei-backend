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
    if job.status != "pending":
        # 任务已被取消（外部置为 cancelled）或状态异常；
        # 抛 BizException 由 Celery 任务层捕获并转为 Ignore，避免触发重试。
        raise BizException(
            code="ANALYSIS_JOB_NOT_RUNNING",
            message=f"任务状态为 {job.status}，无法进入 running",
            status_code=409,
        )
    job.status = "running"
    job.started_at = datetime.now(UTC)
    await db.flush()


CANCELLABLE_STATUSES = frozenset({"pending", "running"})


async def cancel_job(db: AsyncSession, job_id: int) -> str:
    """将任务置为 cancelled，返回取消前的状态（pending/running）。

    仅 pending / running 状态可被取消；其它状态抛 409。
    """
    job = await get_job(db, job_id)
    if job.status not in CANCELLABLE_STATUSES:
        raise BizException(
            code="ANALYSIS_JOB_NOT_CANCELLABLE",
            message=f"任务不可取消（当前 status={job.status}）",
            status_code=409,
        )
    previous_status = job.status
    job.status = "cancelled"
    job.finished_at = datetime.now(UTC)
    await db.flush()
    return previous_status


async def mark_success(
    db: AsyncSession, job_id: int, result_key: str | None, result_summary: dict[str, Any] | None
) -> None:
    job = await get_job(db, job_id)
    job.status = "success"
    job.result_key = result_key
    job.result_summary = result_summary
    job.finished_at = datetime.now(UTC)
    await db.flush()


async def mark_failed(db: AsyncSession, job_id: int, error: str) -> None:
    job = await get_job(db, job_id)
    job.status = "failed"
    job.error = error[:2000]
    job.finished_at = datetime.now(UTC)
    await db.flush()
