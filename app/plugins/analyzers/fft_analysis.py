"""FFT 频谱分析插件。

签名遵循 AnalysisPlugin.analyze(point_id, time_range, data, config) -> dict。

输入：data 为 numpy.ndarray（一维等间隔采样），config 至少含 sampling_rate。
返回：JSON 友好的 dict（含 dominant_freq / dominant_magnitude / num_samples / sampling_rate），
     完整频率/幅值数组以 NumPy .npz 二进制存 MinIO（由调用方负责上传）。
"""

from typing import Any

import numpy as np
from scipy.fft import rfft, rfftfreq

from app.plugins.analyzers.base import AnalysisPlugin


class FftAnalysis(AnalysisPlugin):
    name = "fft"
    input_type = "raw"
    output_type = "json"

    async def analyze(
        self,
        point_id: int,
        time_range: tuple,
        data: np.ndarray,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        if "sampling_rate" not in config:
            raise ValueError("config 必须包含 sampling_rate")
        sr = float(config["sampling_rate"])
        if sr <= 0:
            raise ValueError("sampling_rate 必须 > 0")
        if data is None or len(data) < 2:
            raise ValueError("data 长度不足以做 FFT")

        data = np.asarray(data, dtype=np.float64)
        n = data.size
        # 去直流，避免 0Hz 占主导
        data = data - data.mean()
        spectrum = np.abs(rfft(data)) / n
        freqs = rfftfreq(n, d=1.0 / sr)

        idx = int(np.argmax(spectrum))
        dominant_freq = float(freqs[idx])
        dominant_magnitude = float(spectrum[idx])

        # 警告：样本数过少
        warnings: list[str] = []
        if n < 64:
            warnings.append("样本数过少（<64），频谱分辨率低")

        # 非等间隔采样的探测：data 相邻差值不均暗示了异常（仅基础检查）
        # 真实非等间隔需结合 time_range；此处省略（v0.5+ 完善）

        return {
            "point_id": point_id,
            "sampling_rate": sr,
            "num_samples": n,
            "dominant_freq": dominant_freq,
            "dominant_magnitude": dominant_magnitude,
            "nyquist_freq": sr / 2.0,
            "freq_resolution": sr / n,
            "top_peaks": _top_peaks(freqs, spectrum, n_peaks=3),
            "warnings": warnings,
            # 内部：调用方（Celery task）会取出频谱/幅值并上传 .npz
            "_internal_frequencies": freqs.tolist(),
            "_internal_magnitudes": spectrum.tolist(),
        }


def _top_peaks(freqs: np.ndarray, spectrum: np.ndarray, n_peaks: int = 3) -> list[dict[str, float]]:
    """返回频谱中前 n_peaks 个峰（局部最大值，按幅值降序）。"""
    peaks: list[tuple[float, float]] = []
    for i in range(1, len(spectrum) - 1):
        if spectrum[i] > spectrum[i - 1] and spectrum[i] > spectrum[i + 1]:
            peaks.append((float(freqs[i]), float(spectrum[i])))
    peaks.sort(key=lambda x: x[1], reverse=True)
    return [{"freq": f, "magnitude": m} for f, m in peaks[:n_peaks]]
