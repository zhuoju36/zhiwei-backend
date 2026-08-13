"""认证路由：登录与令牌刷新。"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.core.exceptions import AuthException
from app.core.middleware import create_router
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.dependencies import DbSession
from app.models.user import User
from app.schemas.user import RefreshIn, TokenOut
from app.services.user_service import UserService

router = create_router(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=TokenOut)
async def login(
    db: DbSession,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenOut:
    user = await UserService.authenticate(db, form.username, form.password)
    return TokenOut(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenOut)
async def refresh(payload: RefreshIn, db: DbSession) -> TokenOut:
    token_payload = decode_token(payload.refresh_token, expected_type="refresh")
    user = await db.get(User, int(token_payload["sub"]))
    if user is None or not user.is_active:
        raise AuthException("用户不存在或已停用")
    return TokenOut(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
    )
