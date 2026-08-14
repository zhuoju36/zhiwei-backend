"""测点模型：物理位置。

v0.8b 起 `point` 只是物理位置（塔 3 第 1 个测点），unit / sampling_rate /
alert_rules 下沉到 channel。一个 point 可挂多个 sensor，每个 sensor 有 1-N 个 channel。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.sensor import Sensor


class Point(Base):
    __tablename__ = "points"
    __table_args__ = (UniqueConstraint("device_id", "point_code", name="uq_points_device_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    point_code: Mapped[str] = mapped_column(String(64), nullable=False)  # 测点编码（位置 ID）
    point_name: Mapped[str | None] = mapped_column(String(128))
    point_type: Mapped[str | None] = mapped_column(String(32))  # 位置类型，如 structural_joint
    position: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # {x, y, z} 三维坐标
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    device: Mapped[Device] = relationship(back_populates="points")
    sensors: Mapped[list[Sensor]] = relationship(
        back_populates="point", cascade="all, delete-orphan"
    )
