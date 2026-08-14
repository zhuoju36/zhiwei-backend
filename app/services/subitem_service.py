"""子项业务逻辑。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import Role
from app.core.exceptions import BizException
from app.models.subitem import Subitem, UserSubitem
from app.models.user import User
from app.schemas.subitem import SubitemCreate, SubitemUpdate


class SubitemService:
    @staticmethod
    async def list_subitems(
        db: AsyncSession, user: User, page: int, size: int
    ) -> tuple[list[Subitem], int]:
        stmt = select(Subitem)
        count_stmt = select(func.count()).select_from(Subitem)
        if user.role != Role.ADMIN:
            stmt = stmt.join(UserSubitem, UserSubitem.subitem_id == Subitem.id).where(
                UserSubitem.user_id == user.id
            )
            count_stmt = count_stmt.join(UserSubitem, UserSubitem.subitem_id == Subitem.id).where(
                UserSubitem.user_id == user.id
            )
        total = (await db.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(Subitem.id).offset((page - 1) * size).limit(size)
        result = await db.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_subitem(db: AsyncSession, subitem_id: int) -> Subitem:
        subitem = await db.get(Subitem, subitem_id)
        if subitem is None:
            raise BizException(code="SUBITEM_NOT_FOUND", message="子项不存在", status_code=404)
        return subitem

    @staticmethod
    async def create_subitem(db: AsyncSession, payload: SubitemCreate, creator: User) -> Subitem:
        subitem = Subitem(
            name=payload.name,
            description=payload.description,
            location=payload.location,
            created_by=creator.id,
        )
        db.add(subitem)
        await db.flush()
        return subitem

    @staticmethod
    async def update_subitem(db: AsyncSession, subitem_id: int, payload: SubitemUpdate) -> Subitem:
        subitem = await SubitemService.get_subitem(db, subitem_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(subitem, field, value)
        await db.flush()
        return subitem

    @staticmethod
    async def delete_subitem(db: AsyncSession, subitem_id: int) -> None:
        subitem = await SubitemService.get_subitem(db, subitem_id)
        await db.delete(subitem)
        await db.flush()

    @staticmethod
    async def assign_user(db: AsyncSession, subitem_id: int, user_id: int, permission: str) -> None:
        await SubitemService.get_subitem(db, subitem_id)
        if await db.get(User, user_id) is None:
            raise BizException(code="USER_NOT_FOUND", message="用户不存在", status_code=404)
        link = await db.get(UserSubitem, (user_id, subitem_id))
        if link is None:
            db.add(UserSubitem(user_id=user_id, subitem_id=subitem_id, permission=permission))
        else:
            link.permission = permission
        await db.flush()
