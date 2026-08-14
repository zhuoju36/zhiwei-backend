"""测点 Schema（v0.8b 精简：point 只是物理位置，不含 unit/sampling_rate/alert_rules）。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AlertRule(BaseModel):
    """阈值告警规则：value 与 threshold 经 operator 比较，越界时按 level 触发告警。"""

    operator: str = Field(pattern=r"^(gt|lt|ge|le|eq|ne)$", description="比较运算符")
    threshold: float
    level: str = Field(pattern=r"^(info|warning|danger)$", description="告警级别")
    message: str | None = None
    suppress_seconds: int = Field(default=60, ge=0, description="抑制窗口（秒）")


class PointCreate(BaseModel):
    device_id: int
    point_code: str = Field(min_length=1, max_length=64)
    point_name: str | None = Field(default=None, max_length=128)
    point_type: str | None = Field(default=None, max_length=32)
    position: dict[str, Any] | None = None


class PointUpdate(BaseModel):
    point_name: str | None = Field(default=None, max_length=128)
    point_type: str | None = Field(default=None, max_length=32)
    position: dict[str, Any] | None = None
    is_active: bool | None = None


class PointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    point_code: str
    point_name: str | None
    point_type: str | None
    position: dict[str, Any] | None
    is_active: bool
    created_at: datetime
