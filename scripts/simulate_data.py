"""通用数据模拟器：从后端拉取 device+points，按波形生成读数 POST 到 /data/ingest。

无需任何协议服务；适合最快的端到端演示、压测与告警链路验证。

用法：
    python -m scripts.simulate_data \
        --device-code GW-001 \
        --api-key edge-secret-key --base-url http://localhost:8000 \
        --rate-hz 1 --duration 30 --threshold-trigger 15
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
logger = logging.getLogger("simulate_data")


def make_value(mode: str, t: float, threshold_trigger: float, baseline: float, amp: float) -> float:
    if threshold_trigger > 0 and t >= threshold_trigger:
        # 强制越界一个高值
        return baseline + amp * 5
    if mode == "sine":
        return baseline + amp * math.sin(2 * math.pi * 0.3 * t)
    if mode == "random":
        return baseline + amp * (random.random() - 0.5) * 2
    return baseline


async def fetch_points(client: httpx.AsyncClient, base_url: str, device_code: str) -> list[dict]:
    """通过 device_code 查到 device_id 与其下属 points（用 list API）。"""
    # 列出设备
    resp = await client.get(
        "/api/v1/devices",
        params={"project_id": 1},  # 简化为演示项目；生产按 device_code 搜索
    )
    if resp.status_code != 200:
        logger.error("无法列出设备: %s", resp.text[:200])
        return []
    devices = [d for d in resp.json()["data"]["items"] if d["device_code"] == device_code]
    if not devices:
        logger.error("找不到 device_code=%s 的设备", device_code)
        return []
    device = devices[0]
    # 列出测点
    resp = await client.get("/api/v1/points", params={"device_id": device["id"]})
    if resp.status_code != 200:
        return []
    return resp.json()["data"]["items"]


async def run(
    base_url: str,
    api_key: str,
    device_code: str,
    rate_hz: float,
    duration: float,
    mode: str,
    threshold_trigger: float,
) -> None:
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
        points = await fetch_points(client, base_url, device_code)
        if not points:
            return
        logger.info("找到 %d 个测点: %s", len(points), [p["point_code"] for p in points])
        start = asyncio.get_event_loop().time()
        i = 0
        while True:
            t = asyncio.get_event_loop().time() - start
            if duration > 0 and t >= duration:
                break
            ts = datetime.now(UTC)
            readings = [
                {
                    "device_code": device_code,
                    "point_code": p["point_code"],
                    "timestamp": ts.isoformat(),
                    "value": make_value(mode, t, threshold_trigger, baseline=0.1, amp=0.5),
                    "unit": p.get("unit") or "m/s2",
                }
                for p in points
            ]
            try:
                resp = await client.post(
                    "/api/v1/data/ingest", json={"readings": readings}, headers=headers
                )
                if resp.status_code != 200:
                    logger.warning("ingest 失败: %d %s", resp.status_code, resp.text[:200])
                else:
                    logger.info("t=%.1fs ingested %d readings", t, len(readings))
            except Exception as exc:
                logger.warning("ingest 异常: %s", exc)
            i += 1
            await asyncio.sleep(1.0 / max(rate_hz, 0.1))


def main() -> None:
    p = argparse.ArgumentParser(description="通用时序数据模拟器")
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--api-key", default="edge-secret-key")
    p.add_argument("--device-code", required=True)
    p.add_argument("--rate-hz", type=float, default=1.0)
    p.add_argument("--duration", type=float, default=0.0)
    p.add_argument("--mode", default="sine", choices=["sine", "random"])
    p.add_argument(
        "--threshold-trigger", type=float, default=-1.0, help="t>=N 秒时强制越界一次，<0 关闭"
    )
    args = p.parse_args()
    try:
        asyncio.run(
            run(
                args.base_url,
                args.api_key,
                args.device_code,
                args.rate_hz,
                args.duration,
                args.mode,
                args.threshold_trigger,
            )
        )
    except KeyboardInterrupt:
        logger.info("已停止")


if __name__ == "__main__":
    main()
