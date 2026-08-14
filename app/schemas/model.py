"""3D 模型 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ModelUploadOut(BaseModel):
    model_id: int
    status: str


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subitem_id: int
    original_name: str
    source_format: str
    glb_key: str | None
    status: str
    error: str | None
    created_at: datetime
    finished_at: datetime | None
