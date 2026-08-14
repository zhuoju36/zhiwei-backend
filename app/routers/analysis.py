"""分析路由：任务提交、查询、结果下载。"""

import mimetypes

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
from app.models.channel import Channel
from app.schemas.analysis import (
    AnalysisJobCreate,
    AnalysisJobOut,
    AnalysisPluginMeta,
    AnalysisSubmitOut,
)
from app.schemas.base import PageSchema
from app.services import analysis_service
from app.services.data_service import check_channel_project
from app.tasks.analysis_tasks import run_analysis_job
from app.utils import minio_client

router = create_router(prefix="/analysis", tags=["分析"])


@router.get("/plugins", response_model=list[AnalysisPluginMeta])
async def list_plugins() -> list[AnalysisPluginMeta]:
    """列出全部已注册的分析插件（含元信息与参数表单 schema）。"""
    from app.plugins.analyzers.registry import AnalyzerRegistry

    result = []
    for name in AnalyzerRegistry.names():
        cls = AnalyzerRegistry.get(name)
        if cls is None:
            continue
        result.append(
            AnalysisPluginMeta(
                name=cls.name,
                display_name=cls.display_name,
                description=cls.description,
                version=cls.version,
                input_channels=cls.input_channels,
                min_samples=cls.min_samples,
                params_schema=cls.params_schema,
                result_view=cls.result_view,
            )
        )
    return result


def _job_to_out(job) -> AnalysisJobOut:
    return AnalysisJobOut.model_validate(job)


@router.post("/jobs", response_model=AnalysisSubmitOut, status_code=201)
async def submit_job(
    payload: AnalysisJobCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> AnalysisSubmitOut:
    project_id = await check_channel_project(payload.channel_id)
    await check_project_write_access(db, current_user, project_id)
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
        project_id = await check_channel_project(channel_id)
        await check_project_access(db, current_user, project_id)

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
    project_id = await check_channel_project(channel.id)
    await check_project_access(db, current_user, project_id)
    return _job_to_out(job)


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: int, db: DbSession, current_user: CurrentUser) -> Response:
    job = await analysis_service.get_job(db, job_id)
    channel = await db.get(Channel, job.channel_id)
    project_id = await check_channel_project(channel.id)
    await check_project_access(db, current_user, project_id)
    if job.status != "success" or not job.result_key:
        from app.core.exceptions import BizException

        raise BizException(
            code="ANALYSIS_RESULT_NOT_READY",
            message=f"任务未完成 (status={job.status})",
            status_code=409,
        )
    data = await minio_client.get_bytes(job.result_key)
    # 文件名取 MinIO key 末段（插件声明的 artifact_name，如 fft_1.npz）
    filename = job.result_key.rsplit("/", 1)[-1]
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
