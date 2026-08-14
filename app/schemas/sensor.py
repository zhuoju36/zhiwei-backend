"""传感器 / 通道 Schema（v0.9：sensor 含原 point 的位置字段）。"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AlertRule(BaseModel):
    """阈值告警规则：value 与 threshold 经 operator 比较，越界时按 level 触发告警。"""

    operator: str = Field(pattern=r"^(gt|lt|ge|le|eq|ne)$", description="比较运算符")
    threshold: float
    level: str = Field(pattern=r"^(info|warning|danger)$", description="告警级别")
    message: str | None = None
    suppress_seconds: int = Field(default=60, ge=0, description="抑制窗口（秒）")


class SensorCreate(BaseModel):
    device_id: int
    sensor_code: str = Field(min_length=1, max_length=64)
    sensor_name: str | None = Field(default=None, max_length=128)
    sensor_type: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=128)
    manufacturer: str | None = Field(default=None, max_length=64)
    install_date: date | None = None
    last_calibration: date | None = None
    position: dict[str, Any] | None = None  # {x, y, z} 三维坐标
    metadata: dict[str, Any] | None = None


class SensorUpdate(BaseModel):
    sensor_name: str | None = Field(default=None, max_length=128)
    sensor_type: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=128)
    manufacturer: str | None = Field(default=None, max_length=64)
    install_date: date | None = None
    last_calibration: date | None = None
    position: dict[str, Any] | None = None
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


class SensorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    sensor_code: str
    sensor_name: str | None
    sensor_type: str | None
    model: str | None
    manufacturer: str | None
    install_date: date | None
    last_calibration: date | None
    position: dict[str, Any] | None
    is_active: bool
    metadata_: dict[str, Any] | None = Field(serialization_alias="metadata")
    created_at: datetime


class ChannelCreate(BaseModel):
    sensor_id: int
    channel_code: str = Field(min_length=1, max_length=64)
    channel_type: str | None = Field(default=None, max_length=32)
    unit: str | None = Field(default=None, max_length=16)
    sampling_rate: int = Field(default=1, ge=1)
    position_offset: dict[str, Any] | None = None
    axis: str | None = Field(default=None, max_length=8)
    alert_rules: list[AlertRule] | None = None


class ChannelUpdate(BaseModel):
    channel_type: str | None = Field(default=None, max_length=32)
    unit: str | None = Field(default=None, max_length=16)
    sampling_rate: int | None = Field(default=None, ge=1)
    position_offset: dict[str, Any] | None = None
    axis: str | None = Field(default=None, max_length=8)
    alert_rules: list[AlertRule] | None = None
    is_active: bool | None = None


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sensor_id: int
    channel_code: str
    channel_type: str | None
    unit: str | None
    sampling_rate: int
    position_offset: dict[str, Any] | None
    axis: str | None
    alert_rules: list[dict[str, Any]] | None
    is_active: bool
    created_at: datetime
