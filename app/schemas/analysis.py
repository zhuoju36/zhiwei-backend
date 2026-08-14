"""分析任务 Schema。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalysisJobCreate(BaseModel):
    channel_id: int
    plugin: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)


class AnalysisSubmitOut(BaseModel):
    job_id: int
    status: str


class AnalysisJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
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


class AnalysisPluginMeta(BaseModel):
    """分析插件元信息（/analysis/plugins，前端渲染表单与结果视图用）。"""

    name: str
    display_name: str
    description: str
    version: str
    input_channels: int
    min_samples: int
    params_schema: dict[str, Any]
    result_view: str
