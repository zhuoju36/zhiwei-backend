"""平台元数据模型（单行表 id=1）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlatformSettings(Base):
    __tablename__ = "platform_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_platform_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    platform_name: Mapped[str] = mapped_column(String(128), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(String(512))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
