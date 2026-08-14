"""项目（监测范围）与用户-项目授权关联模型。

v0.9 术语回退：原 `projects` / `user_projects` 改回 `projects` / `user_projects`，
列名 `project_id` 改 `project_id`。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.user import User


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # {lat, lng, address}
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user_links: Mapped[list[UserProject]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    devices: Mapped[list[Device]] = relationship(back_populates="project")


class UserProject(Base):
    """用户-项目多对多关联，控制数据权限。"""

    __tablename__ = "user_projects"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    permission: Mapped[str] = mapped_column(String(16), default="read", server_default="read")

    user: Mapped[User] = relationship(back_populates="project_links")
    project: Mapped[Project] = relationship(back_populates="user_links")
