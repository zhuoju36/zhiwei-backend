"""3D 模型路由：上传、列表、详情、GLB 下载、删除。

上传：multipart 文件 -> MinIO -> 建 3d_models 记录 -> 触发转换任务。
转换产物（GLB）通过 GET /models/{id}/file 流式返回（避免额外签名 URL 配置）。
"""

import uuid
from typing import Annotated

from fastapi import File, Form, Query, UploadFile, status
from fastapi.responses import Response

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.exceptions import BizException
from app.core.middleware import create_router
from app.dependencies import (
    AdminUser,
    CurrentUser,
    DbSession,
    check_project_access,
    check_project_write_access,
)
from app.models.project import Project
from app.schemas.base import PageSchema
from app.schemas.model import ModelOut, ModelUploadOut
from app.services.model_service import ModelService
from app.tasks.model_tasks import convert_model_task
from app.utils import minio_client

# 支持转换的源格式白名单（IFC 等需 v0.9+ Blender/IfcOpenShell）
SUPPORTED_FORMATS = {"obj", "stl", "ply", "gltf", "glb"}
MAX_MODEL_BYTES = 200 * 1024 * 1024  # 200MB，开发阶段一次性读入内存

router = create_router(prefix="/models", tags=["模型"])


@router.post("/{project_id}/upload", response_model=ModelUploadOut, status_code=201)
async def upload_model(
    project_id: int,
    db: DbSession,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File(description="源模型文件（.obj/.stl/.ply/.gltf/.glb）")],
    note: Annotated[str | None, Form()] = None,
) -> ModelUploadOut:
    project = await db.get(Project, project_id)
    if project is None:
        raise BizException(code="PROJECT_NOT_FOUND", message="子项不存在", status_code=404)
    await check_project_write_access(db, current_user, project_id)

    name = file.filename or "model"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in SUPPORTED_FORMATS:
        raise BizException(
            code="MODEL_FORMAT_UNSUPPORTED",
            message=f"不支持的格式 .{ext}（支持 {sorted(SUPPORTED_FORMATS)}；"
            "IFC 需 v0.9+ Blender/IfcOpenShell 转换器）",
            status_code=400,
        )

    data = await file.read()
    if len(data) > MAX_MODEL_BYTES:
        raise BizException(
            code="MODEL_TOO_LARGE",
            message=f"文件超过 {MAX_MODEL_BYTES // (1024 * 1024)}MB 上限",
            status_code=413,
        )
    if not data:
        raise BizException(code="MODEL_EMPTY", message="上传文件为空", status_code=400)

    original_key = f"models/{project_id}/{uuid.uuid4().hex}.{ext}"
    await minio_client.put_bytes(original_key, data)

    model = await ModelService.create(
        db, project_id, original_key, name, ext, current_user.id, note=note
    )
    await db.commit()
    await db.refresh(model)
    model_id = model.id

    try:
        convert_model_task.delay(model_id)
    except Exception:
        # 队列不可用时任务不投递，记录失败状态（可手动重跑）
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await ModelService.mark_failed(session, model_id, "转换任务投递失败（队列不可用）")
            await session.commit()

    return ModelUploadOut(model_id=model_id, status="pending")


@router.get("", response_model=PageSchema[ModelOut])
async def list_models(
    db: DbSession,
    current_user: CurrentUser,
    project_id: int = Query(..., description="按子项筛选"),
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageSchema[ModelOut]:
    await check_project_access(db, current_user, project_id)
    rows, total = await ModelService.list_by_project(db, project_id, page, size)
    return PageSchema(
        total=total,
        page=page,
        size=size,
        items=[ModelOut.model_validate(m) for m in rows],
    )


@router.get("/{model_id}", response_model=ModelOut)
async def get_model(model_id: int, db: DbSession, current_user: CurrentUser) -> ModelOut:
    model = await ModelService.get(db, model_id)
    await check_project_access(db, current_user, model.project_id)
    return ModelOut.model_validate(model)


@router.get("/{model_id}/file")
async def get_model_file(model_id: int, db: DbSession, current_user: CurrentUser) -> Response:
    """返回转换后的 GLB 文件（未转换完成时 409）。"""
    model = await ModelService.get(db, model_id)
    await check_project_access(db, current_user, model.project_id)
    if model.status != "success" or not model.glb_key:
        raise BizException(
            code="MODEL_NOT_READY",
            message=f"模型尚未完成转换 (status={model.status})",
            status_code=409,
        )
    data = await minio_client.get_bytes(model.glb_key)
    filename = model.original_name.rsplit(".", 1)[0] + ".glb"
    return Response(
        content=data,
        media_type="model/gltf-binary",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(model_id: int, db: DbSession, admin: AdminUser) -> None:
    original_key, glb_key = await ModelService.delete(db, model_id)
    await db.commit()
    # MinIO 对象删除失败只记日志，不阻断（孤儿对象可后续清理）
    for key in (original_key, glb_key):
        if key:
            try:
                await minio_client.delete_object(key)
            except Exception:
                pass
