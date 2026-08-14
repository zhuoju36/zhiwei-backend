# 数据库与迁移

> SHM 平台后端 v0.8.0 · 更新于 2026-08-14
>
> 数据库架构定义在 `../架构说明书.md` 第 4 节；本文描述后端实现细节。

## 1. 设计分层（v0.8b）

```
PostgreSQL 15 + TimescaleDB 2.x
  │
  ├─ 关系表（标准 PG 表，业务元数据）
  │    users / subitems / user_subitems / devices / points / sensors / channels /
  │    alerts / analysis_jobs / 3d_models / platform_settings
  │
  └─ 时序表（TimescaleDB hypertable）
       readings  ── 按 channel 存储原始读数，保留 7 天
```

关系表通过 SQLAlchemy 2.0 ORM 管理；时序表 schema 由迁移创建、hypertable 与保留策略由 `scripts/init_db.py` 维护。

## 2. 拓扑：user → subitem → device → point → sensor → channel → readings

```
user
└─ subitem（子项）
   └─ device（采集设备）
      └─ point（测点 = 物理位置）
         └─ sensor（传感器 / 仪器）
            └─ channel（通道：X/Y/Z/温度/...）
               └─ readings（时序数据）
```

`point` 从 v0.7 的"一个传感器一个通道"退化为**物理位置**；`unit / sampling_rate / alert_rules` 下沉到 `channel`。

## 3. 关系模型（`app/models/`）

| 表 | 主键 | 说明 |
|----|------|------|
| `users` | id | 用户；唯一索引 username / email |
| `subitems` | id | 子项；FK `users.id(created_by)` |
| `user_subitems` | (user_id, subitem_id) | 用户-子项授权；复合主键，permission ∈ read/write/admin |
| `devices` | id | 设备；唯一索引 device_code；FK subitems.id |
| `points` | id | 测点（位置）；唯一 (device_id, point_code)；JSONB position |
| `sensors` | id | 传感器；唯一 (point_id, sensor_code)；model / manufacturer / install_date / last_calibration / metadata_ |
| `channels` | id | 通道；唯一 (sensor_id, channel_code)；channel_type / unit / sampling_rate / position_offset / axis / alert_rules / is_active |
| `alerts` | id | 告警；FK channels.id；level / is_resolved / 时间窗 |
| `analysis_jobs` | id | 分析任务；FK channels.id；plugin / params / status / result_key |
| `3d_models` | id | 3D 模型；FK subitems.id（一个子项多个模型）；original_key / glb_key / status（v0.8c） |
| `platform_settings` | id=1 | 平台元数据（单行） |

> v0.8c：`subitems.model_file_key` 列已删除（多模型方案下冗余），模型统一存 `3d_models` 表，GLB 经 `GET /api/v1/models/{id}/file` 下载。

### 告警生命周期（v0.8b）

```
每批 readings 触发 _dispatch_alert_check → Celery alerts 队列 → check_threshold_batch
  │
  ▼
对每个 reading:
  for rule in channel.alert_rules:
    if rule.matches(value):
      → trigger_alert(channel_id, level, value, ...)
        · 无未恢复告警 → INSERT (started_at=reading.timestamp)
        · 已存在 → UPDATE value/threshold（保留 started_at）
    if open_but_not_triggered:
      → close_open_alerts(channel_id, level, reading.timestamp)
        · UPDATE ended_at=ts, is_resolved=true
  │
  ▼
新增/关闭的 alert → Redis Pub/Sub subitem:{id} → WebSocket data:alert
```

每条未恢复告警按 `(channel_id, level)` 唯一。持续触发不重复创建；值回到正常范围自动关闭。v0.5 起支持 `suppress_seconds` 抑制窗口：窗口内再次触发复用最近一条已关闭告警（重开）。

所有表 `created_at` 默认 `now()`，软删除字段未启用（开发早期阶段，AGENTS.md 0.1 节）。

模型使用 SQLAlchemy 2.0 风格 `Mapped[T]` 注解；循环引用通过 `TYPE_CHECKING` + `from __future__ import annotations` 处理。

## 4. 时序模型（`app/models/reading.py` + `scripts/init_db.py`）

### 4.1 readings（唯一时序表，v0.8b 替代 sensor_raw / sensor_feature）

