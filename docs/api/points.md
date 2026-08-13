# 测点

> v0.3.0 · 更新于 2026-08-13

传感器在设备上的具体监测位置。测点配置 `alert_rules` 后，每次数据接入会触发阈值评估并可能产生告警（见 [alerts.md](alerts.md)）。

## 数据模型

```json
{
  "id": 1,
  "device_id": 1,
  "point_code": "ACC-X",
  "point_name": "加速度-X",
  "point_type": "acceleration",
  "unit": "m/s2",
  "position": { "x": 1.2, "y": 3.4, "z": 0.0 },
  "alert_rules": [
    { "operator": "gt", "threshold": 0.5, "level": "warning", "message": "超阈值" }
  ],
  "sampling_rate": 100,
  "is_active": true,
  "created_at": "2026-08-13T11:00:00Z"
}
```

`point_code` 在同 `device_id` 下唯一；`alert_rules` 是 JSONB 数组，每条规则由 `operator / threshold / level / message` 组成。

## `alert_rules` 字段语义

```typescript
interface AlertRule {
  operator: "gt" | "lt" | "ge" | "le" | "eq" | "ne";
  threshold: number;
  level: "info" | "warning" | "danger";
  message?: string;  // 可选，告警文本
}
```

评估时机：每次 `POST /data/ingest` 完成后，Celery `alerts` 队列异步评估每条 reading 是否匹配规则。匹配则触发告警（详见 `alerts.md`）。

支持的比较运算符：

| operator | 含义 |
|----------|------|
| `gt` | value > threshold |
| `lt` | value < threshold |
| `ge` | value ≥ threshold |
| `le` | value ≤ threshold |
| `eq` | value == threshold |
| `ne` | value != threshold |

## 权限

与设备相同（项目级访问 / 写权限；删除需全局 admin）。

---

## GET /api/v1/points

按项目或设备分页列出测点。**`project_id` 与 `device_id` 至少传一个**。

### Query

| 参数 | 必填 | 说明 |
|------|------|------|
| `project_id` | 互斥 | 按项目筛选 |
| `device_id` | 互斥 | 按设备筛选 |
| `page` / `size` | 否 | 分页 |

### 响应 200

```json
{
  "code": "OK",
  "data": {
    "total": 5,
    "page": 1,
    "size": 20,
    "items": [ ... ]
  }
}
```

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 400 | `BAD_REQUEST` | project_id 与 device_id 都未传 |
| 403 | `FORBIDDEN` | 未被授权访问所属项目 |

---

## POST /api/v1/points

创建测点。

### 请求

```json
{
  "device_id": 1,
  "point_code": "ACC-Y",
  "point_name": "加速度-Y",
  "point_type": "acceleration",
  "unit": "m/s2",
  "position": { "x": 1.2, "y": 3.4, "z": 0.0 },
  "sampling_rate": 100,
  "alert_rules": [
    { "operator": "gt", "threshold": 0.5, "level": "warning" },
    { "operator": "lt", "threshold": -0.5, "level": "warning" }
  ]
}
```

### 响应 201

返回 `PointOut`。

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 403 | `FORBIDDEN` | 无设备所属项目的写权限 |
| 404 | `DEVICE_NOT_FOUND` | 设备不存在 |
| 409 | `POINT_CODE_EXISTS` | 同设备下 point_code 已存在 |
| 422 | `VALIDATION_ERROR` | alert_rules 中 operator / level 非法 |

---

## GET /api/v1/points/{point_id}

### 响应 200

返回 `PointOut`。

---

## PUT /api/v1/points/{point_id}

更新测点。**所有字段可选**（PATCH 语义）。

常用场景：
- 修改三维坐标：`{"position": {"x":1.2,"y":3.4,"z":0.0}}`
- 修改告警规则：`{"alert_rules": [{"operator":"gt","threshold":0.7,"level":"danger"}]}`
- 停用测点：`{"is_active": false}`（停用后数据接入会忽略该 point_code）

### 响应 200

返回更新后的 `PointOut`。

---

## DELETE /api/v1/points/{point_id}

删除测点。需要全局 admin。

### 响应 204

---

## curl 示例

```bash
# 创建测点（带告警规则）
curl -X POST http://localhost:8000/api/v1/points \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{
        "device_id": 1,
        "point_code": "ACC-Y",
        "unit": "m/s2",
        "sampling_rate": 100,
        "alert_rules": [{"operator":"gt","threshold":0.5,"level":"warning"}]
    }'

# 按设备列出
curl -G http://localhost:8000/api/v1/points \
    -H "Authorization: Bearer $TOKEN" --data-urlencode "device_id=1"

# 更新告警规则
curl -X PUT http://localhost:8000/api/v1/points/1 \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"alert_rules":[{"operator":"gt","threshold":0.7,"level":"danger"}]}'
```