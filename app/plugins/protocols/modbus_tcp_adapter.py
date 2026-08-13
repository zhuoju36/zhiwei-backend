"""Modbus TCP 协议适配器。

从 pymodbus 的 AsyncModbusTcpClient 读取保持寄存器（Holding Registers），
按 data_type 解码为浮点数，应用 scale 后构造 RawReading。

设备配置示例（存入 devices.config JSONB）：

    {
      "host": "10.0.0.10",
      "port": 502,
      "slave_id": 1,
      "timeout_ms": 3000,
      "registers": [
        {"address": 0, "count": 2, "data_type": "float32",
         "point_code": "ACC-X", "scale": 0.001, "unit": "m/s2"},
        {"address": 2, "count": 1, "data_type": "uint16",
         "point_code": "TEMP", "scale": 0.1, "unit": "°C"}
      ]
    }
"""

import logging
import struct
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from app.plugins.protocols.base import ProtocolAdapter, ProtocolConfig, RawReading

logger = logging.getLogger(__name__)


def _decode_uint16(registers: list[int]) -> float:
    return float(registers[0])


def _decode_int16(registers: list[int]) -> float:
    val = registers[0]
    if val >= 0x8000:
        val -= 0x10000
    return float(val)


def _decode_uint32(registers: list[int]) -> float:
    return float((registers[0] << 16) | registers[1])


def _decode_int32(registers: list[int]) -> float:
    val = (registers[0] << 16) | registers[1]
    if val >= 0x80000000:
        val -= 0x100000000
    return float(val)


def _decode_float32(registers: list[int]) -> float:
    return struct.unpack(">f", struct.pack(">HH", registers[0], registers[1]))[0]


def _decode_float64(registers: list[int]) -> float:
    return struct.unpack(
        ">d",
        struct.pack(
            ">II", (registers[0] << 16) | registers[1], (registers[2] << 16) | registers[3]
        ),
    )[0]


_DECODERS = {
    "uint16": (_decode_uint16, 1),
    "int16": (_decode_int16, 1),
    "uint32": (_decode_uint32, 2),
    "int32": (_decode_int32, 2),
    "float32": (_decode_float32, 2),
    "float64": (_decode_float64, 4),
}


class ModbusTcpAdapter(ProtocolAdapter):
    name = "modbus_tcp"
    version = "1.0.0"
    supports_batch = True

    def __init__(self, config: ProtocolConfig):
        super().__init__(config)
        self._client: AsyncModbusTcpClient | None = None
        self._slave_id: int = int(config.extra.get("slave_id", 1))
        self._registers: list[dict[str, Any]] = list(config.extra.get("registers", []))

    async def connect(self) -> None:
        timeout_s = self.config.timeout_ms / 1000 if self.config.timeout_ms else 3.0
        self._client = AsyncModbusTcpClient(
            host=self.config.host,
            port=self.config.port,
            timeout=timeout_s,
        )
        connected = await self._client.connect()
        if not connected:
            raise ConnectionError(f"Modbus TCP 连接失败: {self.config.host}:{self.config.port}")
        self._connected = True

    async def read_batch(self) -> list[RawReading]:
        if not self._client or not self._connected:
            raise ConnectionError("Modbus client not connected")
        ts = self._now()
        readings: list[RawReading] = []
        for reg in self._registers:
            point_code = reg.get("point_code", "")
            dtype = reg.get("data_type", "uint16")
            scale = float(reg.get("scale", 1.0))
            unit = reg.get("unit", "")
            decoder, expected_count = _DECODERS.get(dtype, (_decode_uint16, 1))
            try:
                response = await self._client.read_holding_registers(
                    address=int(reg["address"]),
                    count=int(reg.get("count", expected_count)),
                    slave=self._slave_id,
                )
                if response.isError():
                    raise ModbusException(str(response))
                registers = response.registers[:expected_count]
                value = decoder(registers) * scale
                readings.append(
                    RawReading(
                        device_code=self.config.extra.get("device_code", ""),
                        point_code=point_code,
                        timestamp=ts,
                        value=value,
                        unit=unit,
                        quality="good",
                    )
                )
            except Exception as exc:
                logger.warning("Modbus 读取失败 (point=%s): %s", point_code, exc)
                readings.append(
                    RawReading(
                        device_code=self.config.extra.get("device_code", ""),
                        point_code=point_code,
                        timestamp=ts,
                        value=0.0,
                        unit=unit,
                        quality="bad",
                    )
                )
        return readings

    async def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            self._connected = False
