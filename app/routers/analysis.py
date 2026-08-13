"""分析路由：任务提交、查询、结果下载。"""

from fastapi import Query
from fastapi.responses import Response

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.middleware import create_router
from app.dependencies import (
    CurrentUser,
    DbSession,
    check_project_access,
    check_project_write_access,
)
from app.models.device import Device
from app.models.point import Point
from app.schemas.analysis import AnalysisJobCreate, AnalysisJobOut, AnalysisSubmitOut
from app.schemas.base import PageSchema
from app.services import analysis_service
from app.services.data_service import check_point_project
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
    project_id = await check_point_project(payload.point_id)
    await check_project_write_access(db, current_user, project_id)
    analysis_service.validate_plugin(payload.plugin)
    job = await analysis_service.create_job(
        db, payload.point_id, payload.plugin, payload.params, current_user.id
    )
    await db.commit()
    try:
        run_analysis_job.delay(job.id)
    except Exception:
        # broker 不可达时回滚状态；保留为 pending 让运维恢复后处理
        pass
    return AnalysisSubmitOut(job_id=job.id, status=job.status)


@router.get("/jobs", response_model=PageSchema[AnalysisJobOut])
async def list_jobs(
    db: DbSession,
    current_user: CurrentUser,
    point_id: int | None = Query(None),
    plugin: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageSchema[AnalysisJobOut]:
    # 权限过滤：list_jobs 默认仅返回用户有访问权限的项目的任务
    if point_id is not None:
        await check_point_project(point_id)
        project_id_for_point = await check_point_project(point_id)
        await check_project_access(db, current_user, project_id_for_point)

    rows, total = await analysis_service.list_jobs(
        db, point_id=point_id, plugin=plugin, status=status, page=page, size=size
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
    point = await db.get(Point, job.point_id)
    device = await db.get(Device, point.device_id)
    await check_project_access(db, current_user, device.project_id)
    return _job_to_out(job)


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: int, db: DbSession, current_user: CurrentUser) -> Response:
    job = await analysis_service.get_job(db, job_id)
    point = await db.get(Point, job.point_id)
    device = await db.get(Device, point.device_id)
    await check_project_access(db, current_user, device.project_id)
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
