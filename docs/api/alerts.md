# 告警

> v0.6.0 · 更新于 2026-08-13

阈值告警的生命周期由 [Celery `alerts` 队列](architecture.md) 异步驱动：每次 `POST /data/ingest` 完成后，对涉及的测点批量评估 `alert_rules`，触发或关闭 `(point_id, level)` 唯一未恢复告警。

## 数据模型

```json
{
  "id": 1,
  "point_id": 1,
  "alert_type": "threshold",
  "level": "warning",
  "message": "超阈值",
  "value": 0.62,
  "threshold": 0.5,
  "started_at": "2026-08-13T12:00:00Z",
  "ended_at": null,
  "is_resolved": false,
  "resolved_by": null
}
```

| 字段 | 说明 |
|------|------|
| `alert_type` | 当前固定 `"threshold"`；v0.3+ 加 `trend / fft` 等 |
| `level` | `info` / `warning` / `danger` |
| `started_at` | 首次触发时间（同一 level 持续触发不重置） |
| `ended_at` | 自动恢复（值回到正常范围）或人工确认时设置 |
| `is_resolved` | 是否已结束；活跃告警为 `false` |
| `resolved_by` | 人工确认的用户 ID；自动恢复时为 `null` |

## 权限

| 操作 | admin | 项目 admin | 项目 write / read | 其他 |
|------|-------|-----------|-------------------|------|
| `GET /alerts`（列表/详情） | ✓ | ✓ | ✓（限可见项目） | ✗ |
| `POST /alerts/{id}/acknowledge` | ✓ | ✓ | ✗ | ✗ |

---

## GET /api/v1/alerts

分页列出告警。**至少传一个过滤条件**（`project_id` 或 `point_id`），避免全表扫描；admin 不带过滤也会查询全量（用于大屏）。

### Query

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `project_id` | int | — | 按项目 |
| `point_id` | int | — | 按测点 |
| `level` | enum | — | `info` / `warning` / `danger` |
| `is_resolved` | bool | — | 活跃 / 已恢复 |
| `start` | datetime | — | 告警 `started_at` 下界 |
| `end` | datetime | — | 告警 `started_at` 上界 |
| `page` / `size` | int | 1 / 20 | 分页 |

### 响应 200

```json
{
  "code": "OK",
  "data": {
    "total": 12,
    "page": 1,
    "size": 20,
    "items": [
      {
        "id": 1,
        "point_id": 1,
        "alert_type": "threshold",
        "level": "warning",
        "message": "gt 0.5 触发",
        "value": 0.62,
        "threshold": 0.5,
        "started_at": "2026-08-13T12:00:00Z",
        "ended_at": null,
        "is_resolved": false,
        "resolved_by": null
      }
    ]
  }
}
```

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 403 | `FORBIDDEN` | 未被授权访问所属项目 |
| 404 | `POINT_NOT_FOUND` | `point_id` 不存在 |

---

## GET /api/v1/alerts/{alert_id}

获取告警详情。

### 响应 200

返回单个 alert 对象（结构同列表项）。

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 403 | `FORBIDDEN` | 未被授权 |
| 404 | `ALERT_NOT_FOUND` | 告警不存在 |

---

## POST /api/v1/alerts/{alert_id}/acknowledge

人工确认告警（设置 `is_resolved=true`、`ended_at=now()`、`resolved_by=current_user.id`）。

幂等保护：已被确认或自动恢复的告警返回 `409 ALERT_ALREADY_RESOLVED`。

### 响应 200

返回更新后的 alert 对象。

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 403 | `FORBIDDEN` | 非项目管理员 |
| 404 | `ALERT_NOT_FOUND` | 告警不存在 |
| 409 | `ALERT_ALREADY_RESOLVED` | 告警已确认 |

---

## WebSocket 实时事件

告警创建 / 关闭时会向 `project:{project_id}` 频道广播：

```json
{
  "type": "data:alert",
  "payload": {
    "alert_id": 1,
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
- `resolved`：自动恢复（值回到正常范围）或人工确认后关闭

订阅方式见 [data.md § WebSocket](data.md#ws-wsdata)。

---

## curl 示例

```bash
# 按项目列出活跃告警
curl -G http://localhost:8000/api/v1/alerts \
    -H "Authorization: Bearer $TOKEN" \
    --data-urlencode "project_id=1" \
    --data-urlencode "is_resolved=false"

# 确认告警
curl -X POST http://localhost:8000/api/v1/alerts/1/acknowledge \
    -H "Authorization: Bearer $TOKEN"
```