"""子项（监测范围）与用户-子项授权关联模型。

v0.8a 重命名：原 `projects` / `user_projects` 改名为 `subitems` /
`user_subitems`，列名 `project_id` 改 `subitem_id`。Schema 物理结构不变。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.user import User


class Subitem(Base):
    __tablename__ = "subitems"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # {lat, lng, address}
    model_file_key: Mapped[str | None] = mapped_column(String(256))  # MinIO 中 GLB 文件路径
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user_links: Mapped[list[UserSubitem]] = relationship(
        back_populates="subitem", cascade="all, delete-orphan"
    )
    devices: Mapped[list[Device]] = relationship(back_populates="subitem")


class UserSubitem(Base):
    """用户-子项多对多关联，控制数据权限。"""

    __tablename__ = "user_subitems"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    subitem_id: Mapped[int] = mapped_column(
        ForeignKey("subitems.id", ondelete="CASCADE"), primary_key=True
    )
    permission: Mapped[str] = mapped_column(String(16), default="read", server_default="read")

    user: Mapped[User] = relationship(back_populates="subitem_links")
    subitem: Mapped[Subitem] = relationship(back_populates="user_links")
