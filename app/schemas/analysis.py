"""分析任务 Schema。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalysisJobCreate(BaseModel):
    point_id: int
    plugin: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)


class AnalysisSubmitOut(BaseModel):
    job_id: int
    status: str


class AnalysisJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    point_id: int
    plugin: str
    params: dict[str, Any]
    status: str
    result_key: str | None
    result_summary: dict[str, Any] | None
    error: str | None
    submitted_by: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
