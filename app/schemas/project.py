"""项目相关 Schema。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import ProjectPermission


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    location: dict[str, Any] | None = None  # {lat, lng, address}


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    location: dict[str, Any] | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    location: dict[str, Any] | None
    created_by: int | None
    created_at: datetime


class ProjectAssignIn(BaseModel):
    user_id: int
    permission: ProjectPermission = ProjectPermission.READ
