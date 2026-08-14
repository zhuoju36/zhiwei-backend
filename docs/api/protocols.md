# 协议

> v0.9.1 · 更新于 2026-08-13

`GET /api/v1/protocols` 返回云端注册的协议适配器元数据，供前端管理页动态生成协议配置表单。后端启动时由 `AdapterRegistry.discover()` 扫描 `app/plugins/protocols/*.py` 自动发现，新协议 = 新增一个模块文件即可。

## GET /api/v1/protocols

### 响应 200

```json
{
  "code": "OK",
  "data": [
    {
      "name": "http_json",
      "version": "1.0.0",
      "supports_batch": true,
      "config_schema": {
        "host": "http://...",
        "port": 9000,
        "path": "/readings",
        "device_code": "GW-001",
        "sample_interval_ms": 1000
      }
    },
    {
      "name": "modbus_tcp",
      "version": "1.0.0",
      "supports_batch": true,
      "config_schema": { "...": "..." }
    },
    {
      "name": "mqtt",
      "version": "1.0.0",
      "supports_batch": true,
      "config_schema": { "...": "..." }
    }
  ]
}
```

### 错误

| HTTP | code | 说明 |
|------|------|------|
| 401 | `AUTH_ERROR` | 未登录 |

`config_schema` 是**示例结构**（描述期望的字段和类型），不是严格 JSON Schema。前端可基于此动态生成表单，后端会做非严格校验。

---

## 各协议 config schema

`devices.config` 是 JSONB，存每个设备的具体协议配置。`POST /api/v1/devices` 时 `protocol` 字段必须是已注册协议名，否则返回 `422 PROTOCOTOL_NOT_REGISTERED`。

### http_json（已存在示例）

```json
{
  "host": "http://10.0.0.10",
  "port": 9000,
  "path": "/readings",
  "device_code": "GW-001",
  "sample_interval_ms": 1000
}
```

期望对端返回 JSON 数组：
```json
[
  {"device_code": "GW-001", "channel_code": "ACC-X", "value": 0.42, "unit": "m/s2", "quality": "good"}
]
```

### modbus_tcp（v0.3 新增）

从 Modbus 保持寄存器读取，data_type 支持 `uint16` / `int16` / `uint32` / `int32` / `float32` / `float64`（按大端字节序）。

```json
{
  "host": "10.0.0.10",
  "port": 502,
  "slave_id": 1,
  "timeout_ms": 3000,
  "device_code": "GW-MOD-001",
  "sample_interval_ms": 1000,
  "registers": [
    {"address": 0, "count": 2, "data_type": "float32",
     "channel_code": "ACC-X", "scale": 0.001, "unit": "m/s2"},
    {"address": 2, "count": 1, "data_type": "uint16",
     "channel_code": "TEMP", "scale": 0.1, "unit": "°C"}
  ]
}
```

| 字段 | 说明 |
|------|------|
| `host` / `port` | Modbus TCP 服务地址 |
| `slave_id` | Modbus 从站地址（默认 1） |
| `registers` | 每个元素定义一个通道的寄存器映射 |
| `registers[].address` | 起始寄存器地址 |
| `registers[].count` | 寄存器数量（按 data_type 默认推断） |
| `registers[].data_type` | 解码类型，默认 `uint16` |
| `registers[].scale` | 解码后乘以的缩放因子，默认 1.0 |
| `registers[].unit` | 单位（透传到 RawReading.unit） |
| `registers[].channel_code` | 通道编码（对应 `channels.channel_code`，v0.8b 起） |

错误恢复：单寄存器读取失败时，该点返回 `quality="bad"`，不影响其他点继续返回。

### mqtt（v0.3 新增）

通过 MQTT broker 订阅 JSON 消息。

```json
{
  "host": "broker.local",
  "port": 1883,
  "username": "edge",
  "password": "secret",
  "topic": "shm/+/+/value",
  "queue_max": 1000,
  "device_code": "GW-MQTT-01",
  "use_tls": false
}
```

