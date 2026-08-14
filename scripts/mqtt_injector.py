"""MQTT 网关行为注入器：直接调云端 /data/ingest，等价于 MQTT 网关的行为。

跳过 MQTT broker 层，便于无 broker 环境下演示与测试。

用法：
    python -m scripts.mqtt_injector \
        --device-code GW-MQTT-01 --channel-codes ACC-X ACC-Y \
        --api-key edge-secret-key --base-url http://localhost:8000 \
        --rate-hz 1 --mode sine --duration 60
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import random
from datetime import UTC, datetime

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mqtt_injector")


def make_value(mode: str, t: float, i: int) -> float:
    if mode == "sine":
        return math.sin(2 * math.pi * 0.5 * t) + i * 0.01
    if mode == "random":
        return random.random()
    if mode == "threshold-test":
        # t=5s 时强制越界一次
        return 10.0 if 4.9 < t < 5.1 else 0.1
    return 0.0


async def run(
    base_url: str,
    api_key: str,
    device_code: str,
    channel_codes: list[str],
    rate_hz: float,
    mode: str,
    duration: float,
) -> None:
    period = 1.0 / max(rate_hz, 0.1)
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    start = asyncio.get_event_loop().time()
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
        i = 0
        while True:
            t = asyncio.get_event_loop().time() - start
            if duration > 0 and t >= duration:
                break
            readings = [
                {
                    "device_code": device_code,
                    "channel_code": pc,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "value": make_value(mode, t, i),
                    "unit": "m/s2",
                }
                for pc in channel_codes
            ]
            try:
                resp = await client.post(
                    "/api/v1/data/ingest", json={"readings": readings}, headers=headers
                )
                if resp.status_code != 200:
                    logger.warning("ingest 失败: %d %s", resp.status_code, resp.text[:200])
                else:
                    logger.info("ingested %d readings (t=%.1fs)", len(readings), t)
            except Exception as exc:
                logger.warning("ingest 异常: %s", exc)
            i += 1
            await asyncio.sleep(period)


def main() -> None:
    p = argparse.ArgumentParser(description="MQTT 行为注入器（直推 /data/ingest）")
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--api-key", default="edge-secret-key")
    p.add_argument("--device-code", required=True)
    p.add_argument("--channel-codes", nargs="+", required=True)
    p.add_argument("--rate-hz", type=float, default=1.0)
    p.add_argument("--mode", default="sine", choices=["sine", "random", "threshold-test"])
    p.add_argument("--duration", type=float, default=0.0, help="0 表示无限")
    args = p.parse_args()
    try:
        asyncio.run(
            run(
                args.base_url,
                args.api_key,
                args.device_code,
                args.channel_codes,
                args.rate_hz,
                args.mode,
                args.duration,
            )
        )
    except KeyboardInterrupt:
        logger.info("已停止")


if __name__ == "__main__":
    main()
