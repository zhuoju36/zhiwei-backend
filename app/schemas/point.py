"""测点 Schema。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AlertRule(BaseModel):
    """阈值告警规则：value 与 threshold 经 operator 比较，越界时按 level 触发告警。"""

    operator: str = Field(pattern=r"^(gt|lt|ge|le|eq|ne)$", description="比较运算符")
    threshold: float
    level: str = Field(pattern=r"^(info|warning|danger)$", description="告警级别")
    message: str | None = None


class PointCreate(BaseModel):
    device_id: int
    point_code: str = Field(min_length=1, max_length=64)
    point_name: str | None = Field(default=None, max_length=128)
    point_type: str | None = Field(default=None, max_length=32)
    unit: str | None = Field(default=None, max_length=16)
    position: dict[str, Any] | None = None
    alert_rules: list[AlertRule] | None = None
    sampling_rate: int = Field(default=1, ge=1)


class PointUpdate(BaseModel):
    point_name: str | None = Field(default=None, max_length=128)
    point_type: str | None = Field(default=None, max_length=32)
    unit: str | None = Field(default=None, max_length=16)
    position: dict[str, Any] | None = None
    alert_rules: list[AlertRule] | None = None
    sampling_rate: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class PointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    point_code: str
    point_name: str | None
    point_type: str | None
    unit: str | None
    position: dict[str, Any] | None
    alert_rules: list[dict[str, Any]] | None
    sampling_rate: int
    is_active: bool
    created_at: datetime
