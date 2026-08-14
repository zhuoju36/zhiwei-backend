"""传感器模型（v0.9 重构：原 point 与 sensor 合一，一个 device 下直接挂 sensor）。

一个 sensor = 一个物理测点 + 其仪器（实际部署中一个测点对应一个传感器）：
- 位置信息（原 point）：device_id / sensor_code（同 device 内唯一）/ position /
  sensor_name / sensor_type / is_active
- 仪器元数据（原 sensor）：model / manufacturer / install_date / last_calibration / metadata_

拓扑链（v0.9 起六层）：project → device → sensor → channel → readings
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.device import Device


class Sensor(Base):
    __tablename__ = "sensors"
    __table_args__ = (UniqueConstraint("device_id", "sensor_code", name="uq_sensors_device_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    sensor_code: Mapped[str] = mapped_column(String(64), nullable=False)  # 同 device 内唯一
    sensor_name: Mapped[str | None] = mapped_column(String(128))
    sensor_type: Mapped[str | None] = mapped_column(String(32))  # 位置/类型，如 structural_joint
    model: Mapped[str | None] = mapped_column(String(128))  # 仪器型号，如 "XYZ-123"
    manufacturer: Mapped[str | None] = mapped_column(String(64))
    install_date: Mapped[date | None] = mapped_column()
    last_calibration: Mapped[date | None] = mapped_column()
    position: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # {x, y, z} 三维坐标
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    note: Mapped[str | None] = mapped_column(Text)  # 用户备注
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    device: Mapped[Device] = relationship(back_populates="sensors")
    channels: Mapped[list[Channel]] = relationship(
        back_populates="sensor", cascade="all, delete-orphan"
    )
