"""v0.8a rename project to subitem

Revision ID: 1e4cdedf9b41
Revises: 7c74c5b67148
Create Date: 2026-08-14 10:38:45.000000

仅术语重命名，schema 物理结构不变：
- user_projects.user_id / subitem_id 列 + 表名 → user_subitems
- projects 表 → subitems
- devices.project_id 列 → subitem_id
对应 FK 约束 drop + recreate（列重命名后必须）。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "1e4cdedf9b41"
down_revision: str | Sequence[str] | None = "7c74c5b67148"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. user_projects.user_id 列名 → 保留，user_projects.project_id → subitem_id
    op.drop_constraint(
        "user_projects_project_id_fkey", "user_projects", type_="foreignkey"
    )
    op.alter_column("user_projects", "project_id", new_column_name="subitem_id")
    op.create_foreign_key(
        "user_subitems_subitem_id_fkey",
        "user_projects",
        "projects",
        ["subitem_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 2. user_projects 表名 → user_subitems
    op.rename_table("user_projects", "user_subitems")

    # 3. projects 表名 → subitems
    op.rename_table("projects", "subitems")

    # 4. devices.project_id → subitem_id
    op.drop_constraint("devices_project_id_fkey", "devices", type_="foreignkey")
    op.alter_column("devices", "project_id", new_column_name="subitem_id")
    op.create_foreign_key(
        "devices_subitem_id_fkey", "devices", "subitems", ["subitem_id"], ["id"]
    )


def downgrade() -> None:
    # 反向
    op.drop_constraint("devices_subitem_id_fkey", "devices", type_="foreignkey")
    op.alter_column("devices", "subitem_id", new_column_name="project_id")
    op.create_foreign_key(
        "devices_project_id_fkey", "devices", "projects", ["project_id"], ["id"]
    )

    op.rename_table("subitems", "projects")

    op.rename_table("user_subitems", "user_projects")
    op.drop_constraint(
        "user_subitems_subitem_id_fkey", "user_subitems", type_="foreignkey"
    )
    op.alter_column("user_subitems", "subitem_id", new_column_name="project_id")
    op.create_foreign_key(
        "user_projects_project_id_fkey",
        "user_projects",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
