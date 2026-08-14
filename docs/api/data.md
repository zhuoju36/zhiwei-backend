# 时序数据

> v0.8.0 · 更新于 2026-08-13

边缘网关通过 `/data/ingest` 上报传感器读数，前端通过 `/data/timeseries`、`/data/latest`、`/ws/data` 消费数据。

## 权限

| 接口 | 鉴权 | 谁能调用 |
|------|------|----------|
| `POST /data/ingest` | `X-API-Key` | 边缘网关（持有 EDGE_API_KEY） |
| `GET /data/timeseries` | JWT Bearer | 已被授权对应子项的用户或 admin |
| `GET /data/latest/{point_id}` | JWT Bearer | 同上 |
| `WS /ws/data` | JWT in query (`?token=`) | 登录用户 |

---

## POST /api/v1/data/ingest

边缘网关批量上报入口。**高频热路径**，使用 asyncpg COPY 写入 `sensor_raw` hypertable。

### 请求

`Content-Type: application/json`

```json
{
  "readings": [
    {
      "device_code": "GW-001",
      "point_code": "ACC-X",
      "timestamp": "2026-08-13T12:34:56.789+00:00",
      "value": 0.0234,
      "unit": "m/s2",
      "quality": "good",
      "extra": { "raw_status": "ok" }
    },
    {
      "device_code": "GW-001",
      "point_code": "ACC-Y",
      "timestamp": "2026-08-13T12:34:56.789+00:00",
      "value": -0.015
    }
  ]
}
```

字段说明：

| 字段 | 必填 | 说明 |
|------|------|------|
| `device_code` | 是 | 设备唯一编码，对应 `devices.device_code` |
| `point_code` | 是 | 测点编码，对应 `points.point_code` |
| `timestamp` | 是 | ISO8601 UTC；边缘网关时间戳，非服务器接收时间 |
| `value` | 是 | 浮点数值 |
| `unit` | 否 | 计量单位；推荐 m/s2 / με / °C / mm |
| `quality` | 否 | `good` / `bad` / `uncertain`，默认 `good` |
| `extra` | 否 | 附加元数据，存入 `sensor_raw.metadata`（JSONB） |

约束：
- `readings`：1-10000 条/批
- 未知 `device_code` 或 `point_code` 的读数被静默丢弃并记日志

### Headers

```
X-API-Key: <EDGE_API_KEY>
Content-Type: application/json
```

### 响应 200

```json
{
  "code": "OK",
  "data": { "written": 1000 },
  "timestamp": "2026-08-13T12:34:56.789+00:00"
}
```

`written` 为实际写入数据库的条数（剔除未知编码后）。

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 401 | `AUTH_ERROR` | API Key 缺失或错误 |
| 422 | `VALIDATION_ERROR` | 字段校验失败（如 readings 超过 10000 条） |

### 性能建议

- 批次大小 1000-5000 条；过小增加 RTT 成本，过大占用连接时间过长
- 多测点合并到一个 readings 数组（按 device / 时间戳分组），单次连接完成整批写入
- 不需要轮询：实时数据通过 WebSocket 推送（见下）

### curl 示例

```bash
curl -X POST http://localhost:8000/api/v1/data/ingest \
    -H 'X-API-Key: edge-secret-key' \
    -H 'Content-Type: application/json' \
    -d '{
        "readings":[
            {"device_code":"GW-001","point_code":"ACC-X",
             "timestamp":"2026-08-13T12:00:00Z","value":0.5}
        ]
    }'
```

---

## GET /api/v1/data/timeseries

查询某测点的时序数据，自动选择数据源。

### Query

| 参数 | 必填 | 说明 |
|------|------|------|
| `point_id` | 是 | 测点 ID |
| `start` | 是 | 开始时间（ISO8601） |
| `end` | 是 | 结束时间（ISO8601） |
| `interval` | 否 | `raw` / `100ms` / `1s` / `1m` / `1h` / `1d`，默认 `1m` |

路由策略：

| 条件 | 数据源 |
|------|--------|
| `interval ∈ {raw,100ms,1s}` 且跨度 ≤ 1h | `sensor_raw` 原始表 |
| 其他 | `sensor_feature_1min` 连续聚合视图 |

### 响应 200

```json
{
  "code": "OK",
  "data": {
    "point_id": 1,
    "interval": "raw",
    "data": [
      {
        "ts": "2026-08-13T12:00:00.500+00:00",
        "value": 0.0234,
        "avg_val": null,
        "max_val": null,
        "min_val": null,
        "rms_val": null
      }
    ]
  }
}
```

