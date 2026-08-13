"""边缘网关参考脚本：从后端拉设备配置 → 实例化适配器 → 循环采集并 ingest。

生产环境下应部署为独立 Docker / 工控机进程；本脚本是**参考实现**，展示
AdapterRegistry + Device.config + /data/ingest 的完整调用模式。

用法：
    python -m scripts.run_edge_adapter --device-code GW-001 \
        --base-url http://localhost:8000 --api-key edge-secret-key

也可配合 modbus_simulator 测试：
    python -m scripts.modbus_simulator --port 5020 &
    python -m scripts.run_edge_adapter --device-code GW-MODBUS-DEMO
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

import httpx

from app.plugins.protocols.base import ProtocolAdapter, ProtocolConfig, RawReading
from app.plugins.protocols.registry import AdapterRegistry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("edge")


def fetch_device_config(
    base_url: str, api_key: str, device_id: int | None, device_code: str | None
) -> dict:
    """用 admin JWT 拉取 device 配置（参考实现：admin 凭据由环境变量传入）。"""
    raise NotImplementedError("需要 admin JWT；演示请改用 --device-code 直传 config")


def build_adapter(protocol: str, device_code: str, config: dict[str, Any]) -> ProtocolAdapter:
    cls = AdapterRegistry.get(protocol)
    if cls is None:
        raise RuntimeError(f"未注册协议: {protocol}；可用: {AdapterRegistry.names()}")
    cfg = ProtocolConfig(
        host=config.get("host", ""),
        port=int(config.get("port", 0)),
        sample_interval_ms=int(config.get("sample_interval_ms", 1000)),
        timeout_ms=int(config.get("timeout_ms", 5000)),
        register_map=config.get("register_map", {}),
        extra=config,
    )
    adapter = cls(cfg)
    # 让读取时的 device_code 由 config 决定（适配器读 self.config.extra）
    adapter.config.extra.setdefault("device_code", device_code)
    return adapter


async def push_ingest(
    client: httpx.AsyncClient, base_url: str, api_key: str, readings: list[RawReading]
) -> None:
    payload = {
        "readings": [
            {
                "device_code": r.device_code,
                "point_code": r.point_code,
                "timestamp": r.timestamp.isoformat(),
                "value": r.value,
                "unit": r.unit,
                "quality": r.quality,
                "extra": r.extra,
            }
            for r in readings
        ]
    }
    resp = await client.post(
        f"{base_url}/api/v1/data/ingest",
        json=payload,
        headers={"X-API-Key": api_key},
    )
    if resp.status_code != 200:
        logger.warning("ingest 失败: %d %s", resp.status_code, resp.text[:200])
    else:
        logger.info("ingested %d readings", len(readings))


async def run_loop(
    base_url: str,
    api_key: str,
    protocol: str,
    device_code: str,
    config: dict[str, Any],
    max_iterations: int,
) -> None:
    adapter = build_adapter(protocol, device_code, config)
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await adapter.connect()
            logger.info("adapter 已连接: %s", protocol)
            for _i in range(max_iterations):
                try:
                    readings = await adapter.read_batch()
                except Exception as exc:
                    logger.warning("read_batch 失败: %s", exc)
                    await asyncio.sleep(adapter.config.sample_interval_ms / 1000)
                    continue
                if readings:
                    await push_ingest(client, base_url, api_key, readings)
                await asyncio.sleep(adapter.config.sample_interval_ms / 1000)
        finally:
            await adapter.disconnect()


def main() -> None:
    p = argparse.ArgumentParser(description="边缘网关参考运行脚本")
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--api-key", default="edge-secret-key")
    p.add_argument("--device-code", required=True)
    p.add_argument("--protocol", required=True, help="协议名：modbus_tcp / mqtt / http_json")
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--config-json", default="{}", help="额外 JSON 配置，覆盖协议默认")
    p.add_argument("--max-iterations", type=int, default=0, help="0 表示无限")
    args = p.parse_args()

    import json

    extra = json.loads(args.config_json) if args.config_json else {}
    config: dict[str, Any] = {
        "host": args.host,
        "port": args.port,
        "sample_interval_ms": 1000,
        **extra,
    }
    try:
        asyncio.run(
            run_loop(
                args.base_url,
                args.api_key,
                args.protocol,
                args.device_code,
                config,
                args.max_iterations,
            )
        )
    except KeyboardInterrupt:
        logger.info("已停止")


if __name__ == "__main__":
    main()
