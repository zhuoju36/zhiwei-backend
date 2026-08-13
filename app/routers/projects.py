"""项目 CRUD 与用户授权。"""

from fastapi import Query

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.middleware import create_router
from app.dependencies import AdminUser, CurrentUser, DbSession, check_project_access
from app.schemas.base import PageSchema
from app.schemas.project import ProjectAssignIn, ProjectCreate, ProjectOut, ProjectUpdate
from app.services.project_service import ProjectService

router = create_router(prefix="/projects", tags=["项目"])


@router.get("", response_model=PageSchema[ProjectOut])
async def list_projects(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageSchema[ProjectOut]:
    projects, total = await ProjectService.list_projects(db, current_user, page, size)
    return PageSchema(
        total=total,
        page=page,
        size=size,
        items=[ProjectOut.model_validate(p) for p in projects],
    )


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(payload: ProjectCreate, db: DbSession, admin: AdminUser) -> ProjectOut:
    project = await ProjectService.create_project(db, payload, admin)
    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, db: DbSession, current_user: CurrentUser) -> ProjectOut:
    await check_project_access(db, current_user, project_id)
    project = await ProjectService.get_project(db, project_id)
    return ProjectOut.model_validate(project)


@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: int, payload: ProjectUpdate, db: DbSession, admin: AdminUser
) -> ProjectOut:
    project = await ProjectService.update_project(db, project_id, payload)
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, db: DbSession, admin: AdminUser) -> None:
    await ProjectService.delete_project(db, project_id)


@router.post("/{project_id}/users", status_code=204)
async def assign_user(
    project_id: int, payload: ProjectAssignIn, db: DbSession, admin: AdminUser
) -> None:
    await ProjectService.assign_user(db, project_id, payload.user_id, payload.permission.value)
