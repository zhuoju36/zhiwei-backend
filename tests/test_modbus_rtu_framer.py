"""Modbus RTU 帧解析单元测试：CRC16、粘包/半包、坏帧、解码。"""

import struct

from app.plugins.protocols.base import ProtocolConfig
from app.plugins.protocols.modbus_rtu_tcp import (
    ModbusRtuOverTcpAdapter,
    crc16_modbus,
    split_rtu_frames,
)


def rtu_response(slave: int, registers: list[int]) -> bytes:
    """构造读保持寄存器（0x03）RTU 响应帧。"""
    data = b"".join(struct.pack(">H", r) for r in registers)
    body = bytes([slave, 0x03, len(data)]) + data
    crc = crc16_modbus(body)
    return body + struct.pack("<H", crc)  # CRC 低字节在前


def _adapter(registers: list[dict]) -> ModbusRtuOverTcpAdapter:
    return ModbusRtuOverTcpAdapter(
        ProtocolConfig(
            host="0.0.0.0",
            port=5021,
            extra={
                "slave_id": 1,
                "device_code": "GW-DTU-001",
                "registers": registers,
            },
        )
    )


def test_crc16_known_vector() -> None:
    """CRC-16/MODBUS 标准校验向量：check("123456789") == 0x4B37。"""
    assert crc16_modbus(b"123456789") == 0x4B37


def test_split_single_frame() -> None:
    frame = rtu_response(1, [0x0001, 0x0002])
    frames, rest = split_rtu_frames(frame)
    assert frames == [frame]
    assert rest == b""


def test_split_sticky_packets() -> None:
    """两个帧粘在一起应完整切出。"""
    f1 = rtu_response(1, [0x0001])
    f2 = rtu_response(1, [0x1234])
    frames, rest = split_rtu_frames(f1 + f2)
    assert frames == [f1, f2]
    assert rest == b""


def test_split_half_packet_waits() -> None:
    """半包应保留为剩余字节等待后续数据。"""
    frame = rtu_response(1, [0x0001, 0x0002])
    frames, rest = split_rtu_frames(frame[:-2])  # 缺 CRC
    assert frames == []
    assert rest == frame[:-2]


def test_split_bad_crc_resync() -> None:
    """CRC 错误的帧应被丢弃并重同步到下一个合法帧。"""
    good = rtu_response(1, [0x00AB])
    bad = rtu_response(1, [0x00CD])
    corrupted = bad[:-1] + bytes([bad[-1] ^ 0xFF])  # 翻转 CRC 末字节
    frames, rest = split_rtu_frames(corrupted + good)
    assert frames == [good]
    assert rest == b""


def test_decode_uint16_registers() -> None:
    adapter = _adapter(
        [
            {
                "address": 0,
                "count": 1,
                "data_type": "uint16",
                "channel_code": "TEMP",
                "scale": 0.1,
                "unit": "°C",
            },
        ]
    )
    readings = adapter.decode_stream(rtu_response(1, [0x0190]))  # 400 * 0.1 = 40.0
    assert len(readings) == 1
    r = readings[0]
    assert r.device_code == "GW-DTU-001"
    assert r.channel_code == "TEMP"
    assert abs(r.value - 40.0) < 1e-6
    assert r.quality == "good"


def test_decode_float32() -> None:
    adapter = _adapter(
        [
            {
                "address": 0,
                "count": 2,
                "data_type": "float32",
                "channel_code": "ACC-X",
                "scale": 1.0,
                "unit": "m/s2",
            },
        ]
    )
    # float32 3.0 = 0x40400000
    readings = adapter.decode_stream(rtu_response(1, [0x4040, 0x0000]))
    assert len(readings) == 1
    assert abs(readings[0].value - 3.0) < 1e-6


def test_decode_wrong_slave_ignored() -> None:
    adapter = _adapter([{"address": 0, "count": 1, "data_type": "uint16", "channel_code": "X"}])
    readings = adapter.decode_stream(rtu_response(2, [0x0001]))  # slave 2 ≠ 配置 1
    assert readings == []


def test_decode_exception_response_ignored() -> None:
    adapter = _adapter([{"address": 0, "count": 1, "data_type": "uint16", "channel_code": "X"}])
    body = bytes([1, 0x83, 0x02])  # 异常响应：func 0x03|0x80, code 2
    crc = crc16_modbus(body)
    frame = body + struct.pack("<H", crc)
    assert adapter.decode_stream(frame) == []
