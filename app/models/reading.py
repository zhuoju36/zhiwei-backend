"""时序数据模型：按 channel 存储原始读数（TimescaleDB hypertable）。

替代 v0.7 的 sensor_raw / sensor_feature。统一只存原始读数；
连续聚合（如 1min 均值）由 init_db.py 在 readings 上单独创建。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.channel import Channel


class Reading(Base):
    __tablename__ = "readings"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), primary_key=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    quality: Mapped[str] = mapped_column(String(8), default="good", server_default="good")
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)

    channel: Mapped[Channel] = relationship(back_populates="readings")
