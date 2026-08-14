"""告警记录模型。"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    alert_type: Mapped[str | None] = mapped_column(String(32))  # threshold, fft, trend...
    level: Mapped[str | None] = mapped_column(String(16))  # info, warning, danger
    message: Mapped[str | None] = mapped_column(Text)
    value: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_resolved: Mapped[bool] = mapped_column(default=False, server_default="false")
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
