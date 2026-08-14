"""FFT 频谱分析插件（v2 接口示例）。

输入：AnalysisInput（一维等间隔采样数组 + sampling_rate）。
输出：JSON 摘要（dominant_freq 等）+ NPZ 附件（完整频率/幅值数组）。
"""

import io
from typing import Any

import numpy as np
from scipy.fft import rfft, rfftfreq

from app.plugins.analyzers.base import AnalysisInput, AnalysisOutput, AnalysisPlugin


class FftAnalysis(AnalysisPlugin):
    name = "fft"
    display_name = "FFT 频谱分析"
    description = "快速傅里叶变换，输出主频、幅值谱与峰值列表（附件含完整频谱）"
    version = "2.0.0"
    input_channels = 1
    min_samples = 2
    params_schema = {
        "type": "object",
        "properties": {
            "sampling_rate": {
                "type": "number",
                "description": "采样率（Hz），缺省用通道配置的 sampling_rate",
                "exclusiveMinimum": 0,
            }
        },
    }

    async def analyze(self, data: AnalysisInput, config: dict[str, Any]) -> AnalysisOutput:
        arr = np.asarray(data.data, dtype=np.float64)
        if arr.size < 2:
            raise ValueError("data 长度不足以做 FFT")
        sr = float(config.get("sampling_rate", data.sampling_rate))
        if sr <= 0:
            raise ValueError("sampling_rate 必须 > 0")

        n = arr.size
        # 去直流，避免 0Hz 占主导
        arr = arr - arr.mean()
        spectrum = np.abs(rfft(arr)) / n
        freqs = rfftfreq(n, d=1.0 / sr)

        idx = int(np.argmax(spectrum))
        dominant_freq = float(freqs[idx])
        dominant_magnitude = float(spectrum[idx])

        warnings: list[str] = []
        if n < 64:
            warnings.append("样本数过少（<64），频谱分辨率低")

        summary: dict[str, Any] = {
            "channel_id": data.channel_ids[0],
            "sampling_rate": sr,
            "num_samples": n,
            "dominant_freq": dominant_freq,
            "dominant_magnitude": dominant_magnitude,
            "nyquist_freq": sr / 2.0,
            "freq_resolution": sr / n,
            "top_peaks": _top_peaks(freqs, spectrum, n_peaks=3),
            "warnings": warnings,
        }

        # NPZ 附件：完整频谱供前端绘图 / 深度分析
        npz_buf = io.BytesIO()
        np.savez(
            npz_buf,
            frequencies=freqs,
            magnitudes=spectrum,
            sampling_rate=sr,
            channel_id=data.channel_ids[0],
        )
        return AnalysisOutput(
            summary=summary,
            artifact=npz_buf.getvalue(),
            artifact_name=f"fft_{data.channel_ids[0]}.npz",
            artifact_type="application/octet-stream",
        )


def _top_peaks(freqs: np.ndarray, spectrum: np.ndarray, n_peaks: int = 3) -> list[dict[str, float]]:
    """返回频谱中前 n_peaks 个峰（局部最大值，按幅值降序）。"""
    peaks: list[tuple[float, float]] = []
    for i in range(1, len(spectrum) - 1):
        if spectrum[i] > spectrum[i - 1] and spectrum[i] > spectrum[i + 1]:
            peaks.append((float(freqs[i]), float(spectrum[i])))
    peaks.sort(key=lambda x: x[1], reverse=True)
    return [{"freq": f, "magnitude": m} for f, m in peaks[:n_peaks]]
