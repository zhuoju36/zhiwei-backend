"""用户管理路由：仅 admin。"""

from fastapi import Query, status

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Role
from app.core.middleware import create_router
from app.dependencies import AdminUser, DbSession
from app.schemas.base import PageSchema
from app.schemas.user import (
    UserAdminUpdate,
    UserCreate,
    UserListQuery,
    UserOut,
    UserPasswordReset,
)
from app.services import user_service

router = create_router(prefix="/users", tags=["用户"])


@router.get("", response_model=PageSchema[UserOut])
async def list_users(
    db: DbSession,
    admin: AdminUser,
    username: str | None = Query(None),
    role: Role | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageSchema[UserOut]:
    query = UserListQuery(username=username, role=role, is_active=is_active, page=page, size=size)
    rows, total = await user_service.UserService.list_users(db, query)
    return PageSchema(
        total=total,
        page=page,
        size=size,
        items=[UserOut.model_validate(u) for u in rows],
    )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, db: DbSession, admin: AdminUser) -> UserOut:
    user = await user_service.UserService.create_user(db, payload)
    await db.commit()
    return UserOut.model_validate(user)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, db: DbSession, admin: AdminUser) -> UserOut:
    from app.core.exceptions import BizException

    user = await user_service.UserService.get_by_id(db, user_id)
    if user is None:
        raise BizException(code="USER_NOT_FOUND", message="用户不存在", status_code=404)
    return UserOut.model_validate(user)


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int, payload: UserAdminUpdate, db: DbSession, admin: AdminUser
) -> UserOut:
    user = await user_service.UserService.admin_update_user(db, admin, user_id, payload)
    await db.commit()
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: DbSession, admin: AdminUser) -> None:
    await user_service.UserService.admin_delete_user(db, admin, user_id)
    await db.commit()


@router.post("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: int,
    payload: UserPasswordReset,
    db: DbSession,
    admin: AdminUser,
) -> None:
    await user_service.UserService.admin_reset_password(db, admin, user_id, payload.new_password)
    await db.commit()
