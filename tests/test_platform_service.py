"""平台元数据 service 单测：单行表兜底与更新。"""

import pytest
from sqlalchemy import text

from app.core.exceptions import BizException
from app.database import AsyncSessionLocal
from app.schemas.platform import PlatformUpdate
from app.services import platform_service


@pytest.mark.asyncio
async def test_ensure_singleton_creates_default_row() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM platform_settings"))
        await db.commit()
    async with AsyncSessionLocal() as db:
        await platform_service.ensure_singleton(db)
    async with AsyncSessionLocal() as db:
        row = await platform_service.get_settings(db)
        assert row.platform_name == "SHM Platform"
        assert row.id == 1


@pytest.mark.asyncio
async def test_get_settings_fallback_when_empty() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM platform_settings"))
        await db.commit()
    async with AsyncSessionLocal() as db:
        row = await platform_service.get_settings(db)
        assert row.id == 1  # 空表兜底初始化


@pytest.mark.asyncio
async def test_update_settings_fields_and_empty_rejected(admin_user: dict) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM platform_settings"))
        await db.commit()
    async with AsyncSessionLocal() as db:
        updated = await platform_service.update_settings(
            db,
            PlatformUpdate(platform_name="知微 SHM", contact_email="ops@example.com"),
            admin_user["id"],
        )
        assert updated.platform_name == "知微 SHM"
        assert updated.contact_email == "ops@example.com"
        assert updated.updated_by == admin_user["id"]

        with pytest.raises(BizException) as exc:
            await platform_service.update_settings(db, PlatformUpdate(), admin_user["id"])
        assert exc.value.code == "EMPTY_UPDATE"
