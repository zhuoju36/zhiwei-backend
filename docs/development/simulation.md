# 模拟与冒烟（无硬件）

> v0.8.0 · 更新于 2026-08-13

现场没有真实硬件时，可用三套脚本完成**采集 → 入库 → 告警 → 推送**全链路的演示与压测。

## 工具清单

| 脚本 | 用途 | 是否需要 broker / 真实设备 |
|------|------|---------------------------|
| `scripts/simulate_data.py` | 通用 HTTP 模拟器，从后端拉设备配置后直推 `/data/ingest` | 不需要，最快上手 |
| `scripts/mqtt_injector.py` | MQTT 网关行为注入器，绕开 broker 直接推 ingest | 不需要 broker |
| `scripts/modbus_simulator.py` | 内存 Modbus TCP 服务，配合 `modbus_tcp_adapter` 测试 | 不需要真实设备 |
| `scripts/run_edge_adapter.py` | 边缘网关参考运行脚本，从后端拉配置后采协议并 ingest | 需配合 modbus_simulator 或真实设备 |

**推荐顺序**：先用 `simulate_data.py`（5 秒跑通）；再上 `modbus_simulator + run_edge_adapter` 测试真实 modbus 适配器路径。

---

## 1. simulate_data.py（最简单）

直接 POST 到 `/data/ingest`，跳过协议层。

```bash
# 1Hz sine 波持续上报
.venv/bin/python -m scripts.simulate_data \
    --device-code GW-001 \
    --base-url http://localhost:8000 \
    --api-key edge-secret-key \
    --rate-hz 1 --duration 30

# 15 秒后强制越界（演示告警链路）
.venv/bin/python -m scripts.simulate_data \
    --device-code GW-001 \
    --rate-hz 1 --duration 30 --threshold-trigger 15
```

要求：device 下已有带 `alert_rules` 的测点（可参考 [points.md §alert_rules 字段语义](../api/points.md#alert_rules-字段语义)）。

启动后到 `/api/v1/alerts` 应能看到新告警；`/api/v1/dashboard/stats` 显示活跃告警计数。

---

## 2. mqtt_injector.py（模拟 MQTT 网关）

按 MQTT 网关的行为生成读数，但绕开 broker 直接调 ingest。适合复现"网关批量上报"场景。

```bash
.venv/bin/python -m scripts.mqtt_injector \
    --device-code GW-MQTT-01 \
    --point-codes ACC-X ACC-Y TEMP \
    --base-url http://localhost:8000 \
    --api-key edge-secret-key \
    --rate-hz 1 --mode sine --duration 60

# 5 秒后强制越界
.venv/bin/python -m scripts.mqtt_injector \
    --device-code GW-MQTT-01 --point-codes ACC-X \
    --rate-hz 2 --mode threshold-test --duration 30
```

---

## 3. modbus_simulator.py + run_edge_adapter.py（最完整）

完整覆盖"协议适配器 + 边缘网关 + ingest"三层：

### 步骤

```bash
# A. 启动内存 Modbus TCP 服务（端口 5020）
.venv/bin/python -m scripts.modbus_simulator --port 5020 --rate-hz 2 &

# B. 创建 modbus 设备（指向 5020）
curl -X POST http://localhost:8000/api/v1/devices \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{
        "project_id": 1,
        "device_code": "GW-MODBUS-DEMO",
        "protocol": "modbus_tcp",
        "config": {
            "host": "127.0.0.1", "port": 5020, "slave_id": 1,
            "device_code": "GW-MODBUS-DEMO",
            "registers": [
                {"address": 0, "count": 2, "data_type": "float32",
                 "point_code": "ACC-X", "scale": 0.001, "unit": "m/s2"}
            ]
        }
    }'

# C. 在该设备下创建同名测点（带 alert_rules 演示告警）
curl -X POST http://localhost:8000/api/v1/points \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{
        "device_id": <DEVICE_ID>,
        "point_code": "ACC-X",
        "unit": "m/s2",
        "alert_rules": [{"operator": "gt", "threshold": 0.5, "level": "warning"}]
    }'

# D. 启动边缘网关读取 modbus_simulator 并推 ingest
.venv/bin/python -m scripts.run_edge_adapter \
    --device-code GW-MODBUS-DEMO \
    --protocol modbus_tcp \
    --host 127.0.0.1 --port 5020 \
    --base-url http://localhost:8000 \
    --api-key edge-secret-key \
    --max-iterations 60
```

Ctrl+C 优雅退出；观察 `/api/v1/data/timeseries?point_id=<...>` 与 `/api/v1/alerts` 出现数据。

---

## 4. 常见问题

- **ingest 返回 401**：检查 `--api-key` 是否与 `.env` 中 `EDGE_API_KEY` 一致
- **找不到 device_code**：先用 `GET /api/v1/devices?project_id=<pid>` 确认设备已创建
- **告警没触发**：确认测点的 `alert_rules` 字段已设置；sine 波幅度默认较小，可在 `modbus_simulator.py` 里把 `amp` 调大到 1.0+ 触发 0.5 阈值
- **modbus 连接失败**：确认 modbus_simulator 已启动且监听 0.0.0.0:5020
- **`modbus_simulator.py` 在 pymodbus 3.14+ 启动失败**：pymodbus 3.14 重写了 server API（用 `ModbusSimulatorContext` + `SimDevice/SimData`），原 `ModbusServerContext(slaves=...)` 已 deprecated。模拟器脚本需按新版 API 改写（v0.5+ 计划）；`ModbusTcpAdapter` 客户端本身不受影响，已通过 mock 单测覆盖。