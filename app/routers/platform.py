"""平台元数据路由：GET 公开，PUT admin。"""

from app.core.middleware import create_router
from app.dependencies import AdminUser, DbSession
from app.schemas.platform import PlatformOut, PlatformUpdate
from app.services import platform_service

router = create_router(prefix="/platform", tags=["平台"])


@router.get("", response_model=PlatformOut)
async def get_platform(db: DbSession) -> PlatformOut:
    """公开：前端 setup 页面 / 登录页可获取平台名称展示。"""
    return PlatformOut.model_validate(await platform_service.get_settings(db))


@router.put("", response_model=PlatformOut)
async def update_platform(payload: PlatformUpdate, db: DbSession, admin: AdminUser) -> PlatformOut:
    """仅 admin 可改。"""
    row = await platform_service.update_settings(db, payload, admin.id)
    return PlatformOut.model_validate(row)
