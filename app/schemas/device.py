"""设备 Schema。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import DeviceStatus


class DeviceCreate(BaseModel):
    project_id: int
    device_code: str = Field(min_length=1, max_length=64)
    device_name: str | None = Field(default=None, max_length=128)
    protocol: str = Field(min_length=1, max_length=32)
    config: dict[str, Any] = Field(default_factory=dict)


class DeviceUpdate(BaseModel):
    device_name: str | None = Field(default=None, max_length=128)
    protocol: str | None = Field(default=None, max_length=32)
    config: dict[str, Any] | None = None
    status: DeviceStatus | None = None
    last_seen: datetime | None = None


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    device_code: str
    device_name: str | None
    protocol: str
    config: dict[str, Any]
    status: str
    last_seen: datetime | None
    created_at: datetime
