"""add platform_settings

Revision ID: 7c74c5b67148
Revises: 6c0943361e16
Create Date: 2026-08-14 09:59:15.904478

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '7c74c5b67148'
down_revision: str | Sequence[str] | None = '6c0943361e16'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform_name", sa.String(length=128), nullable=False),
        sa.Column("contact_email", sa.String(length=128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.String(length=512), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.CheckConstraint("id = 1", name="ck_platform_settings_singleton"),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
