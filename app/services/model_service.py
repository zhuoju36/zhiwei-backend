"""3D 模型业务逻辑：上传记录创建、状态流转、删除。

MinIO 对象读写由任务层 / 路由层完成，service 只负责 3d_models 表。
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.models.model import Model


class ModelService:
    @staticmethod
    async def create(
        db: AsyncSession,
        subitem_id: int,
        original_key: str,
        original_name: str,
        source_format: str,
        user_id: int | None = None,
    ) -> Model:
        model = Model(
            subitem_id=subitem_id,
            original_key=original_key,
            original_name=original_name,
            source_format=source_format,
            status="pending",
            created_by=user_id,
        )
        db.add(model)
        await db.flush()
        return model

    @staticmethod
    async def get(db: AsyncSession, model_id: int) -> Model:
        model = await db.get(Model, model_id)
        if model is None:
            raise BizException(code="MODEL_NOT_FOUND", message="模型不存在", status_code=404)
        return model

    @staticmethod
    async def list_by_subitem(
        db: AsyncSession, subitem_id: int, page: int, size: int
    ) -> tuple[list[Model], int]:
        total = (
            await db.execute(
                select(func.count()).select_from(Model).where(Model.subitem_id == subitem_id)
            )
        ).scalar_one()
        rows = (
            (
                await db.execute(
                    select(Model)
                    .where(Model.subitem_id == subitem_id)
                    .order_by(Model.created_at.desc(), Model.id.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    @staticmethod
    async def mark_running(db: AsyncSession, model_id: int) -> None:
        model = await ModelService.get(db, model_id)
        model.status = "processing"
        await db.flush()

    @staticmethod
    async def mark_success(db: AsyncSession, model_id: int, glb_key: str) -> None:
        model = await ModelService.get(db, model_id)
        model.status = "success"
        model.glb_key = glb_key
        model.error = None
        model.finished_at = datetime.now(UTC)
        await db.flush()

    @staticmethod
    async def mark_failed(db: AsyncSession, model_id: int, error: str) -> None:
        model = await ModelService.get(db, model_id)
        model.status = "failed"
        model.error = error
        model.finished_at = datetime.now(UTC)
        await db.flush()

    @staticmethod
    async def delete(db: AsyncSession, model_id: int) -> tuple[str | None, str | None]:
        """删除记录，返回 (original_key, glb_key) 供路由层清理 MinIO 对象。"""
        model = await ModelService.get(db, model_id)
        keys = (model.original_key, model.glb_key)
        await db.delete(model)
        await db.flush()
        return keys
