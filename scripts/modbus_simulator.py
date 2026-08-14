"""Modbus TCP 模拟器：在内存中启动一个 Modbus TCP 服务，按波形生成保持寄存器数据。

用 pymodbus.server 的 StartTcpServer + ModbusServerContext，无需真实硬件。
配套 app/plugins/protocols/modbus_tcp_adapter.py 使用。

用法：
    python -m scripts.modbus_simulator --port 5020 --rate-hz 1

启动后，外部 ModbusTcpAdapter 配置如下即可读取：
    {
      "host": "127.0.0.1", "port": 5020,
      "registers": [{"address": 0, "count": 2, "data_type": "float32",
                     "channel_code": "ACC-X", "scale": 1.0, "unit": "m/s2"}]
    }
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import random
import struct
import time
from typing import Any

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.server import StartTcpServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("modbus_simulator")


# 默认虚拟寄存器：地址 0/2/4 起各放 2 个寄存器（float32 编码）
DEFAULT_REGISTERS = [
    {
        "address": 0,
        "channel_code": "ACC-X",
        "wave": "sine",
        "amp": 1.0,
        "bias": 0.0,
        "freq_hz": 0.5,
    },
    {
        "address": 2,
        "channel_code": "ACC-Y",
        "wave": "sine",
        "amp": 0.5,
        "bias": 0.0,
        "freq_hz": 0.7,
    },
    {
        "address": 4,
        "channel_code": "TEMP",
        "wave": "random",
        "amp": 5.0,
        "bias": 25.0,
        "freq_hz": 0.1,
    },
]


def _encode_float32(value: float) -> tuple[int, int]:
    hi, lo = struct.unpack(">HH", struct.pack(">f", value))
    return hi, lo


def make_value(spec: dict[str, Any], t: float) -> float:
    """按波形规范生成一个标量。"""
    wave = spec.get("wave", "sine")
    amp = float(spec.get("amp", 1.0))
    bias = float(spec.get("bias", 0.0))
    freq = float(spec.get("freq_hz", 0.5))
    if wave == "sine":
        return bias + amp * math.sin(2 * math.pi * freq * t)
    if wave == "random":
        return bias + amp * (random.random() - 0.5) * 2
    if wave == "threshold-spike":
        # 大部分时间低频正弦，每 10 秒一次尖峰
        spike = 1.0 if int(t) % 10 == 0 and (t % 1) < 0.2 else 0.0
        return bias + amp * math.sin(2 * math.pi * freq * t) + spike * amp * 5
    return bias


async def updater(context: ModbusServerContext, registers: list[dict], rate_hz: float) -> None:
    """周期更新所有虚拟寄存器的值。"""
    period = 1.0 / max(rate_hz, 0.1)
    start = time.monotonic()
    while True:
        t = time.monotonic() - start
        # 写入到默认 slave 的 holding registers
        slave = context.slaves()[0] if context.slaves() else context[0]
        store = slave.store
        hr_block = store["hr"]
        for reg in registers:
            addr = int(reg["address"])
            value = make_value(reg, t)
            hi, lo = _encode_float32(value)
            hr_block.setValues(addr, [hi, lo])
        await asyncio.sleep(period)


async def run(port: int, rate_hz: float) -> None:
    # 构建一个足够大的保持寄存器块（覆盖最大地址 + 2）
    # pymodbus 3.14 的 SimData 校验要求 address >= 1（内部做 address-1 越界检查）
    block = ModbusSequentialDataBlock(1, [0] * 1024)
    context = ModbusServerContext(slaves=block, single=True)

    server_task = asyncio.create_task(StartTcpServer(context=context, address=("0.0.0.0", port)))
    update_task = asyncio.create_task(updater(context, DEFAULT_REGISTERS, rate_hz))
    logger.info("Modbus 模拟器已启动: port=%d, rate=%.1f Hz", port, rate_hz)
    try:
        await asyncio.gather(server_task, update_task)
    except asyncio.CancelledError:
        server_task.cancel()
        update_task.cancel()


def main() -> None:
    p = argparse.ArgumentParser(description="Modbus TCP 模拟器")
    p.add_argument("--port", type=int, default=5020)
    p.add_argument("--rate-hz", type=float, default=1.0, help="数据更新频率")
    args = p.parse_args()
    try:
        asyncio.run(run(args.port, args.rate_hz))
    except KeyboardInterrupt:
        logger.info("已停止")


if __name__ == "__main__":
    main()
