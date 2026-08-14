"""传感器 / 通道 Schema。"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.point import AlertRule


class SensorCreate(BaseModel):
    point_id: int
    sensor_code: str = Field(min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    manufacturer: str | None = Field(default=None, max_length=64)
    install_date: date | None = None
    last_calibration: date | None = None
    metadata: dict[str, Any] | None = None


class SensorUpdate(BaseModel):
    model: str | None = Field(default=None, max_length=128)
    manufacturer: str | None = Field(default=None, max_length=64)
    install_date: date | None = None
    last_calibration: date | None = None
    metadata: dict[str, Any] | None = None


class SensorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    point_id: int
    sensor_code: str
    model: str | None
    manufacturer: str | None
    install_date: date | None
    last_calibration: date | None
    metadata_: dict[str, Any] | None = Field(
        validation_alias="metadata", serialization_alias="metadata"
    )
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
