"""分析插件抽象基类（v2 接口契约）。

设计原则（面向社区开发者）：
- 插件 = 纯计算单元：输入数组 + 参数，输出摘要/附件。不接触数据库、IO、实时流
- 元信息自描述：注册表与前端用类属性渲染"可用分析"列表与参数表单
- 数据声明式请求：插件用 input_channels / min_samples 声明需求，框架负责拉取
- 版本守卫：plugin_api_version 不匹配时注册表拒绝加载，防止接口演进静默破坏

写入/读取时序数据、任务编排由 app/tasks/analysis_tasks.py 完成；
插件作者只需实现 analyze()。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

PLUGIN_API_VERSION = "1"  # 当前框架实现的接口版本


@dataclass
class AnalysisInput:
    """框架构造、插件只读的输入。

    - input_channels=1 的插件：data 为 np.ndarray（一维等间隔采样）
    - input_channels=N 的插件：data 为 dict[channel_id(int), np.ndarray]
    """

    channel_ids: list[int]
    time_range: tuple[str, str]
    sampling_rate: float
    data: Any = field(default_factory=dict)  # np.ndarray | dict[int, np.ndarray]


@dataclass
class AnalysisOutput:
    """插件返回的执行结果。

    - summary：JSON 摘要，存入 analysis_jobs.result_summary
    - artifact：可选二进制附件（NPZ / PNG / CSV...），存入 MinIO
    """

    summary: dict[str, Any]
    artifact: bytes | None = None
    artifact_name: str = "result"
    artifact_type: str = "application/octet-stream"


class AnalysisPlugin(ABC):
    # —— 自描述元信息 ——
    name: str = "base"  # 唯一标识（与 /analysis/jobs 的 plugin 字段对应）
    display_name: str = ""  # 展示名（前端列表）
    description: str = ""  # 一句话说明
    version: str = "1.0.0"
    plugin_api_version: str = PLUGIN_API_VERSION
    input_channels: int = 1  # 需要参与分析的通道数（1 或 N）
    min_samples: int = 2  # 每个通道最少样本数（框架前置校验）
    params_schema: dict[str, Any] = {}  # JSON Schema，前端表单

    @abstractmethod
    async def analyze(self, data: AnalysisInput, config: dict[str, Any]) -> AnalysisOutput:
        """执行分析，返回结构化结果。

        config 为任务提交时的 params（插件自行校验，非法参数抛 ValueError，
        框架捕获后标记任务 failed 并记录错误）。
        """
        raise NotImplementedError
