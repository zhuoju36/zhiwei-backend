"""子项 CRUD 与用户授权（仅 admin 可创建/更新/删除/授权；普通用户可读被授权的）。"""

from fastapi import Query

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.middleware import create_router
from app.dependencies import AdminUser, CurrentUser, DbSession, check_subitem_access
from app.schemas.base import PageSchema
from app.schemas.subitem import SubitemAssignIn, SubitemCreate, SubitemOut, SubitemUpdate
from app.services.subitem_service import SubitemService

router = create_router(prefix="/subitems", tags=["子项"])


@router.get("", response_model=PageSchema[SubitemOut])
async def list_subitems(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageSchema[SubitemOut]:
    subitems, total = await SubitemService.list_subitems(db, current_user, page, size)
    return PageSchema(
        total=total,
        page=page,
        size=size,
        items=[SubitemOut.model_validate(s) for s in subitems],
    )


@router.post("", response_model=SubitemOut, status_code=201)
async def create_subitem(payload: SubitemCreate, db: DbSession, admin: AdminUser) -> SubitemOut:
    subitem = await SubitemService.create_subitem(db, payload, admin)
    return SubitemOut.model_validate(subitem)


@router.get("/{subitem_id}", response_model=SubitemOut)
async def get_subitem(subitem_id: int, db: DbSession, current_user: CurrentUser) -> SubitemOut:
    await check_subitem_access(db, current_user, subitem_id)
    subitem = await SubitemService.get_subitem(db, subitem_id)
    return SubitemOut.model_validate(subitem)


@router.put("/{subitem_id}", response_model=SubitemOut)
async def update_subitem(
    subitem_id: int, payload: SubitemUpdate, db: DbSession, admin: AdminUser
) -> SubitemOut:
    subitem = await SubitemService.update_subitem(db, subitem_id, payload)
    return SubitemOut.model_validate(subitem)


@router.delete("/{subitem_id}", status_code=204)
async def delete_subitem(subitem_id: int, db: DbSession, admin: AdminUser) -> None:
    await SubitemService.delete_subitem(db, subitem_id)


@router.post("/{subitem_id}/users", status_code=204)
async def assign_user(
    subitem_id: int, payload: SubitemAssignIn, db: DbSession, admin: AdminUser
) -> None:
    await SubitemService.assign_user(db, subitem_id, payload.user_id, payload.permission.value)