期望 broker 上转发的 JSON payload：

```json
{
  "device_code": "GW-MQTT-01",
  "channel_code": "ACC-X",
  "value": 0.42,
  "unit": "m/s2",
  "quality": "good",
  "timestamp": "2026-08-13T12:00:00Z"
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `host` / `port` | 是 | broker 地址 |
| `username` / `password` | 否 | 认证 |
| `topic` | 是 | 订阅 topic，支持通配符（`+` / `#`） |
| `queue_max` | 否 | 内部缓冲队列上限（默认 1000），满则丢弃 |
| `use_tls` | 否 | 是否 TLS（证书管理留 v0.5+） |
| `device_code` | 否 | 若 broker 消息不携带 device_code，用此兜底 |

字段缺失 / JSON 错误 / 队列满：记日志并丢弃，不中断订阅。

### modbus_rtu_over_tcp（v0.9 新增，监听型 / DTU 透传）

**拓扑**：现场仪表(RS485/Modbus RTU) → DTU(4G 透传) → 云端 `dtu_server` 监听端口。DTU 是透明管道，把现场设备返回的 Modbus RTU 响应帧字节流原样推送；`app/dtu_server` 独立进程接收、解析（CRC16 校验）并直写时序库，与 API 进程解耦（`docker compose up dtu-server` 启动）。

```json
{
  "host": "0.0.0.0",
  "port": 5021,
  "slave_id": 1,
  "device_code": "GW-DTU-001",
  "registers": [
    {"address": 0, "count": 2, "data_type": "float32",
     "channel_code": "ACC-X", "scale": 0.001, "unit": "m/s2"}
  ]
}
```

| 字段 | 说明 |
|------|------|
| `host` / `port` | 监听地址与端口（**一端口一设备**；`port` 必填） |
| `slave_id` | 现场从站地址（默认 1） |
| `registers` | 通道映射，语义同 `modbus_tcp`；**约定响应帧寄存器从 address 0 起连续排布** |
| `device_code` | 缺省取设备 `device_code` |

约定：粘包/半包与坏帧（CRC 错）由服务端自动处理；异常响应仅记日志不产出读数。

---

## 适配器自动发现

新增协议步骤：

1. 在 `app/plugins/protocols/` 下新建 `<protocol>_adapter.py`
2. 继承 `ProtocolAdapter`（`app/plugins/protocols/base.py`，**禁止修改契约**）
3. 设置类属性 `name = "<protocol>"`（与 `devices.protocol` 字段值一致）
4. 实现 `connect / read_batch / disconnect`；监听型适配器额外设 `supports_listen = True` 并实现 `decode_stream`（无需 `connect` 语义，见 `modbus_rtu_over_tcp` 示例）
5. 进程启动时 `AdapterRegistry.discover()` 自动注册

详见 [AGENTS.md §4.2](../../AGENTS.md)。

---

## curl 示例

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
    -d 'username=admin&password=admin123456' | jq -r '.data.access_token')

# 列出协议
curl http://localhost:8000/api/v1/protocols -H "Authorization: Bearer $TOKEN"

# 创建 modbus 设备
curl -X POST http://localhost:8000/api/v1/devices \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{
        "project_id": 1,
        "device_code": "GW-MOD-001",
        "protocol": "modbus_tcp",
        "config": {
            "host": "10.0.0.10", "port": 502, "slave_id": 1,
            "device_code": "GW-MOD-001",
            "registers": [
                {"address": 0, "count": 2, "data_type": "float32",
                 "channel_code": "ACC-X", "scale": 0.001, "unit": "m/s2"}
            ]
        }
    }'

# 创建 mqtt 设备
curl -X POST http://localhost:8000/api/v1/devices \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{
        "project_id": 1,
        "device_code": "GW-MQTT-01",
        "protocol": "mqtt",
        "config": {
            "host": "broker.local", "port": 1883,
            "topic": "shm/+/+/value",
            "device_code": "GW-MQTT-01"
        }
    }'
```