# 通道

> v0.9.3 · 更新于 2026-08-14

传感器的信号通道（3 轴 IMU 的 X / Y / Z 分别是三个 channel）。**时序数据 / 告警 / 分析都按 channel 粒度**。v0.8b 新增层。

## 数据模型

```json
{
  "id": 1,
  "sensor_id": 1,
  "channel_code": "X",
  "channel_type": "acceleration",
  "unit": "m/s2",
  "sampling_rate": 100,
  "position_offset": { "dx": 0.05, "dy": 0, "dz": 0 },
  "axis": "x",
  "note": null,
  "alert_rules": [
    { "operator": "gt", "threshold": 0.5, "level": "warning", "suppress_seconds": 60 }
  ],
  "is_active": true,
  "created_at": "2026-08-13T11:00:00Z"
}
```

- `channel_code` 在同 `sensor_id` 下唯一
- `channel_type`：`acceleration` / `strain` / `temperature` 等
- `axis`：`x` / `y` / `z`，给 3D 大屏着色用
- `alert_rules`：阈值告警规则（v0.8b 起从 point 下沉到这里）

## `alert_rules` 字段语义

```typescript
interface AlertRule {
  operator: "gt" | "lt" | "ge" | "le" | "eq" | "ne";
  threshold: number;
  level: "info" | "warning" | "danger";
  message?: string;
  suppress_seconds?: number;  // 抑制窗口（秒），默认 60
}
```

评估时机：每次 `POST /data/ingest` 完成后，Celery `alerts` 队列异步评估每条 reading 是否匹配规则。匹配则触发告警（详见 [alerts.md](alerts.md)）。

## 权限

与设备相同（项目级访问 / 写权限；删除需全局 admin）。

---

## GET /api/v1/channels?sensor_id={sensor_id}

列出某传感器下的通道。

### Query

| 参数 | 必填 | 说明 |
|------|------|------|
| `sensor_id` | 是 | 传感器 ID |
| `page` / `size` | 否 | 分页 |

### 响应 200

```json
{
  "code": "OK",
  "data": { "total": 3, "page": 1, "size": 20, "items": [ ... ] }
}
```

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 403 | `FORBIDDEN` | 未被授权访问所属项目 |
| 404 | `SENSOR_NOT_FOUND` | 传感器不存在 |

---

## POST /api/v1/channels

创建通道。

### 请求

```json
{
  "sensor_id": 1,
  "channel_code": "X",
  "channel_type": "acceleration",
  "unit": "m/s2",
  "sampling_rate": 100,
  "axis": "x",
  "alert_rules": [
    { "operator": "gt", "threshold": 0.5, "level": "warning", "suppress_seconds": 60 }
  ]
}
```

### 响应 201

返回 `ChannelOut`。

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 403 | `FORBIDDEN` | 无项目写权限 |
| 404 | `SENSOR_NOT_FOUND` | 传感器不存在 |
| 409 | `CHANNEL_CODE_EXISTS` | 同传感器下 channel_code 已存在 |
| 422 | `VALIDATION_ERROR` | alert_rules 中 operator / level 非法 |

---

## GET /api/v1/channels/{channel_id}

### 响应 200

返回 `ChannelOut`。

---

## PUT /api/v1/channels/{channel_id}

更新通道（channel_type / unit / sampling_rate / position_offset / axis / alert_rules / is_active）。所有字段可选。

### 响应 200

返回更新后的 `ChannelOut`。

---

## DELETE /api/v1/channels/{channel_id}

删除通道（级联删除其 readings 时序数据）。需要全局 admin。

### 响应 204

---

## 与数据 / 告警 / 分析的关系

| 功能 | 入参 |
|------|------|
| `POST /data/ingest` 上报 | `device_code + channel_code` |
| `GET /data/timeseries` | `channel_id` |
| `GET /data/latest/{channel_id}` | `channel_id` |
| `GET /alerts?channel_id=` | `channel_id` |
| `POST /analysis/jobs` | `channel_id` |

---

## curl 示例

```bash
# 创建通道（带告警规则）
curl -X POST http://localhost:8000/api/v1/channels \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{
        "sensor_id": 1,
        "channel_code": "X",
        "channel_type": "acceleration",
        "unit": "m/s2",
        "sampling_rate": 100,
        "alert_rules": [{"operator":"gt","threshold":0.5,"level":"warning"}]
    }'

# 列出
curl -G http://localhost:8000/api/v1/channels \
    -H "Authorization: Bearer $TOKEN" --data-urlencode "sensor_id=1"
```
