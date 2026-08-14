# 传感器（测点）

> v0.9 · 更新于 2026-08-14

v0.9 起**测点（point）与传感器（sensor）合一**：实际部署中一个测点对应一个传感器，合并为一个实体 `sensor`，挂载在设备（device）下。传感器同时携带**位置字段**（position 三维坐标、sensor_name、sensor_type）与**仪器元数据**（model、manufacturer、校准日期）。

## 数据模型

```json
{
  "id": 1,
  "device_id": 1,
  "sensor_code": "IMU1",
  "sensor_name": "塔 3 第 1 测点",
  "sensor_type": "structural_joint",
  "model": "XYZ-123",
  "manufacturer": "Acme",
  "install_date": "2026-01-15",
  "last_calibration": "2026-06-01",
  "position": { "x": 0.0, "y": 0.0, "z": 15.0 },
  "is_active": true,
  "metadata": null,
  "created_at": "2026-08-14T10:00:00Z"
}
```

`position` 为 3D 大屏测点标记坐标；`unit / sampling_rate / alert_rules` 在通道（channel）层。

## 权限

| 操作 | admin | 项目 write | 项目 read | 其他 |
|------|-------|-----------|-----------|------|
| `GET /sensors`（列表） | ✓ | ✓ | ✓ | ✗ |
| `POST /sensors`（创建） | ✓ | ✓ | ✗ | ✗ |
| `GET /sensors/{id}` | ✓ | ✓ | ✓ | ✗ |
| `PUT /sensors/{id}` | ✓ | ✓ | ✗ | ✗ |
| `DELETE /sensors/{id}` | ✓ | ✗ | ✗ | ✗ |

---

## GET /api/v1/sensors?device_id={id}

按设备分页列出传感器。**`device_id` 必填**（缺失返回 400 `BAD_REQUEST`）。

**成功 200**：`PageSchema`（total / page / size / items）。

---

## POST /api/v1/sensors

创建传感器。**权限**：项目 write。

```json
{
  "device_id": 1,
  "sensor_code": "IMU1",
  "sensor_name": "塔 3 第 1 测点",
  "position": { "x": 0.0, "y": 0.0, "z": 15.0 },
  "model": "XYZ-123"
}
```

**成功 201**：`SensorOut`。

**错误**：

| HTTP | code | 场景 |
|------|------|------|
| 404 | `DEVICE_NOT_FOUND` | 设备不存在 |
| 409 | `SENSOR_CODE_EXISTS` | 同 device 内 `sensor_code` 重复 |

---

## GET /api/v1/sensors/{id}

详情。**权限**：项目 read。

---

## PUT /api/v1/sensors/{id}

更新（可更新位置、名称、类型、仪器元数据、`is_active`）。**权限**：项目 write。

---

## DELETE /api/v1/sensors/{id}

删除（级联删除其通道与读数）。**权限**：admin。**成功 204**；不存在 404。
