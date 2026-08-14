"""平台元数据 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlatformOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform_name: str
    contact_email: str | None = None
    description: str | None = None
    logo_url: str | None = None
    updated_at: datetime
    updated_by: int | None = None


class PlatformUpdate(BaseModel):
    """所有字段可选；至少传一个。"""

    platform_name: str | None = Field(default=None, min_length=1, max_length=128)
    contact_email: str | None = Field(default=None, max_length=128)
    description: str | None = None
    logo_url: str | None = Field(default=None, max_length=512)

    def is_empty(self) -> bool:
        return all(
            getattr(self, f) is None
            for f in ("platform_name", "contact_email", "description", "logo_url")
        )
