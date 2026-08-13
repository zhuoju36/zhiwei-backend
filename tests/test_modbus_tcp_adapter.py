"""Modbus TCP 适配器单元测试。"""

from unittest.mock import MagicMock

import pytest

from app.plugins.protocols.base import ProtocolConfig
from app.plugins.protocols.modbus_tcp_adapter import (
    ModbusTcpAdapter,
    _decode_float32,
    _decode_float64,
    _decode_int16,
    _decode_int32,
    _decode_uint16,
    _decode_uint32,
)


def test_decode_uint16() -> None:
    assert _decode_uint16([0x1234]) == 4660.0


def test_decode_int16_positive() -> None:
    assert _decode_int16([0x1234]) == 4660.0


def test_decode_int16_negative() -> None:
    # 0xFFFF as signed int16 = -1
    assert _decode_int16([0xFFFF]) == -1.0


def test_decode_uint32() -> None:
    assert _decode_uint32([0x1234, 0x5678]) == 0x12345678


def test_decode_int32_negative() -> None:
    # 0xFFFFFFFF = -1
    assert _decode_int32([0xFFFF, 0xFFFF]) == -1.0


def test_decode_float32() -> None:
    # 3.0 in IEEE 754 = 0x40400000 = [0x4040, 0x0000]
    assert abs(_decode_float32([0x4040, 0x0000]) - 3.0) < 1e-6


def test_decode_float64() -> None:
    # 2.0 in IEEE 754 double = 0x4000000000000000
    val = _decode_float64([0x4000, 0x0000, 0x0000, 0x0000])
    assert abs(val - 2.0) < 1e-12


async def test_read_batch_normal() -> None:
    """正常路径：所有寄存器读取成功。"""
    config = ProtocolConfig(
        host="127.0.0.1",
        port=5020,
        extra={
            "device_code": "GW-TEST",
            "slave_id": 1,
            "registers": [
                {
                    "address": 0,
                    "count": 2,
                    "data_type": "float32",
                    "point_code": "ACC-X",
                    "scale": 0.001,
                    "unit": "m/s2",
                },
                {
                    "address": 2,
                    "count": 1,
                    "data_type": "uint16",
                    "point_code": "TEMP",
                    "scale": 0.1,
                    "unit": "°C",
                },
            ],
        },
    )
    adapter = ModbusTcpAdapter(config)
    adapter._connected = True
    adapter._client = MagicMock()

    async def fake_read(address, count, slave):
        if address == 0:
            return MagicMock(isError=lambda: False, registers=[0x4040, 0x0000])  # 3.0
        if address == 2:
            return MagicMock(isError=lambda: False, registers=[250])  # 25.0 * scale=0.1
        return MagicMock(isError=lambda: True)

    adapter._client.read_holding_registers = fake_read
    readings = await adapter.read_batch()
    assert len(readings) == 2
    assert readings[0].point_code == "ACC-X"
    assert abs(readings[0].value - 3.0 * 0.001) < 1e-9
    assert readings[1].point_code == "TEMP"
    assert abs(readings[1].value - 25.0) < 1e-9
    assert all(r.quality == "good" for r in readings)


async def test_read_batch_isolates_point_errors() -> None:
    """单点错误不应影响其他点：失败点 quality='bad'，其他正常返回。"""
    config = ProtocolConfig(
        host="127.0.0.1",
        port=5020,
        extra={
            "device_code": "GW-TEST",
            "registers": [
                {"address": 0, "count": 1, "data_type": "uint16", "point_code": "P1"},
                {"address": 2, "count": 1, "data_type": "uint16", "point_code": "P2"},
            ],
        },
    )
    adapter = ModbusTcpAdapter(config)
    adapter._connected = True

    async def fake_read(address, count, slave):
        if address == 0:
            raise ConnectionError("Modbus 设备离线")
        return MagicMock(isError=lambda: False, registers=[100])

    adapter._client = MagicMock()
    adapter._client.read_holding_registers = fake_read
    readings = await adapter.read_batch()
    assert len(readings) == 2
    assert readings[0].quality == "bad"
    assert readings[0].value == 0.0
    assert readings[1].quality == "good"
    assert readings[1].value == 100.0


async def test_read_batch_not_connected() -> None:
    adapter = ModbusTcpAdapter(ProtocolConfig(host="x", extra={"registers": []}))
    with pytest.raises(ConnectionError):
        await adapter.read_batch()
