"""分析路由：任务提交、查询、结果下载。"""

from fastapi import Query
from fastapi.responses import Response

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.middleware import create_router
from app.dependencies import (
    CurrentUser,
    DbSession,
    check_subitem_access,
    check_subitem_write_access,
)
from app.models.channel import Channel
from app.schemas.analysis import AnalysisJobCreate, AnalysisJobOut, AnalysisSubmitOut
from app.schemas.base import PageSchema
from app.services import analysis_service
from app.services.data_service import check_channel_subitem
from app.tasks.analysis_tasks import run_analysis_job
from app.utils import minio_client

router = create_router(prefix="/analysis", tags=["分析"])


def _job_to_out(job) -> AnalysisJobOut:
    return AnalysisJobOut.model_validate(job)


@router.post("/jobs", response_model=AnalysisSubmitOut, status_code=201)
async def submit_job(
    payload: AnalysisJobCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> AnalysisSubmitOut:
    subitem_id = await check_channel_subitem(payload.channel_id)
    await check_subitem_write_access(db, current_user, subitem_id)
    analysis_service.validate_plugin(payload.plugin)
    job = await analysis_service.create_job(
        db, payload.channel_id, payload.plugin, payload.params, current_user.id
    )
    await db.commit()
    try:
        run_analysis_job.delay(job.id)
    except Exception:
        pass
    return AnalysisSubmitOut(job_id=job.id, status=job.status)


@router.get("/jobs", response_model=PageSchema[AnalysisJobOut])
async def list_jobs(
    db: DbSession,
    current_user: CurrentUser,
    channel_id: int | None = Query(None),
    plugin: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageSchema[AnalysisJobOut]:
    if channel_id is not None:
        subitem_id = await check_channel_subitem(channel_id)
        await check_subitem_access(db, current_user, subitem_id)

    rows, total = await analysis_service.list_jobs(
        db, channel_id=channel_id, plugin=plugin, status=status, page=page, size=size
    )
    return PageSchema(
        total=total,
        page=page,
        size=size,
        items=[_job_to_out(j) for j in rows],
    )


@router.get("/jobs/{job_id}", response_model=AnalysisJobOut)
async def get_job(job_id: int, db: DbSession, current_user: CurrentUser) -> AnalysisJobOut:
    job = await analysis_service.get_job(db, job_id)
    channel = await db.get(Channel, job.channel_id)
    subitem_id = await check_channel_subitem(channel.id)
    await check_subitem_access(db, current_user, subitem_id)
    return _job_to_out(job)


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: int, db: DbSession, current_user: CurrentUser) -> Response:
    job = await analysis_service.get_job(db, job_id)
    channel = await db.get(Channel, job.channel_id)
    subitem_id = await check_channel_subitem(channel.id)
    await check_subitem_access(db, current_user, subitem_id)
    if job.status != "success" or not job.result_key:
        from app.core.exceptions import BizException

        raise BizException(
            code="ANALYSIS_RESULT_NOT_READY",
            message=f"任务未完成 (status={job.status})",
            status_code=409,
        )
    data = await minio_client.get_bytes(job.result_key)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="job_{job_id}.npz"'},
    )
