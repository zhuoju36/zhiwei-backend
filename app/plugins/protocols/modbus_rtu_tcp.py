"""Modbus RTU over TCP 监听型适配器（DTU 透传接入，v0.9）。

场景（拓扑 A）：现场仪表(RS485/Modbus RTU) → DTU(4G 透传) → 云端 dtu_server 监听端口。
DTU 是透明管道，把现场设备返回的 Modbus RTU 响应帧字节流原样推上来。

本适配器作为"帧解析器"（supports_listen=True）：把字节流切成合法 RTU 帧
（CRC16 校验、粘包/半包处理），解析读保持寄存器响应，按 registers 映射为
RawReading。字节流缓冲由 TcpServerManager 负责。

设备配置示例（存入 devices.config JSONB，一端口一设备）：

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

约定：DTU 透传的响应帧寄存器从 address 0 起连续排布（与配置 registers 的
address 一一对应）。
"""

import logging
from typing import Any

from app.plugins.protocols.base import ProtocolAdapter, ProtocolConfig, RawReading
from app.plugins.protocols.modbus_tcp_adapter import _DECODERS

logger = logging.getLogger(__name__)

_READ_HOLDING = 0x03


def crc16_modbus(data: bytes) -> int:
    """Modbus CRC16（多项式 0xA001，初值 0xFFFF）。"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def split_rtu_frames(buf: bytes) -> tuple[list[bytes], bytes]:
    """从字节流切分出完整合法的 RTU 帧，返回 (frames, 剩余字节)。

    帧长推断：
    - 异常响应（func|0x80）：addr + func + code + crc2 = 5 字节
    - 读保持寄存器响应（0x03）：addr + func + byte_count + data + crc2 = 3 + byte_count + 2
    - 其它功能码响应无法从头部判断长度：丢弃首字节重同步

    CRC 校验失败时丢一字节重同步；长度不足视为半包等待更多数据。
    """
    frames: list[bytes] = []
    rest = bytes(buf)
    while len(rest) >= 5:
        func = rest[1]
        if func & 0x80:
            frame_len = 5
        elif func == _READ_HOLDING:
            frame_len = 3 + rest[2] + 2
        else:
            rest = rest[1:]  # 未知功能码：重同步
            continue
        if len(rest) < frame_len:
            break  # 半包
        frame = rest[:frame_len]
        if crc16_modbus(frame[:-2]) == (frame[-2] | (frame[-1] << 8)):
            frames.append(frame)
            rest = rest[frame_len:]
        else:
            rest = rest[1:]  # CRC 错：重同步
    return frames, rest


class ModbusRtuOverTcpAdapter(ProtocolAdapter):
    name = "modbus_rtu_over_tcp"
    version = "1.0.0"
    supports_batch = True
    supports_listen = True

    def __init__(self, config: ProtocolConfig):
        super().__init__(config)
        self._slave_id: int = int(config.extra.get("slave_id", 1))
        self._device_code: str = config.extra.get("device_code", "")
        self._registers: list[dict[str, Any]] = list(config.extra.get("registers", []))

    async def connect(self) -> None:
        # 监听型适配器：由 dtu_server 接收连接，无需主动连接设备
        raise NotImplementedError("modbus_rtu_over_tcp 为监听型适配器，无需 connect")

    async def read_batch(self) -> list[RawReading]:
        # 监听型适配器：由 dtu_server 通过 decode_stream 驱动
        raise NotImplementedError("modbus_rtu_over_tcp 由 dtu_server 驱动，不支持 read_batch")

    async def disconnect(self) -> None:
        pass

    def decode_stream(self, data: bytes) -> list[RawReading]:
        frames, _ = split_rtu_frames(data)
        readings: list[RawReading] = []
        for frame in frames:
            readings.extend(self._decode_frame(frame))
        return readings

    def _decode_frame(self, frame: bytes) -> list[RawReading]:
        if len(frame) < 5 or frame[0] != self._slave_id:
            return []
        func = frame[1]
        if func & 0x80:
            logger.warning(
                "Modbus RTU 异常响应: addr=%s func=%s code=%s",
                frame[0],
                func & 0x7F,
                frame[2],
            )
            return []
        if func != _READ_HOLDING:
            return []
        byte_count = frame[2]
        data = frame[3 : 3 + byte_count]
        registers = [(data[i] << 8) | data[i + 1] for i in range(0, len(data) - 1, 2)]
        ts = self._now()
        readings: list[RawReading] = []
        for reg in self._registers:
            idx = int(reg["address"])
            dtype = reg.get("data_type", "uint16")
            decoder, count = _DECODERS.get(dtype, _DECODERS["uint16"])
            if idx + count > len(registers):
                continue  # 响应数据不足
            value = decoder(registers[idx : idx + count]) * float(reg.get("scale", 1.0))
            readings.append(
                RawReading(
                    device_code=self._device_code,
                    channel_code=reg.get("channel_code", ""),
                    timestamp=ts,
                    value=value,
                    unit=reg.get("unit", ""),
                    quality="good",
                )
            )
        return readings
