"""协议元数据 Schema。"""

from pydantic import BaseModel


class ProtocolMeta(BaseModel):
    name: str
    version: str
    supports_batch: bool
    config_schema: dict


# config_schema 描述 Device.config JSONB 的期望结构（按 name 不同而不同）。
# 这里给出最简约定，详细 schema 见 docs/api/protocols.md。
CONFIG_SCHEMAS: dict[str, dict] = {
    "http_json": {
        "host": "http://...",
        "port": 9000,
        "path": "/readings",
        "device_code": "GW-001",
        "sample_interval_ms": 1000,
    },
    "modbus_tcp": {
        "host": "10.0.0.10",
        "port": 502,
        "slave_id": 1,
        "timeout_ms": 3000,
        "device_code": "GW-001",
        "registers": [
            {
                "address": 0,
                "count": 2,
                "data_type": "float32",
                "channel_code": "ACC-X",
                "scale": 1.0,
                "unit": "m/s2",
            }
        ],
    },
    "mqtt": {
        "host": "broker.local",
        "port": 1883,
        "topic": "shm/+/+/value",
        "username": "edge",
        "password": "secret",
        "queue_max": 1000,
        "use_tls": False,
    },
}
