# 传感器

> v0.9.0 · 更新于 2026-08-14

挂在测点（物理位置）下的具体仪器。v0.8b 新增层。

## 数据模型

```json
{
  "id": 1,
  "point_id": 1,
  "sensor_code": "IMU1",
  "model": "XYZ-123",
  "manufacturer": "Acme",
  "install_date": "2026-08-01",
  "last_calibration": "2026-08-01",
  "metadata": { "serial": "SN-001" },
  "created_at": "2026-08-13T11:00:00Z"
}
```

- `sensor_code` 在同 `point_id` 下唯一
- 一个 point 可挂多个 sensor（IMU + 温湿度计 + 应变计）
- 单通道传感器（温度计等）：1 sensor = 1 channel，元数据仍在 sensor 层

## 权限

与设备相同（子项级访问 / 写权限；删除需全局 admin）。

---

## GET /api/v1/sensors?point_id={point_id}

列出某测点下的传感器。

### Query

| 参数 | 必填 | 说明 |
|------|------|------|
| `point_id` | 是 | 测点 ID |
| `page` / `size` | 否 | 分页 |

### 响应 200

```json
{
  "code": "OK",
  "data": { "total": 2, "page": 1, "size": 20, "items": [ ... ] }
}
```

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 403 | `FORBIDDEN` | 未被授权访问所属子项 |
| 404 | `POINT_NOT_FOUND` | 测点不存在 |

---

## POST /api/v1/sensors

创建传感器。

### 请求

```json
{
  "point_id": 1,
  "sensor_code": "IMU1",
  "model": "XYZ-123",
  "manufacturer": "Acme",
  "install_date": "2026-08-01",
  "last_calibration": "2026-08-01",
  "metadata": { "serial": "SN-001" }
}
```

### 响应 201

返回 `SensorOut`。

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 403 | `FORBIDDEN` | 无子项写权限 |
| 404 | `POINT_NOT_FOUND` | 测点不存在 |
| 409 | `SENSOR_CODE_EXISTS` | 同测点下 sensor_code 已存在 |

---

## GET /api/v1/sensors/{sensor_id}

### 响应 200

返回 `SensorOut`。

---

## PUT /api/v1/sensors/{sensor_id}

更新传感器元数据（model / manufacturer / install_date / last_calibration / metadata）。所有字段可选。

### 响应 200

返回更新后的 `SensorOut`。

---

## DELETE /api/v1/sensors/{sensor_id}

删除传感器（级联删除其下 channels → readings）。需要全局 admin。

### 响应 204

---

## curl 示例

```bash
# 创建传感器
curl -X POST http://localhost:8000/api/v1/sensors \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"point_id":1,"sensor_code":"IMU1","model":"XYZ-123"}'

# 列出
curl -G http://localhost:8000/api/v1/sensors \
    -H "Authorization: Bearer $TOKEN" --data-urlencode "point_id=1"
```
