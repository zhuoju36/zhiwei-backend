"""3D 模型转换任务（Celery reports 队列）。

执行流程：
1. 读取 3d_models 记录，mark_running
2. 从 MinIO 下载源文件
3. scripts.model_convert.convert_bytes -> GLB
4. 上传 GLB 到 MinIO，mark_success

格式问题（解析失败/不支持格式）不自动重试；意外异常也落到 failed 状态，
避免任务悬挂在 processing。
"""

import asyncio
import logging
import uuid

import nest_asyncio

from app.database import AsyncSessionLocal
from app.services import model_service
from app.tasks.celery_app import celery_app
from app.utils import minio_client
from scripts.model_convert import convert_bytes

nest_asyncio.apply()

logger = logging.getLogger(__name__)


async def _run(model_id: int) -> dict:
    await minio_client.init()

    async with AsyncSessionLocal() as db:
        model = await model_service.ModelService.get(db, model_id)
        subitem_id = model.subitem_id
        original_key = model.original_key
        source_format = model.source_format

    async with AsyncSessionLocal() as db:
        await model_service.ModelService.mark_running(db, model_id)
        await db.commit()

    data = await minio_client.get_bytes(original_key)
    try:
        glb = convert_bytes(data, source_format)
    except ValueError as exc:
        async with AsyncSessionLocal() as db:
            await model_service.ModelService.mark_failed(db, model_id, str(exc))
            await db.commit()
        return {"status": "failed", "error": str(exc)}

    glb_key = f"models/{subitem_id}/{uuid.uuid4().hex}.glb"
    await minio_client.put_bytes(glb_key, glb, content_type="model/gltf-binary")

    async with AsyncSessionLocal() as db:
        await model_service.ModelService.mark_success(db, model_id, glb_key)
        await db.commit()
    return {"status": "success", "glb_key": glb_key}


@celery_app.task(bind=True, queue="reports")
def convert_model_task(self, model_id: int) -> dict:
    try:
        return asyncio.run(_run(model_id))
    except Exception as exc:
        logger.exception("模型转换任务失败: model_id=%s", model_id)
        try:
            asyncio.run(_mark_failed_async(model_id, str(exc)))
        except Exception:
            logger.exception("模型失败状态回写失败: model_id=%s", model_id)
        return {"status": "failed", "error": str(exc)}


async def _mark_failed_async(model_id: int, error: str) -> None:
    async with AsyncSessionLocal() as db:
        await model_service.ModelService.mark_failed(db, model_id, error)
        await db.commit()
