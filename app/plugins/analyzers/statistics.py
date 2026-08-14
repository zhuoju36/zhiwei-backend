"""基础统计插件：社区插件开发的最小示例。

只做一件事：对通道数据计算基础统计量并返回 JSON 摘要（无附件）。
作为 AnalysisPlugin v2 接口的"最短可运行"样板——新增插件时复制本文件即可。
"""

from typing import Any

import numpy as np

from app.plugins.analyzers.base import AnalysisInput, AnalysisOutput, AnalysisPlugin


class StatisticsAnalysis(AnalysisPlugin):
    name = "statistics"
    display_name = "基础统计"
    description = "计算通道数据的均值 / 峰值 / 有效值（RMS）等基础统计量"
    version = "1.0.0"
    input_channels = 1
    min_samples = 1
    params_schema = {}  # 无需参数

    async def analyze(self, data: AnalysisInput, config: dict[str, Any]) -> AnalysisOutput:
        arr = np.asarray(data.data, dtype=np.float64)
        if arr.size == 0:
            raise ValueError("data 为空")
        rms = float(np.sqrt(np.mean(arr**2)))
        return AnalysisOutput(
            summary={
                "channel_id": data.channel_ids[0],
                "num_samples": int(arr.size),
                "mean": float(arr.mean()),
                "min": float(arr.min()),
                "max": float(arr.max()),
                "std": float(arr.std()),
                "rms": rms,
            }
        )
