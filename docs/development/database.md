# 数据库与迁移

> SHM 平台后端 v0.3.0 · 更新于 2026-08-13
>
> 数据库架构定义在 `../架构说明书.md` 第 4 节；本文描述后端实现细节。

## 1. 设计分层

```
PostgreSQL 15 + TimescaleDB 2.x
  │
  ├─ 关系表（标准 PG 表，业务元数据）
  │    users / projects / user_projects / devices / points / alerts
  │
  └─ 时序表（TimescaleDB hypertable，传感器数据）
       sensor_raw       ── 高频原始数据，保留 7 天
       sensor_feature   ── 边缘预处理特征数据，保留 1 年
```

关系表通过 SQLAlchemy 2.0 ORM 管理；时序表的 schema 由迁移创建、hypertable 与连续聚合由 `scripts/init_db.py` 维护。

## 2. 关系模型（`app/models/`）

| 表 | 主键 | 说明 |
|----|------|------|
| `users` | id | 用户；唯一索引 username / email |
| `projects` | id | 项目；FK `users.id(created_by)` |
| `user_projects` | (user_id, project_id) | 用户-项目授权；复合主键，permission ∈ read/write/admin |
| `devices` | id | 设备；唯一索引 device_code；FK projects.id |
| `points` | id | 测点；唯一 (device_id, point_code)；JSONB position / alert_rules |
| `alerts` | id | 告警；FK points.id；level / is_resolved / 时间窗 |

### 告警生命周期

```
每批 readings 触发 _dispatch_alert_check → Celery alerts 队列 → check_threshold_batch
  │
  ▼
对每个 reading:
  for rule in alert_rules:
    if rule.matches(value):
      → upsert_alert(point_id, level, value, ...)
        · 无未恢复告警 → INSERT (started_at=reading.timestamp)
        · 已存在 → UPDATE value/threshold（保留 started_at）
    if open_but_not_triggered:
      → close_open_alerts(point_id, level, reading.timestamp)
        · UPDATE ended_at=ts, is_resolved=true
  │
  ▼
新增/关闭的 alert → Redis Pub/Sub project:{id} → WebSocket data:alert
```

每条未恢复告警按 `(point_id, level)` 唯一。持续触发不重复创建；值回到正常范围自动关闭。v0.2 未做滑动窗口去重 / 告警抑制 / 升级。

所有表 `created_at` 默认 `now()`，软删除字段未启用（开发早期阶段，AGENTS.md 0.1 节）。

模型使用 SQLAlchemy 2.0 风格 `Mapped[T]` 注解；循环引用通过 `TYPE_CHECKING` + `from __future__ import annotations` 处理（见 `app/models/user.py`、`app/models/project.py`）。

## 3. 时序模型（`app/models/timeseries.py` + `scripts/init_db.py`）

### 3.1 sensor_raw（高频原始数据）

```sql
time         TIMESTAMPTZ  NOT NULL
device_id    INTEGER      NOT NULL
point_id     INTEGER      NOT NULL
value        FLOAT        NOT NULL
quality      VARCHAR(8)   DEFAULT 'good'
metadata     JSONB
PRIMARY KEY (time, device_id, point_id)
```

- 转换：`create_hypertable('sensor_raw', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)`
- 索引：`CREATE INDEX idx_sensor_raw_device_point ON sensor_raw (device_id, point_id, time DESC)`
- 保留策略：`add_retention_policy('sensor_raw', INTERVAL '7 days', if_not_exists => TRUE)`

### 3.2 sensor_feature（特征数据）

字段：`time / device_id / point_id / avg_value / max_value / min_value / rms_value / peak_factor`，主键同上。

- 转换：`create_hypertable('sensor_feature', 'time', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE)`
- 保留策略：`add_retention_policy('sensor_feature', INTERVAL '365 days', if_not_exists => TRUE)`

### 3.3 sensor_feature_1min 连续聚合

