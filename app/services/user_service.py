"""用户业务逻辑：认证 / setup admin 创建 / admin CRUD。"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import Role
from app.core.exceptions import AuthException, BizException
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserAdminUpdate, UserCreate, UserListQuery

logger = logging.getLogger(__name__)


class UserService:
    @staticmethod
    async def get_by_username(db: AsyncSession, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> User | None:
        return await db.get(User, user_id)

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
        # email 唯一性
        stmt = select(User).where(User.email == payload.email)
        if (await db.execute(stmt)).scalar_one_or_none() is not None:
            raise BizException(code="EMAIL_EXISTS", message="邮箱已存在", status_code=409)
        user = User(
            username=payload.username,
            email=payload.email,
            hashed_password=await hash_password(payload.password),
            role=payload.role.value,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return user

    @staticmethod
    async def list_users(db: AsyncSession, query: UserListQuery) -> tuple[list[User], int]:
        stmt = select(User)
        count_stmt = select(func.count()).select_from(User)
        if query.username is not None:
            stmt = stmt.where(User.username == query.username)
            count_stmt = count_stmt.where(User.username == query.username)
        if query.role is not None:
            stmt = stmt.where(User.role == query.role.value)
            count_stmt = count_stmt.where(User.role == query.role.value)
        if query.is_active is not None:
            stmt = stmt.where(User.is_active.is_(query.is_active))
            count_stmt = count_stmt.where(User.is_active.is_(query.is_active))
        total = (await db.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(User.id).offset((query.page - 1) * query.size).limit(query.size)
        rows = (await db.execute(stmt)).scalars().all()
        return list(rows), total

    @staticmethod
    async def _count_active_admins(db: AsyncSession, exclude_user_id: int | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(User)
            .where(User.role == Role.ADMIN.value, User.is_active.is_(True))
        )
        if exclude_user_id is not None:
            stmt = stmt.where(User.id != exclude_user_id)
        return (await db.execute(stmt)).scalar_one()

    @staticmethod
    async def admin_update_user(
        db: AsyncSession, operator: User, target_id: int, payload: UserAdminUpdate
    ) -> User:
        """admin 修改用户。包含 SELF_PROTECTED + LAST_ADMIN 守卫。"""
        target = await UserService.get_by_id(db, target_id)
        if target is None:
            raise BizException(code="USER_NOT_FOUND", message="用户不存在", status_code=404)

        is_self = target.id == operator.id

        # 1) 改 role：不能把自己降级（除非目标 role 没变）
        if payload.role is not None and payload.role.value != target.role:
            if is_self and payload.role.value != Role.ADMIN.value:
                raise BizException(
                    code="SELF_PROTECTED",
                    message="不能修改自己的管理员角色",
                    status_code=409,
                )

        # 2) 改 is_active：不能停用自己
        if payload.is_active is not None and payload.is_active is False and target.is_active:
            if is_self:
                raise BizException(
                    code="SELF_PROTECTED",
                    message="不能停用自己",
                    status_code=409,
                )

        # 3) 改 role 到非 admin / 停用一个 admin → 检查剩余活跃 admin
        will_lose_admin = (
            (payload.role is not None and payload.role.value != Role.ADMIN.value)
            or (payload.is_active is False)
        ) and target.role == Role.ADMIN.value
        if will_lose_admin:
            others = await UserService._count_active_admins(db, exclude_user_id=target.id)
            if others < 1:
                raise BizException(
                    code="LAST_ADMIN",
                    message="至少需要保留一个活跃管理员",
                    status_code=409,
                )

        # 应用变更
        if payload.email is not None and payload.email != target.email:
            stmt = select(User).where(User.email == payload.email, User.id != target.id)
            if (await db.execute(stmt)).scalar_one_or_none() is not None:
                raise BizException(code="EMAIL_EXISTS", message="邮箱已存在", status_code=409)
            target.email = payload.email
        if payload.role is not None:
            target.role = payload.role.value
        if payload.is_active is not None:
            target.is_active = payload.is_active

        await db.flush()
        await db.refresh(target)
        logger.warning(
            "admin 变更用户: operator=%s target=%s changes=%s",
            operator.username,
            target.username,
            payload.model_dump(exclude_none=True),
        )
        return target

    @staticmethod
    async def admin_delete_user(db: AsyncSession, operator: User, target_id: int) -> None:
        target = await UserService.get_by_id(db, target_id)
        if target is None:
            raise BizException(code="USER_NOT_FOUND", message="用户不存在", status_code=404)
        if target.id == operator.id:
            raise BizException(code="SELF_PROTECTED", message="不能删除自己", status_code=409)
        if target.role == Role.ADMIN.value:
            others = await UserService._count_active_admins(db, exclude_user_id=target.id)
            if others < 1:
                raise BizException(
                    code="LAST_ADMIN",
                    message="至少需要保留一个活跃管理员",
                    status_code=409,
                )
        logger.warning("admin 删除用户: operator=%s target=%s", operator.username, target.username)
        await db.delete(target)
        await db.flush()

    @staticmethod
    async def admin_reset_password(
        db: AsyncSession, operator: User, target_id: int, new_password: str
    ) -> None:
        target = await UserService.get_by_id(db, target_id)
        if target is None:
            raise BizException(code="USER_NOT_FOUND", message="用户不存在", status_code=404)
        target.hashed_password = await hash_password(new_password)
        await db.flush()
        logger.warning("admin 重置密码: operator=%s target=%s", operator.username, target.username)
