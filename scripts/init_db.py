"""初始化 TimescaleDB：hypertable、连续聚合、保留策略（幂等，可重复执行）。

在 alembic upgrade head 之后执行：
    .venv/bin/python scripts/init_db.py
"""

import asyncio
import logging

import asyncpg

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_db")

STATEMENTS = [
    "CREATE EXTENSION IF NOT EXISTS timescaledb",
    # 高频原始数据 -> hypertable，chunk 1 天
    """SELECT create_hypertable('sensor_raw', 'time',
       chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)""",
    """CREATE INDEX IF NOT EXISTS idx_sensor_raw_device_point
       ON sensor_raw (device_id, point_id, time DESC)""",
    # 特征数据 -> hypertable，chunk 7 天
    """SELECT create_hypertable('sensor_feature', 'time',
       chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE)""",
    # 连续聚合：按分钟预聚合特征数据
    """CREATE MATERIALIZED VIEW IF NOT EXISTS sensor_feature_1min
       WITH (timescaledb.continuous) AS
       SELECT
           time_bucket('1 minute', time) AS bucket,
           device_id,
           point_id,
           AVG(avg_value) AS avg_val,
           MAX(max_value) AS max_val,
           MIN(min_value) AS min_val,
           AVG(rms_value) AS rms_val
       FROM sensor_feature
       GROUP BY bucket, device_id, point_id
       WITH NO DATA""",
    # 保留策略：原始数据 7 天，特征数据 1 年
    "SELECT add_retention_policy('sensor_raw', INTERVAL '7 days', if_not_exists => TRUE)",
    "SELECT add_retention_policy('sensor_feature', INTERVAL '365 days', if_not_exists => TRUE)",
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
