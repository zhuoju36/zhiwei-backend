"""时序数据读写核心：批量 COPY 写入 readings、按间隔智能路由查询。

连接池采用懒初始化，避免依赖应用 lifespan（测试与 Celery 场景同样可用）。
"""

import asyncio
import json
import logging
from datetime import datetime

import asyncpg
import redis.asyncio as aioredis

from app.config import settings
from app.core.exceptions import BizException
from app.schemas.data import ReadingIn, TimeSeriesPoint

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_redis: aioredis.Redis | None = None
_lock = asyncio.Lock()


async def get_pool() -> asyncpg.Pool:
    global _pool, _lock
    if _lock is None:
        _lock = asyncio.Lock()
    if _pool is None:
        async with _lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(
                    dsn=settings.asyncpg_dsn,
                    min_size=5,
                    max_size=20,
                    command_timeout=60,
                )
    return _pool


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close() -> None:
    global _pool, _redis
    if _pool is not None:
        await _pool.close()
        _pool = None
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def _resolve_code_map(
    conn: asyncpg.Connection, readings: list[ReadingIn]
) -> dict[tuple[str, str], tuple[int, int, int]]:
    """批量将 (device_code, channel_code) 映射为 (channel_id, project_id)。

    返回：{(device_code, channel_code): (channel_id, project_id)}
    """
    device_codes = list({r.device_code for r in readings})
    rows = await conn.fetch(
        """
        SELECT d.id AS device_id, d.device_code, d.project_id,
               c.id AS channel_id, c.channel_code
        FROM devices d
        JOIN sensors s ON s.device_id = d.id
        JOIN channels c ON c.sensor_id = s.id
        WHERE d.device_code = ANY($1)
        """,
        device_codes,
    )
    return {
        (row["device_code"], row["channel_code"]): (
            row["channel_id"],
            row["project_id"],
        )
        for row in rows
    }


async def batch_ingest(readings: list[ReadingIn]) -> int:
    """批量写入 readings，返回实际写入条数。未知编码的读数被丢弃并记日志。

    写完后：
    1. Redis 最新值缓存与实时推送（_publish_realtime）
    2. 投递到 Celery alerts 队列做阈值检查（_dispatch_alert_check）
    """
    if not readings:
        return 0

    pool = await get_pool()
    async with pool.acquire() as conn:
        code_map = await _resolve_code_map(conn, readings)

        records = []
        accepted: list[tuple[ReadingIn, int, int]] = []  # (reading, channel_id, project_id)
        skipped = 0
        for r in readings:
            ids = code_map.get((r.device_code, r.channel_code))
            if ids is None:
                skipped += 1
                continue
            channel_id, project_id = ids
            records.append((r.timestamp, channel_id, r.value, r.quality.value, json.dumps(r.extra)))
            accepted.append((r, channel_id, project_id))

        if skipped:
            logger.warning("批量接入丢弃 %d 条未知编码读数", skipped)
        if not records:
            return 0

        await conn.copy_records_to_table(
            "readings",
            records=records,
            columns=["time", "channel_id", "value", "quality", "metadata"],
        )

    await _publish_realtime(accepted)
    await _dispatch_alert_check(accepted)
    return len(records)


async def _publish_realtime(accepted: list[tuple[ReadingIn, int, int]]) -> None:
    """写入 Redis 最新值缓存，并按子项频道发布实时推送（供 WebSocket 广播）。"""
    try:
        rds = await get_redis()
        async with rds.pipeline(transaction=False) as pipe:
            for r, channel_id, project_id in accepted:
                payload = {
                    "type": "data:realtime",
                    "payload": {
                        "channel_id": channel_id,
                        "device_code": r.device_code,
                        "channel_code": r.channel_code,
                        "value": r.value,
                        "unit": r.unit,
                        "quality": r.quality.value,
                        "timestamp": r.timestamp.isoformat(),
                    },
                }
                pipe.set(f"latest:{channel_id}", json.dumps(payload["payload"]))
                pipe.publish(f"project:{project_id}", json.dumps(payload))
            await pipe.execute()
    except Exception:
        # 推送失败不影响写入主流程
        logger.exception("实时推送失败")


async def _dispatch_alert_check(accepted: list[tuple[ReadingIn, int, int]]) -> None:
    """将已写入的读数投递到 Celery alerts 队列做阈值检查。"""
    if not accepted:
        return
    payload = [
        {
            "channel_id": channel_id,
            "project_id": project_id,
            "device_code": r.device_code,
            "channel_code": r.channel_code,
            "value": r.value,
            "timestamp": r.timestamp.isoformat(),
            "quality": r.quality.value,
        }
        for r, channel_id, project_id in accepted
    ]
    try:
        # 延迟导入避免循环依赖（alert_tasks 间接依赖 data_service.get_redis）
        from app.tasks.alert_tasks import check_threshold_batch

        check_threshold_batch.delay(payload)
    except Exception:
        logger.exception("投递告警检查任务失败")


async def get_latest(channel_id: int) -> dict | None:
    rds = await get_redis()
    raw = await rds.get(f"latest:{channel_id}")
    return json.loads(raw) if raw else None


async def query_timeseries(
    channel_id: int, start: datetime, end: datetime, interval: str
) -> list[TimeSeriesPoint]:
    """根据时间范围与聚合间隔智能选择数据源：

    - interval 为 raw/1s/100ms 且跨度 <= 1 小时 -> readings 原始表
    - 其余 -> 连续聚合视图（当前未启用连续聚合，返回 raw）
    """
    pool = await get_pool()

    # 当前 v0.8b 无连续聚合（sensor_feature_1min 已删除），全部按 raw 返回
    sql = """
        SELECT time AS ts, value
        FROM readings
        WHERE channel_id = $1 AND time BETWEEN $2 AND $3
        ORDER BY time ASC
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, channel_id, start, end)
    return [TimeSeriesPoint(ts=row["ts"], value=row["value"]) for row in rows]


async def check_channel_project(channel_id: int) -> int:
    """返回通道所属子项 ID，用于路由层权限校验。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        project_id = await conn.fetchval(
            """
            SELECT d.project_id
            FROM channels c
            JOIN sensors s ON s.id = c.sensor_id
            JOIN devices d ON d.id = s.device_id
            WHERE c.id = $1
            """,
            channel_id,
        )
    if project_id is None:
        raise BizException(code="CHANNEL_NOT_FOUND", message="通道不存在", status_code=404)
    return project_id
