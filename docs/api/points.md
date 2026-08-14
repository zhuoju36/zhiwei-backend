# 测点（物理位置）

> v0.8.0 · 更新于 2026-08-14

**v0.8b 起 `point` 只是物理位置**（如"塔 3 第 1 个测点"），不再承载通道语义。单位 / 采样率 / 告警规则全部下沉到 [通道](channels.md)。

一个 point 下可挂多个 [传感器](sensors.md)；每个传感器有 1-N 个通道；通道承载时序数据。

```
device ── 1:N ── point（物理位置）── 1:N ── sensor（仪器）── 1:N ── channel（信号通道）── 时序 readings
```

## 数据模型

```json
{
  "id": 1,
  "device_id": 1,
  "point_code": "P01",
  "point_name": "塔 3 第 1 测点",
  "point_type": "structural_joint",
  "position": { "x": 1.2, "y": 3.4, "z": 0.0 },
  "is_active": true,
  "created_at": "2026-08-13T11:00:00Z"
}
```

- `point_code` 在同 `device_id` 下唯一
- `point_type` 是**位置类型**（`structural_joint` / `beam` / `column` 等），不再是传感器类型（后者在 `channel.channel_type`）
- **没有** `unit` / `sampling_rate` / `alert_rules` —— 全部在 channel

## 权限

与设备相同（子项级访问 / 写权限；删除需全局 admin）。

---

## GET /api/v1/points

按子项或设备分页列出测点。**`subitem_id` 与 `device_id` 至少传一个**。

### Query

| 参数 | 必填 | 说明 |
|------|------|------|
| `subitem_id` | 互斥 | 按子项筛选 |
| `device_id` | 互斥 | 按设备筛选 |
| `page` / `size` | 否 | 分页 |

### 响应 200

```json
{
  "code": "OK",
  "data": { "total": 5, "page": 1, "size": 20, "items": [ ... ] }
}
```

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 400 | `BAD_REQUEST` | subitem_id 与 device_id 都未传 |
| 403 | `FORBIDDEN` | 未被授权访问所属子项 |

---

## POST /api/v1/points

创建测点（物理位置）。

### 请求

```json
{
  "device_id": 1,
  "point_code": "P01",
  "point_name": "塔 3 第 1 测点",
  "point_type": "structural_joint",
  "position": { "x": 1.2, "y": 3.4, "z": 0.0 }
}
```

### 响应 201

返回 `PointOut`。

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 403 | `FORBIDDEN` | 无设备所属子项的写权限 |
| 404 | `DEVICE_NOT_FOUND` | 设备不存在 |
| 409 | `POINT_CODE_EXISTS` | 同设备下 point_code 已存在 |

---

## GET /api/v1/points/{point_id}

### 响应 200

返回 `PointOut`。

---

## PUT /api/v1/points/{point_id}

更新测点。**所有字段可选**（PATCH 语义）。

常用场景：
- 修改三维坐标：`{"position": {"x":1.2,"y":3.4,"z":0.0}}`
- 停用测点：`{"is_active": false}`

### 响应 200

返回更新后的 `PointOut`。

---

## DELETE /api/v1/points/{point_id}

删除测点（级联删除其下 sensors → channels）。需要全局 admin。

### 响应 204

---

## curl 示例

```bash
# 创建测点
curl -X POST http://localhost:8000/api/v1/points \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{
        "device_id": 1,
        "point_code": "P01",
        "point_name": "塔 3 第 1 测点",
        "position": {"x": 1.2, "y": 3.4, "z": 0.0}
    }'

# 按设备列出
curl -G http://localhost:8000/api/v1/points \
    -H "Authorization: Bearer $TOKEN" --data-urlencode "device_id=1"

# 更新位置
curl -X PUT http://localhost:8000/api/v1/points/1 \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"position": {"x": 1.2, "y": 3.4, "z": 5.0}}'
```
