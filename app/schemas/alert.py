"""告警 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import AlertLevel


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    point_id: int
    alert_type: str | None
    level: str | None
    message: str | None
    value: float | None
    threshold: float | None
    started_at: datetime
    ended_at: datetime | None
    is_resolved: bool
    resolved_by: int | None


class AlertListQuery(BaseModel):
    """告警列表查询参数（也可用 FastAPI Query 直接声明）。"""

    subitem_id: int | None = None
    point_id: int | None = None
    level: AlertLevel | None = None
    is_resolved: bool | None = None
    start: datetime | None = None
    end: datetime | None = None
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=200)