```sql
CREATE MATERIALIZED VIEW sensor_feature_1min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', time) AS bucket,
    device_id, point_id,
    AVG(avg_value) AS avg_val,
    MAX(max_value) AS max_val,
    MIN(min_value) AS min_val,
    AVG(rms_value) AS rms_val
FROM sensor_feature
GROUP BY bucket, device_id, point_id
WITH NO DATA;
```

聚合策略未配置自动刷新时间（`add_continuous_aggregate_policy`），由 v0.2 在 `scripts/maintenance_tasks.py` 中按小时调度。

## 4. 迁移工作流

### 4.1 生成新迁移

修改 `app/models/*.py` 后：

```bash
.venv/bin/alembic revision --autogenerate -m "describe your change"
```

**审查生成的脚本**（AGENTS.md 强制要求）后再 `upgrade`，autogenerate 不能正确处理的场景：
- TimescaleDB 特异性 DDL（hypertable、连续聚合、保留策略）
- 列重命名、类型变更
- 数据迁移

### 4.2 应用 / 回退

```bash
.venv/bin/alembic upgrade head         # 全部迁移
.venv/bin/alembic downgrade -1         # 回退一步
.venv/bin/alembic history              # 查看历史
```

### 4.3 初始迁移后的顺序

```bash
.venv/bin/alembic upgrade head         # 1. 关系表 + sensor_raw/sensor_feature 普通表
.venv/bin/python -m scripts.init_db    # 2. 转换为 hypertable + 创建连续聚合 + 保留策略
.venv/bin/python -m scripts.seed       # 3. 种子数据（开发环境）
```

`scripts/init_db.py` 所有 SQL 均为幂等（`IF NOT EXISTS`、`if_not_exists => TRUE`），可重复执行。

## 5. 写入热路径（`app/services/data_service.py`）

```python
async def batch_ingest(readings: list[ReadingIn]) -> int:
    async with pool.acquire() as conn:
        code_map = await _resolve_code_map(conn, readings)  # 一次 SELECT
        records = [
            (r.timestamp, did, pid, r.value, r.quality, json.dumps(r.extra))
            for r in readings
            if (r.device_code, r.point_code) in code_map
        ]
        await conn.copy_records_to_table(
            "sensor_raw",
            records=records,
            columns=["time", "device_id", "point_id", "value", "quality", "metadata"],
        )
    await _publish_realtime(readings, code_map)  # Redis SET + PUBLISH
```

要点：
- 单次 SELECT 解析所有编码（避免 N+1）
- `copy_records_to_table` 是 asyncpg 最高性能写入路径
- 同步写 Redis 最新值 + Pub/Sub 发布，失败仅记日志，不阻塞主流程

## 6. 查询路由（智能选择数据源）

`DataService.query_timeseries`：

| 条件 | 数据源 |
|------|--------|
| `interval ∈ {raw, 100ms, 1s}` 且时间跨度 ≤ 1h | `sensor_raw` 原始表 |
| 其他 | `sensor_feature_1min` 连续聚合视图 |

若连续聚合未初始化（尚未执行 `scripts/init_db.py`），返回 HTTP 503 `code=AGGREGATE_NOT_READY`。

## 7. 数据库连接池

- SQLAlchemy engine（`app/database.py`）：`pool_size=20, max_overflow=30, pool_pre_ping=True, pool_recycle=3600`
- asyncpg pool（`app/services/data_service.py:get_pool`）：`min_size=5, max_size=20, command_timeout=60`，懒初始化
- 测试场景使用 session 级 event loop，避免连接池跨 loop 绑定错误（`pyproject.toml`）

## 8. 性能基准目标

来自架构说明书第 12 节：

| 指标 | 目标 | 实现路径 |
|------|------|----------|
| 高频写入 | 10万点/秒 | 边缘预处理 + COPY + 分区 |
| 实时查询延迟 | < 100ms | Redis 缓存最新值 |
| 历史查询（1天） | < 2s | 读 feature 表 / 连续聚合视图 |

集成测试 `tests/test_data_ingest.py:test_batch_ingest_performance` 断言 1 万条写入 < 2 秒。