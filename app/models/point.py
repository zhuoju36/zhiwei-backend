"""测点模型（与三维模型坐标绑定）。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.device import Device


class Point(Base):
    __tablename__ = "points"
    __table_args__ = (UniqueConstraint("device_id", "point_code", name="uq_points_device_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    point_code: Mapped[str] = mapped_column(String(64), nullable=False)  # 测点编码
    point_name: Mapped[str | None] = mapped_column(String(128))
    point_type: Mapped[str | None] = mapped_column(String(32))  # acceleration, strain, temp...
    unit: Mapped[str | None] = mapped_column(String(16))  # m/s2, με, °C, mm
    position: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # {x, y, z} 三维坐标
    alert_rules: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)  # 阈值告警规则
    sampling_rate: Mapped[int] = mapped_column(Integer, default=1, server_default="1")  # Hz
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    device: Mapped[Device] = relationship(back_populates="points")
