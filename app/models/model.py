"""3D 模型模型：一个子项可上传多个模型（v0.8c）。

每条记录对应一次上传的源文件（MinIO）与其 GLB 转换产物（MinIO）。
status 状态机：pending -> processing -> success / failed。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

if TYPE_CHECKING:
    pass


class Model(Base):
    __tablename__ = "3d_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    original_key: Mapped[str] = mapped_column(String(256), nullable=False)  # MinIO 源文件
    original_name: Mapped[str] = mapped_column(String(256), nullable=False)  # 用户上传文件名
    source_format: Mapped[str] = mapped_column(String(16), nullable=False)  # obj/stl/ply/gltf/glb
    glb_key: Mapped[str | None] = mapped_column(String(256))  # MinIO GLB 产物
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending"
    )  # pending/processing/success/failed
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
