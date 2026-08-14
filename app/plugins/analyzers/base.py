"""分析插件抽象基类（接口契约，禁止随意修改）。"""

from abc import ABC, abstractmethod
from typing import Any


class AnalysisPlugin(ABC):
    name: str = "base"
    input_type: str = "raw"  # raw / feature / aggregate
    output_type: str = "json"  # json / image / series

    @abstractmethod
    async def analyze(
        self,
        channel_id: int,
        time_range: tuple,
        data: Any,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """执行分析，返回结构化结果。"""
