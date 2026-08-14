"""模拟器脚本与边缘网关参考脚本的 smoke 测试。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_modbus_simulator_imports() -> None:
    """模拟器脚本可正常导入（不依赖启动服务）。"""
    from scripts import modbus_simulator

    assert callable(modbus_simulator.main)


def test_mqtt_injector_make_value_sine() -> None:
    from scripts.mqtt_injector import make_value

    assert abs(make_value("sine", 0.0, 0)) < 1e-9
    # sin(2π·0.5·0.25) = sin(π/4) ≈ 0.7071
    assert abs(make_value("sine", 0.25, 0) - 0.7071067811865475) < 1e-6


def test_mqtt_injector_threshold_test() -> None:
    from scripts.mqtt_injector import make_value

    # t=5s 强制越界
    assert make_value("threshold-test", 4.9, 0) < 1.0
    assert make_value("threshold-test", 5.0, 0) > 5.0


def test_simulate_data_make_value_with_trigger() -> None:
    from scripts.simulate_data import make_value

    base = make_value("sine", 10.0, threshold_trigger=-1, baseline=0.1, amp=0.5)
    assert base < 1.0
    triggered = make_value("sine", 20.0, threshold_trigger=15.0, baseline=0.1, amp=0.5)
    assert triggered > 1.0  # baseline + amp*5 = 2.6


async def test_run_edge_adapter_loop() -> None:
    """run_edge_adapter 的核心循环：用 fake adapter + mock httpx 验证一次完整 read→ingest。

    FakeAdapter 在第二次 read_batch 时主动 raise CancelledError 跳出循环，
    这是真实使用中 Ctrl+C / 任务取消的预期路径。run_loop 把 CancelledError
    透传以触发 finally 块的 adapter.disconnect。
    """
    from scripts import run_edge_adapter

    fake_readings = [
        MagicMock(
            device_code="GW",
            channel_code="P1",
            timestamp=MagicMock(isoform=lambda: "2026-08-13T12:00:00+00:00"),
            value=1.0,
            unit="m/s2",
            quality="good",
            extra={},
        )
    ]

    class FakeAdapter:
        def __init__(self, config):
            self.config = config
            self.connect_called = 0
            self.read_called = 0
            self.disconnect_called = 0

        async def connect(self):
            self.connect_called += 1

        async def read_batch(self):
            self.read_called += 1
            if self.read_called >= 2:
                raise asyncio.CancelledError()
            return fake_readings

        async def disconnect(self):
            self.disconnect_called += 1

    cfg = MagicMock()
    cfg.sample_interval_ms = 100
    cfg.timeout_ms = 1000
    fake_adapter = FakeAdapter(cfg)

    with patch.object(run_edge_adapter, "build_adapter", return_value=fake_adapter):
        with patch.object(run_edge_adapter, "httpx") as fake_httpx:
            fake_client = MagicMock()
            fake_client.post = AsyncMock(return_value=MagicMock(status_code=200))
            fake_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=fake_client)
            fake_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(asyncio.CancelledError):
                await run_edge_adapter.run_loop(
                    base_url="http://localhost:8000",
                    api_key="test",
                    protocol="http_json",
                    device_code="GW",
                    config={"host": "x"},
                    max_iterations=5,
                )

    assert fake_adapter.connect_called == 1
    assert fake_adapter.disconnect_called == 1
    assert fake_client.post.called
