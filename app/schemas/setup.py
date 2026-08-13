"""首次部署引导 Schema。"""

from typing import Any

from pydantic import BaseModel, EmailStr, Field


class SetupStatusResponse(BaseModel):
    initialized: bool
    password_requirements: dict[str, Any]


class InitAdminRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    # 不强制 role（v0.6 总是创建 admin）


class InitAdminResponse(BaseModel):
    admin_id: int
    username: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
