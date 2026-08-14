"""传感器模型：挂在一个物理测点下的具体仪器。

一个 point（测点/位置）可挂多个 sensor（IMU、温湿度计、应变计等）。
单通道场景下 sensor 与 channel 一一对应，但传感器元数据（型号/校准）仍在
sensor 层而不在 channel 层，避免多通道共享元数据时冗余。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.point import Point


class Sensor(Base):
    __tablename__ = "sensors"

    id: Mapped[int] = mapped_column(primary_key=True)
    point_id: Mapped[int] = mapped_column(ForeignKey("points.id"), nullable=False)
    sensor_code: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # 测点内唯一编码，如 "IMU1"
    model: Mapped[str | None] = mapped_column(String(128))  # 型号，如 "XYZ-123"
    manufacturer: Mapped[str | None] = mapped_column(String(64))
    install_date: Mapped[date | None] = mapped_column()
    last_calibration: Mapped[date | None] = mapped_column()
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    point: Mapped[Point] = relationship(back_populates="sensors")
    channels: Mapped[list[Channel]] = relationship(
        back_populates="sensor", cascade="all, delete-orphan"
    )
