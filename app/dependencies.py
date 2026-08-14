"""FastAPI 依赖注入：DB 会话、当前用户、权限、API Key。"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.constants import Role
from app.core.exceptions import AuthException, BizException
from app.core.security import decode_token
from app.database import AsyncSessionLocal
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User:
    if not token:
        raise AuthException("缺少访问令牌")
    payload = decode_token(token, expected_type="access")
    user_id = int(payload["sub"])
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthException("用户不存在或已停用")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(current_user: CurrentUser) -> User:
    if current_user.role != Role.ADMIN:
        raise BizException(code="FORBIDDEN", message="需要管理员权限", status_code=403)
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]


async def verify_api_key(x_api_key: Annotated[str | None, Header()] = None) -> str:
    """边缘网关 API Key 认证（非 JWT）。"""
    if not x_api_key or x_api_key != settings.edge_api_key:
        raise AuthException("API Key 无效")
    return x_api_key


async def check_project_access(db: AsyncSession, user: User, project_id: int) -> None:
    """校验用户是否有指定子项的访问权限（admin 放行）。"""
    if user.role == Role.ADMIN:
        return
    from app.models.project import UserProject

    stmt = select(UserProject).where(
        UserProject.user_id == user.id, UserProject.project_id == project_id
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise BizException(code="FORBIDDEN", message="无权访问该子项", status_code=403)


async def check_project_write_access(db: AsyncSession, user: User, project_id: int) -> None:
    """校验用户是否有子项写权限（admin 全局；子项成员需 permission in {write, admin}）。"""
    if user.role == Role.ADMIN:
        return
    from app.core.constants import ProjectPermission
    from app.models.project import UserProject

    stmt = select(UserProject.permission).where(
        UserProject.user_id == user.id, UserProject.project_id == project_id
    )
    permission = (await db.execute(stmt)).scalar_one_or_none()
    if permission is None or permission not in (
        ProjectPermission.WRITE.value,
        ProjectPermission.ADMIN.value,
    ):
        raise BizException(code="FORBIDDEN", message="需要子项写权限", status_code=403)


async def check_project_admin(db: AsyncSession, user: User, project_id: int) -> None:
    """校验用户是否有子项管理员权限（admin 全局；子项成员需 permission=admin）。"""
    if user.role == Role.ADMIN:
        return
    from app.core.constants import ProjectPermission
    from app.models.project import UserProject

    stmt = select(UserProject.permission).where(
        UserProject.user_id == user.id, UserProject.project_id == project_id
    )
    permission = (await db.execute(stmt)).scalar_one_or_none()
    if permission != ProjectPermission.ADMIN.value:
        raise BizException(code="FORBIDDEN", message="需要子项管理员权限", status_code=403)
