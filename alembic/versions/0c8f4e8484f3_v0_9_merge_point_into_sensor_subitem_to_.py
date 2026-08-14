"""v0.9 merge point into sensor, subitem to project

开发阶段重置重构：
- point 与 sensor 合一（sensor 挂 device 下，含位置字段）
- subitem → project 术语回退（subitems/user_subitems → projects/user_projects）

表结构重建（drop 旧表 → create 最终结构），不迁移数据。

Revision ID: 0c8f4e8484f3
Revises: c4f21bee2f8b
Create Date: 2026-08-14 21:06:17.757147

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0c8f4e8484f3'
down_revision: str | Sequence[str] | None = 'c4f21bee2f8b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- 1. 删除旧结构（按 FK 依赖顺序；devices 列名变更，一并重建） ---
    op.drop_table('3d_models')
    op.drop_table('alerts')
    op.drop_table('analysis_jobs')
    op.drop_table('readings')
    op.drop_table('channels')
    op.drop_table('sensors')
    op.drop_table('points')
    op.drop_table('user_subitems')
    op.drop_table('devices')
    op.drop_table('subitems')

    # --- 2. 项目与授权 ---
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('location', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'user_projects',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('permission', sa.String(length=16), server_default='read', nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'project_id'),
    )

    # --- 3. 设备 ---
    op.create_table(
        'devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('device_code', sa.String(length=64), nullable=False),
        sa.Column('device_name', sa.String(length=128), nullable=True),
        sa.Column('protocol', sa.String(length=32), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='offline', nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('device_code'),
    )

    # --- 4. 传感器（point+sensor 合一） ---
    op.create_table(
        'sensors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('sensor_code', sa.String(length=64), nullable=False),
        sa.Column('sensor_name', sa.String(length=128), nullable=True),
        sa.Column('sensor_type', sa.String(length=32), nullable=True),
        sa.Column('model', sa.String(length=128), nullable=True),
        sa.Column('manufacturer', sa.String(length=64), nullable=True),
        sa.Column('install_date', sa.Date(), nullable=True),
        sa.Column('last_calibration', sa.Date(), nullable=True),
        sa.Column('position', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('device_id', 'sensor_code', name='uq_sensors_device_code'),
    )

    # --- 5. 通道 ---
    op.create_table(
        'channels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sensor_id', sa.Integer(), nullable=False),
        sa.Column('channel_code', sa.String(length=64), nullable=False),
        sa.Column('channel_type', sa.String(length=32), nullable=True),
        sa.Column('unit', sa.String(length=16), nullable=True),
        sa.Column('sampling_rate', sa.Integer(), server_default='1', nullable=False),
        sa.Column('position_offset', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('axis', sa.String(length=8), nullable=True),
        sa.Column('alert_rules', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['sensor_id'], ['sensors.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sensor_id', 'channel_code'),
    )

    # --- 6. 时序读数 ---
    op.create_table(
        'readings',
        sa.Column('time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('quality', sa.String(length=8), server_default='good', nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ),
        sa.PrimaryKeyConstraint('time', 'channel_id'),
    )

    # --- 7. 3D 模型 ---
    op.create_table(
        '3d_models',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('original_key', sa.String(length=256), nullable=False),
        sa.Column('original_name', sa.String(length=256), nullable=False),
        sa.Column('source_format', sa.String(length=16), nullable=False),
        sa.Column('glb_key', sa.String(length=256), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_3d_models_project_id'), '3d_models', ['project_id'], unique=False)

    # --- 8. 告警 ---
    op.create_table(
        'alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('alert_type', sa.String(length=32), nullable=True),
        sa.Column('level', sa.String(length=16), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('value', sa.Float(), nullable=True),
        sa.Column('threshold', sa.Float(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # --- 9. 分析任务 ---
    op.create_table(
        'analysis_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('plugin', sa.String(length=64), nullable=False),
        sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('result_key', sa.String(length=256), nullable=True),
        sa.Column('result_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('submitted_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ),
        sa.ForeignKeyConstraint(['submitted_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    # 开发阶段重置重构，不支持降级（数据已丢）
    raise NotImplementedError("v0.9 重构为开发阶段重置，不支持 downgrade")
