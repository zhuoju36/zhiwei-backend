"""用户业务逻辑。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthException, BizException
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserCreate


class UserService:
    @staticmethod
    async def get_by_username(db: AsyncSession, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def authenticate(db: AsyncSession, username: str, password: str) -> User:
        user = await UserService.get_by_username(db, username)
        if user is None or not await verify_password(password, user.hashed_password):
            raise AuthException("用户名或密码错误")
        if not user.is_active:
            raise AuthException("用户已停用")
        return user

    @staticmethod
    async def create_user(db: AsyncSession, payload: UserCreate) -> User:
        if await UserService.get_by_username(db, payload.username) is not None:
            raise BizException(code="USER_EXISTS", message="用户名已存在", status_code=409)
        user = User(
            username=payload.username,
            email=payload.email,
            hashed_password=await hash_password(payload.password),
            role=payload.role.value,
        )
        db.add(user)
        await db.flush()
        return user
