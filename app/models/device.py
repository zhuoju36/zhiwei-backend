"""设备模型。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.point import Point
    from app.models.project import Project


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    device_code: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )  # 设备唯一编码
    device_name: Mapped[str | None] = mapped_column(String(128))
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)  # modbus_tcp, mqtt, opcua...
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # 协议配置参数
    status: Mapped[str] = mapped_column(String(16), default="offline", server_default="offline")
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="devices")
    points: Mapped[list[Point]] = relationship(back_populates="device")
