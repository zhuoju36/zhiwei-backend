"""通用 Schema：分页与统一响应。"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

T = TypeVar("T")


class PageParams(BaseModel):
    page: int = Field(1, ge=1)
    size: int = Field(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class PageSchema(BaseModel, Generic[T]):
    total: int
    page: int
    size: int
    items: list[T]


class ResponseSchema(BaseModel, Generic[T]):
    """统一响应结构（实际包装由 EnvelopeRoute 自动完成，此类用于文档与显式构造）。"""

    code: str = "OK"
    message: str = "success"
    data: T | None = None
    timestamp: str = ""
