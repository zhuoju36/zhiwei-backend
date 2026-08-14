"""子项相关 Schema。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import SubitemPermission


class SubitemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    location: dict[str, Any] | None = None  # {lat, lng, address}


class SubitemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    location: dict[str, Any] | None = None
    model_file_key: str | None = None


class SubitemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    location: dict[str, Any] | None
    model_file_key: str | None
    created_by: int | None
    created_at: datetime


class SubitemAssignIn(BaseModel):
    user_id: int
    permission: SubitemPermission = SubitemPermission.READ
