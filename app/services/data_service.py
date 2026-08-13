"""时序数据读写核心：批量 COPY 写入、按间隔智能路由查询。

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
    global _pool
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
    """批量将 (device_code, point_code) 映射为 (device_id, point_id, project_id)。"""
    device_codes = list({r.device_code for r in readings})
    rows = await conn.fetch(
        """
        SELECT d.id AS device_id, d.device_code, d.project_id, p.id AS point_id, p.point_code
        FROM devices d
        JOIN points p ON p.device_id = d.id
        WHERE d.device_code = ANY($1)
        """,
        device_codes,
    )
    return {
        (row["device_code"], row["point_code"]): (
            row["device_id"],
            row["point_id"],
            row["project_id"],
        )
        for row in rows
    }


async def batch_ingest(readings: list[ReadingIn]) -> int:
    """批量写入 sensor_raw，返回实际写入条数。未知编码的读数被丢弃并记日志。

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
        accepted: list[
            tuple[ReadingIn, int, int, int]
        ] = []  # (reading, device_id, point_id, project_id)
        skipped = 0
        for r in readings:
            ids = code_map.get((r.device_code, r.point_code))
            if ids is None:
                skipped += 1
                continue
            device_id, point_id, project_id = ids
            records.append(
                (r.timestamp, device_id, point_id, r.value, r.quality.value, json.dumps(r.extra))
            )
            accepted.append((r, device_id, point_id, project_id))

        if skipped:
            logger.warning("批量接入丢弃 %d 条未知编码读数", skipped)
        if not records:
            return 0

        await conn.copy_records_to_table(
            "sensor_raw",
            records=records,
            columns=["time", "device_id", "point_id", "value", "quality", "metadata"],
        )

    await _publish_realtime(readings, code_map)
    await _dispatch_alert_check(accepted)
    return len(records)


async def _dispatch_alert_check(accepted: list[tuple[ReadingIn, int, int, int]]) -> None:
    """将已写入的读数投递到 Celery alerts 队列做阈值检查。"""
    if not accepted:
        return
    payload = [
        {
            "device_id": device_id,
            "point_id": point_id,
            "project_id": project_id,
            "value": r.value,
            "timestamp": r.timestamp.isoformat(),
            "quality": r.quality.value,
        }
        for r, device_id, point_id, project_id in accepted
    ]
    try:
        # 延迟导入避免循环依赖（alert_tasks 间接依赖 data_service.get_redis）
        from app.tasks.alert_tasks import check_threshold_batch

        check_threshold_batch.delay(payload)
    except Exception:
        logger.exception("投递告警检查任务失败")


async def _publish_realtime(
    readings: list[ReadingIn], code_map: dict[tuple[str, str], tuple[int, int, int]]
) -> None:
    """写入 Redis 最新值缓存，并按项目频道发布实时推送（供 WebSocket 广播）。"""
    try:
        rds = await get_redis()
        async with rds.pipeline(transaction=False) as pipe:
            for r in readings:
                ids = code_map.get((r.device_code, r.point_code))
                if ids is None:
                    continue
                _, point_id, project_id = ids
                payload = {
                    "type": "data:realtime",
                    "payload": {
                        "point_id": point_id,
                        "value": r.value,
                        "unit": r.unit,
                        "quality": r.quality.value,
                        "timestamp": r.timestamp.isoformat(),
                    },
                }
                pipe.set(f"latest:{point_id}", json.dumps(payload["payload"]))
                pipe.publish(f"project:{project_id}", json.dumps(payload))
            await pipe.execute()
    except Exception:
        # 推送失败不影响写入主流程
        logger.exception("实时推送失败")


async def get_latest(point_id: int) -> dict | None:
    rds = await get_redis()
    raw = await rds.get(f"latest:{point_id}")
    return json.loads(raw) if raw else None


async def query_timeseries(
    point_id: int, start: datetime, end: datetime, interval: str
) -> list[TimeSeriesPoint]:
    """根据时间范围与聚合间隔智能选择数据源：

    - interval 为 raw/1s/100ms 且跨度 <= 1 小时 -> sensor_raw 原始表
    - 其余 -> sensor_feature_1min 连续聚合
    """
    span_hours = (end - start).total_seconds() / 3600
    pool = await get_pool()

    if interval in ("raw", "100ms", "1s") and span_hours <= 1:
        sql = """
            SELECT time AS ts, value
            FROM sensor_raw
            WHERE point_id = $1 AND time BETWEEN $2 AND $3
            ORDER BY time ASC
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, point_id, start, end)
        return [TimeSeriesPoint(ts=row["ts"], value=row["value"]) for row in rows]

    sql = """
        SELECT bucket AS ts, avg_val, max_val, min_val, rms_val
        FROM sensor_feature_1min
        WHERE point_id = $1 AND bucket BETWEEN $2 AND $3
        ORDER BY bucket ASC
    """
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, point_id, start, end)
    except asyncpg.UndefinedTableError as exc:
        raise BizException(
            code="AGGREGATE_NOT_READY",
            message="连续聚合视图未初始化，请先执行 scripts/init_db.py",
            status_code=503,
        ) from exc
    return [
        TimeSeriesPoint(
            ts=row["ts"],
            avg_val=row["avg_val"],
            max_val=row["max_val"],
            min_val=row["min_val"],
            rms_val=row["rms_val"],
        )
        for row in rows
    ]


async def check_point_project(point_id: int) -> int:
    """返回测点所属项目 ID，用于路由层权限校验。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        project_id = await conn.fetchval(
            """
            SELECT d.project_id
            FROM points p JOIN devices d ON d.id = p.device_id
            WHERE p.id = $1
            """,
            point_id,
        )
    if project_id is None:
        raise BizException(code="POINT_NOT_FOUND", message="测点不存在", status_code=404)
    return project_id