```sql
CREATE TABLE readings (
  time        TIMESTAMPTZ NOT NULL,
  channel_id  INT NOT NULL REFERENCES channels(id),
  value       FLOAT NOT NULL,
  quality     VARCHAR(8) DEFAULT 'good',
  metadata    JSONB,
  PRIMARY KEY (time, channel_id)
);
SELECT create_hypertable('readings', 'time',
  chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_readings_channel_time
  ON readings (channel_id, time DESC);
SELECT add_retention_policy('readings', INTERVAL '7 days', if_not_exists => TRUE);
```

- 高保真度：原始读数直接落盘（v0.7 的 sensor_feature 特征表已移除）
- 连续聚合（1min / 1h）留 v0.9+ 在 readings 上重建

## 5. 迁移工作流

### 5.1 生成新迁移

修改 `app/models/*.py` 后：

```bash
.venv/bin/alembic revision --autogenerate -m "describe your change"
```

**审查生成的脚本**（AGENTS.md 强制要求）后再 `upgrade`。注意 TimescaleDB 自动索引（如 `idx_readings_channel_time`）不会被 autogenerate 识别——用 `IF EXISTS` 处理 drop。

### 5.2 应用 / 回退

```bash
.venv/bin/alembic upgrade head         # 全部迁移
.venv/bin/alembic downgrade -1         # 回退一步
.venv/bin/alembic history              # 查看历史
```

### 5.3 干净库安装顺序

```bash
.venv/bin/alembic upgrade head         # 1. 全部表
.venv/bin/python -m scripts.init_db    # 2. readings hypertable + 保留策略
```

### 5.4 迁移历史

| 迁移 | 版本 | 说明 |
|------|------|------|
| `dda0b01608f9` | v0.1 | 初始 8 表 |
| `6c0943361e16` | v0.4 | analysis_jobs；drop Timescale 自动索引（IF EXISTS） |
| `7c74c5b67148` | v0.7 | platform_settings |
| `1e4cdedf9b41` | v0.8a | projects → subitems（术语重命名） |
| `af5a7548852c` | v0.8b | sensors / channels / readings；drop sensor_raw / sensor_feature；alerts / analysis_jobs 改 channel_id |
| `c4f21bee2f8b` | v0.8c | 3d_models 表；drop subitems.model_file_key |

## 6. 写入热路径（`app/services/data_service.py`）

```python
async def batch_ingest(readings: list[ReadingIn]) -> int:
    async with pool.acquire() as conn:
        code_map = await _resolve_code_map(conn, readings)  # 一次 JOIN: device→point→sensor→channel
        records = [
            (r.timestamp, cid, r.value, r.quality, json.dumps(r.extra))
            for r in readings
            if (r.device_code, r.channel_code) in code_map
        ]
        await conn.copy_records_to_table(
            "readings",
            records=records,
            columns=["time", "channel_id", "value", "quality", "metadata"],
        )
    await _publish_realtime(accepted)  # Redis SET + PUBLISH subitem:{id}
    await _dispatch_alert_check(accepted)  # Celery alerts 队列
```

要点：
- 编码映射 JOIN 链变长（4 表），但仍一次查询；单测点 1 万条写入 < 3s
- `channel_code` 全局唯一可定位（`devices.device_code` + `channels.channel_code`）

## 7. 查询路由

`DataService.query_timeseries(channel_id, start, end, interval)`：

| 条件 | 数据源 |
|------|--------|
| 全部（v0.8b） | `readings` 原始表 |
| v0.9+：interval ∈ {1m,1h,1d} | readings 上的连续聚合视图 |

## 8. 数据库连接池

- SQLAlchemy engine（`app/database.py`）：`pool_size=20, max_overflow=30, pool_pre_ping=True, pool_recycle=3600`
- asyncpg pool（`app/services/data_service.py:get_pool`）：`min_size=5, max_size=20, command_timeout=60`，懒初始化
- 测试场景使用 session 级 event loop，避免连接池跨 loop 绑定错误（`pyproject.toml`）

## 9. 性能基准目标

| 指标 | 目标 | 实现路径 |
|------|------|----------|
| 高频写入 | 10万点/秒 | 边缘预处理 + COPY + 分区 |
| 实时查询延迟 | < 100ms | Redis 缓存最新值 |
| 历史查询（1天） | < 2s | readings + 索引 |

集成测试 `tests/test_data_ingest.py::test_batch_ingest_performance` 断言 1 万条写入 < 3s。
