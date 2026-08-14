"""用户相关 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Role


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role = Role.USER


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: Role | None = None
    is_active: bool | None = None


class UserAdminUpdate(BaseModel):
    """admin 更新普通用户 / 其他 admin（不含密码，密码走单独端点）。"""

    email: EmailStr | None = None
    role: Role | None = None
    is_active: bool | None = None


class UserPasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class UserListQuery(BaseModel):
    username: str | None = Field(default=None, max_length=64, description="精确匹配")
    role: Role | None = None
    is_active: bool | None = None
    page: int = Field(default=1, ge=1)
    size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime


class UserLogin(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str
