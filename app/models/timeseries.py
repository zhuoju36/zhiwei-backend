"""时序数据模型（TimescaleDB Hypertable）。

注意：hypertable 转换、连续聚合与保留策略由 scripts/init_db.py 完成，
Alembic 只负责建普通表结构。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SensorRaw(Base):
    """高频原始采样数据（边缘上传的原始采样点）。"""

    __tablename__ = "sensor_raw"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    device_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    point_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    quality: Mapped[str] = mapped_column(String(8), default="good", server_default="good")
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)


class SensorFeature(Base):
    """特征数据（边缘预处理后的 1Hz 特征）。"""

    __tablename__ = "sensor_feature"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    device_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    point_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    avg_value: Mapped[float | None] = mapped_column(Float)
    max_value: Mapped[float | None] = mapped_column(Float)
    min_value: Mapped[float | None] = mapped_column(Float)
    rms_value: Mapped[float | None] = mapped_column(Float)  # 有效值，对加速度尤为重要
    peak_factor: Mapped[float | None] = mapped_column(Float)  # 峰值因子
