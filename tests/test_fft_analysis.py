"""FFT 分析插件单元测试。"""

import asyncio

import numpy as np
import pytest

from app.plugins.analyzers.fft_analysis import FftAnalysis


def _sine(freq_hz: float, sr: float, duration_s: float = 1.0) -> np.ndarray:
    n = int(sr * duration_s)
    t = np.arange(n) / sr
    return np.sin(2 * np.pi * freq_hz * t)


def test_fft_detects_50hz_sine() -> None:
    """50Hz 正弦信号在 100Hz 采样下应识别 dominant_freq 接近 50。"""
    plugin = FftAnalysis()
    sr = 200.0
    data = _sine(50.0, sr, duration_s=2.0)
    result = asyncio.run(
        plugin.analyze(
            channel_id=1,
            time_range=("2026-01-01T00:00:00Z", "2026-01-01T00:00:02Z"),
            data=data,
            config={"sampling_rate": sr},
        )
    )
    assert abs(result["dominant_freq"] - 50.0) < 1.0
    assert result["num_samples"] == 400
    assert result["sampling_rate"] == sr
    assert result["nyquist_freq"] == sr / 2


def test_fft_finds_higher_harmonic() -> None:
    """150Hz 正弦（远超 Nyquist）会被混叠到 50Hz（fs=200Hz, Nyquist=100Hz）。"""
    plugin = FftAnalysis()
    sr = 200.0
    data = _sine(150.0, sr, duration_s=2.0)
    result = asyncio.run(
        plugin.analyze(channel_id=1, time_range=("", ""), data=data, config={"sampling_rate": sr})
    )
    # 150Hz 在 200Hz 采样下混叠为 200-150=50Hz
    assert abs(result["dominant_freq"] - 50.0) < 1.0


def test_fft_requires_sampling_rate() -> None:
    plugin = FftAnalysis()
    data = _sine(10.0, 100.0)
    with pytest.raises(ValueError):
        asyncio.run(plugin.analyze(1, ("", ""), data, config={}))


def test_fft_rejects_invalid_sampling_rate() -> None:
    plugin = FftAnalysis()
    data = _sine(10.0, 100.0)
    with pytest.raises(ValueError):
        asyncio.run(plugin.analyze(1, ("", ""), data, config={"sampling_rate": 0}))


def test_fft_rejects_too_short_data() -> None:
    plugin = FftAnalysis()
    with pytest.raises(ValueError):
        asyncio.run(
            plugin.analyze(1, ("", ""), data=np.array([1.0]), config={"sampling_rate": 100})
        )


def test_fft_warns_on_small_sample() -> None:
    plugin = FftAnalysis()
    data = _sine(10.0, 100.0, duration_s=0.2)  # 20 samples
    result = asyncio.run(plugin.analyze(1, ("", ""), data=data, config={"sampling_rate": 100}))
    assert "样本数过少" in result["warnings"][0]


def test_fft_top_peaks_returns_list() -> None:
    plugin = FftAnalysis()
    sr = 200.0
    # 30Hz + 60Hz 叠加
    data = _sine(30.0, sr, duration_s=2.0) + 0.5 * _sine(60.0, sr, duration_s=2.0)
    result = asyncio.run(plugin.analyze(1, ("", ""), data=data, config={"sampling_rate": sr}))
    peaks = result["top_peaks"]
    assert 1 <= len(peaks) <= 3
    assert peaks[0]["magnitude"] >= peaks[-1]["magnitude"]
