"""时序数据相关 Schema。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.constants import Quality


class ReadingIn(BaseModel):
    """边缘网关上行的单条读数（按编码寻址，不传内部 ID）。"""

    device_code: str = Field(min_length=1, max_length=64)
    point_code: str = Field(min_length=1, max_length=64)
    timestamp: datetime
    value: float
    unit: str = ""
    quality: Quality = Quality.GOOD
    extra: dict[str, Any] = Field(default_factory=dict)


class DataBatchIngest(BaseModel):
    readings: list[ReadingIn] = Field(min_length=1, max_length=10000)


class TimeSeriesPoint(BaseModel):
    ts: datetime
    value: float | None = None
    avg_val: float | None = None
    max_val: float | None = None
    min_val: float | None = None
    rms_val: float | None = None


class TimeSeriesOut(BaseModel):
    point_id: int
    interval: str
    data: list[TimeSeriesPoint]
