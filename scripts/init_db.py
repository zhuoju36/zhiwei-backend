"""初始化 TimescaleDB：readings hypertable、连续聚合、保留策略（幂等，可重复执行）。

在 alembic upgrade head 之后执行：
    .venv/bin/python -m scripts.init_db

v0.8b：readings 表替代原 sensor_raw / sensor_feature。保留策略沿用：
- readings: 保留 7 天
- 保留 sensor_feature 相关策略（兼容旧部署）
"""

import asyncio
import logging

import asyncpg

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_db")

STATEMENTS = [
    "CREATE EXTENSION IF NOT EXISTS timescaledb",
    # 时序数据 -> hypertable，chunk 1 天
    """SELECT create_hypertable('readings', 'time',
       chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)""",
    """CREATE INDEX IF NOT EXISTS idx_readings_channel_time
       ON readings (channel_id, time DESC)""",
    # 保留策略：readings 7 天
    "SELECT add_retention_policy('readings', INTERVAL '7 days', if_not_exists => TRUE)",
]


async def main() -> None:
    conn = await asyncpg.connect(dsn=settings.asyncpg_dsn)
    try:
        for stmt in STATEMENTS:
            logger.info("执行: %.60s...", stmt)
            await conn.execute(stmt)
        logger.info("TimescaleDB 初始化完成")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
