"""平台元数据 service：单行表 + upsert。"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.models.platform import PlatformSettings
from app.schemas.platform import PlatformUpdate

logger = logging.getLogger(__name__)


DEFAULT_ROW: dict[str, Any] = {
    "id": 1,
    "platform_name": "SHM Platform",
    "contact_email": None,
    "description": None,
    "logo_url": None,
}


async def ensure_singleton(db: AsyncSession) -> None:
    """启动时调用：若表空则插入默认行。"""
    row = (await db.execute(select(PlatformSettings))).scalar_one_or_none()
    if row is None:
        db.add(PlatformSettings(**DEFAULT_ROW))
        await db.commit()
        logger.info("platform_settings 已初始化默认行")


async def get_settings(db: AsyncSession) -> PlatformSettings:
    row = (await db.execute(select(PlatformSettings))).scalar_one_or_none()
    if row is None:
        # 极端情况：lifespan 没跑 / DB 直接 DELETE — 兜底初始化
        await ensure_singleton(db)
        row = (await db.execute(select(PlatformSettings))).scalar_one()
    return row


async def update_settings(
    db: AsyncSession, payload: PlatformUpdate, updated_by: int
) -> PlatformSettings:
    if payload.is_empty():
        raise BizException(code="EMPTY_UPDATE", message="至少提供一个字段", status_code=422)
    row = await get_settings(db)
    if payload.platform_name is not None:
        row.platform_name = payload.platform_name
    if payload.contact_email is not None:
        row.contact_email = payload.contact_email
    if payload.description is not None:
        row.description = payload.description
    if payload.logo_url is not None:
        row.logo_url = payload.logo_url
    row.updated_by = updated_by
    row.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(row)
    return row
