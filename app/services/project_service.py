"""项目业务逻辑。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import Role
from app.core.exceptions import BizException
from app.models.project import Project, UserProject
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectService:
    @staticmethod
    async def list_projects(
        db: AsyncSession, user: User, page: int, size: int
    ) -> tuple[list[Project], int]:
        stmt = select(Project)
        count_stmt = select(func.count()).select_from(Project)
        if user.role != Role.ADMIN:
            # 普通用户只能看到被授权的项目
            stmt = stmt.join(UserProject, UserProject.project_id == Project.id).where(
                UserProject.user_id == user.id
            )
            count_stmt = count_stmt.join(UserProject, UserProject.project_id == Project.id).where(
                UserProject.user_id == user.id
            )
        total = (await db.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(Project.id).offset((page - 1) * size).limit(size)
        result = await db.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_project(db: AsyncSession, project_id: int) -> Project:
        project = await db.get(Project, project_id)
        if project is None:
            raise BizException(code="PROJECT_NOT_FOUND", message="项目不存在", status_code=404)
        return project

    @staticmethod
    async def create_project(db: AsyncSession, payload: ProjectCreate, creator: User) -> Project:
        project = Project(
            name=payload.name,
            description=payload.description,
            location=payload.location,
            created_by=creator.id,
        )
        db.add(project)
        await db.flush()
        return project

    @staticmethod
    async def update_project(db: AsyncSession, project_id: int, payload: ProjectUpdate) -> Project:
        project = await ProjectService.get_project(db, project_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(project, field, value)
        await db.flush()
        return project

    @staticmethod
    async def delete_project(db: AsyncSession, project_id: int) -> None:
        project = await ProjectService.get_project(db, project_id)
        await db.delete(project)
        await db.flush()

    @staticmethod
    async def assign_user(db: AsyncSession, project_id: int, user_id: int, permission: str) -> None:
        await ProjectService.get_project(db, project_id)
        if await db.get(User, user_id) is None:
            raise BizException(code="USER_NOT_FOUND", message="用户不存在", status_code=404)
        link = await db.get(UserProject, (user_id, project_id))
        if link is None:
            db.add(UserProject(user_id=user_id, project_id=project_id, permission=permission))
        else:
            link.permission = permission
        await db.flush()
