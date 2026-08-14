"""通道模型：一个传感器的一条信号通道。

每个 channel 对应一组时序数据（readings）。channel 携带单位、采样率、告警规则。
3 轴 IMU：一个 sensor 有 X / Y / Z 三个 channel。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.reading import Reading
    from app.models.sensor import Sensor


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id"), nullable=False)
    channel_code: Mapped[str] = mapped_column(String(64), nullable=False)  # 如 "X" / "Y" / "T"
    channel_type: Mapped[str | None] = mapped_column(String(32))  # acceleration/strain/temp...
    unit: Mapped[str | None] = mapped_column(String(16))  # m/s2, με, °C, mm
    sampling_rate: Mapped[int] = mapped_column(Integer, default=1, server_default="1")  # Hz
    position_offset: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # {dx,dy,dz} 相对偏移
    axis: Mapped[str | None] = mapped_column(String(8))  # "x" / "y" / "z"（3D 可视化用）
    alert_rules: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)  # 阈值告警规则
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sensor: Mapped[Sensor] = relationship(back_populates="channels")
    readings: Mapped[list[Reading]] = relationship(back_populates="channel")
