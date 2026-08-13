"""首次部署引导路由（无认证，仅 users 表为空时可用）。"""

import logging

from fastapi import status

from app.core.middleware import create_router
from app.dependencies import DbSession
from app.schemas.setup import InitAdminRequest, InitAdminResponse, SetupStatusResponse
from app.services import setup_service

logger = logging.getLogger(__name__)

router = create_router(prefix="/setup", tags=["首次部署"])


@router.get("/status", response_model=SetupStatusResponse)
async def get_status(db: DbSession) -> SetupStatusResponse:
    """返回初始化状态与密码策略（前端 setup 页面轮询）。"""
    return SetupStatusResponse(
        initialized=await setup_service.is_initialized(db),
        password_requirements=setup_service.PASSWORD_REQUIREMENTS,
    )


@router.post("/init-admin", response_model=InitAdminResponse, status_code=status.HTTP_201_CREATED)
async def init_admin(payload: InitAdminRequest, db: DbSession) -> InitAdminResponse:
    """创建第一个 admin 用户。

    - 仅当 users 表为空时成功；否则 409 ALREADY_INITIALIZED
    - 密码不符合策略返回 422 WEAK_PASSWORD
    - 不需要 JWT（setup 阶段无用户）
    """
    result = await setup_service.init_first_admin(
        db, payload.username, payload.email, payload.password
    )
    await db.commit()
    return InitAdminResponse(
        admin_id=result["user"].id,
        username=result["user"].username,
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
    )
