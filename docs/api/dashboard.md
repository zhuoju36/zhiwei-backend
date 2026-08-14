# 大屏

> v0.9.3 · 更新于 2026-08-13

为前端数字孪生大屏提供的轻量聚合统计接口。复杂图表由前端基于 [data.md](data.md) 的时序查询自行组装。

---

## GET /api/v1/dashboard/stats

聚合统计：活跃告警数、近 24h 告警数、按级别分布。

### Query

| 参数 | 必填 | 说明 |
|------|------|------|
| `project_id` | 否 | 不传 → 全局统计（仅 admin 可见）；传 → 限该项目 |

### 响应 200

```json
{
  "code": "OK",
  "data": {
    "active_alerts": 5,
    "alerts_24h": 23,
    "by_level": {
      "info": 1,
      "warning": 3,
      "danger": 1
    },
    "project_id": 1
  }
}
```

| 字段 | 说明 |
|------|------|
| `active_alerts` | `is_resolved=false` 的告警数 |
| `alerts_24h` | `started_at >= now() - 24h` 的告警数（含已恢复） |
| `by_level` | 当前活跃告警按 level 分组计数（仅包含数据库中实际出现的 level） |
| `project_id` | 回显查询参数 |

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 403 | `FORBIDDEN` | 非项目成员 |

---

## GET /api/v1/dashboard/recent-alerts

按时间倒序获取最近 N 条告警（不论已恢复/未恢复）。

### Query

| 参数 | 默认 | 说明 |
|------|------|------|
| `project_id` | — | 可选 |
| `limit` | 10 | 1-200 |

### 响应 200

```json
{
  "code": "OK",
  "data": [
    { "id": 23, "point_id": 1, "level": "danger", "started_at": "...", "is_resolved": false, ... }
  ]
}
```

数组元素结构与 `/alerts` 列表项一致（见 [alerts.md](alerts.md)）。

---

## curl 示例

```bash
curl -G http://localhost:8000/api/v1/dashboard/stats \
    -H "Authorization: Bearer $TOKEN" --data-urlencode "project_id=1"

curl -G http://localhost:8000/api/v1/dashboard/recent-alerts \
    -H "Authorization: Bearer $TOKEN" \
    --data-urlencode "project_id=1" --data-urlencode "limit=20"
```