字段含义：

| 字段 | 原始查询 | 聚合查询 |
|------|----------|----------|
| `ts` | 采样时间戳 | 聚合桶时间 |
| `value` | ✓ | — |
| `avg_val` / `max_val` / `min_val` / `rms_val` | — | ✓ |

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 401 | `AUTH_ERROR` | 未登录或 token 失效 |
| 403 | `FORBIDDEN` | 未被授权访问该测点所属子项 |
| 404 | `POINT_NOT_FOUND` | 测点不存在 |
| 503 | `AGGREGATE_NOT_READY` | 聚合视图未初始化（需执行 `scripts/init_db.py`） |

### curl 示例

```bash
curl -G http://localhost:8000/api/v1/data/timeseries \
    -H "Authorization: Bearer $TOKEN" \
    --data-urlencode "point_id=1" \
    --data-urlencode "start=2026-08-13T00:00:00Z" \
    --data-urlencode "end=2026-08-13T01:00:00Z" \
    --data-urlencode "interval=raw"
```

---

## GET /api/v1/data/latest/{point_id}

获取某测点最近一次写入的最新值（Redis 缓存，毫秒级返回）。

### 路径参数

- `point_id`：整数

### 响应 200

```json
{
  "code": "OK",
  "data": {
    "point_id": 1,
    "value": 0.42,
    "unit": "m/s2",
    "quality": "good",
    "timestamp": "2026-08-13T12:34:56.789+00:00"
  }
}
```

如果该测点从未上报，返回 `data: null`。

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 401 | `AUTH_ERROR` | 未登录 |
| 403 | `FORBIDDEN` | 未被授权 |
| 404 | `POINT_NOT_FOUND` | 测点不存在 |

---

## WS /ws/data

WebSocket 实时推送。客户端订阅子项频道后，接收该子项的实时读数与告警。

### 连接

```
ws://<host>/ws/data?token=<access_token>
```

### 客户端 → 服务端

订阅子项：

```json
{ "type": "cmd:subscribe", "project_id": 1 }
```

服务端回复：

```json
{ "type": "cmd:subscribed", "project_id": 1 }
```

### 服务端 → 客户端

实时数据（每次 `/data/ingest` 后推送）：

```json
{
  "type": "data:realtime",
  "payload": {
    "point_id": 1,
    "value": 0.42,
    "unit": "m/s2",
    "quality": "good",
    "timestamp": "2026-08-13T12:34:56.789+00:00"
  }
}
```

告警事件（由 Celery `alerts` 队列异步推送，前端在订阅子项频道后接收）：

```json
{
  "type": "data:alert",
  "payload": {
    "alert_id": 456,
    "point_id": 1,
    "level": "warning",
    "value": 0.62,
    "threshold": 0.5,
    "message": "gt 0.5 触发",
    "status": "triggered",
    "started_at": "2026-08-13T12:00:00Z"
  }
}
```

`status` 取值：
- `triggered`：新告警创建
- `updated`：已有未恢复告警被新读数刷新（value/threshold 更新）
- `resolved`：自动恢复或人工确认后关闭

完整字段说明见 [alerts.md § WebSocket 实时事件](alerts.md#websocket-实时事件)。

### 错误

- 连接时 token 无效 / 过期：服务关闭连接（close code `4401`）
- 子项 ID 无效：当前不主动通知客户端；建议前端校验后发送

### 客户端示例（Python）

```python
import asyncio, json, websockets


async def main():
    async with websockets.connect(f"ws://localhost:8000/ws/data?token={TOKEN}") as ws:
        await ws.send(json.dumps({"type": "cmd:subscribe", "project_id": 1}))
        async for msg in ws:
            data = json.loads(msg)
            print(data)


asyncio.run(main())
```

### 注意事项

- 当前 WebSocket 端点**未做子项权限校验**（`endpoints.py` 注释标注 `TODO`）。生产前必须补充，否则持有 JWT 的用户可订阅任意子项
- 多实例部署时实时推送通过 Redis Pub/Sub 跨实例广播（`app/ws/manager.py`），无需额外配置
- 单测点推送频率受边缘网关采集频率影响；前端展示时建议按时间窗口合并渲染
- 告警事件由 `app/tasks/alert_tasks.py` 在 `POST /data/ingest` 完成后异步推送，与实时数据共享同一 Redis 频道