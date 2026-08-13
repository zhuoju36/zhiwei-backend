"""协议适配器抽象基类（接口契约，绝对禁止修改）。

边缘网关与云端后端共用此接口。新增协议 = 新增一个模块继承 ProtocolAdapter。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class RawReading:
    device_code: str  # 设备唯一编码，对应 devices.device_code
    point_code: str  # 测点编码，对应 points.point_code
    timestamp: datetime  # 采样时间戳（UTC）
    value: float
    unit: str = ""
    quality: str = "good"  # good | bad | uncertain
    raw_bytes: bytes = field(repr=False, default=b"")
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProtocolConfig:
    host: str = ""
    port: int = 0
    sample_interval_ms: int = 1000
    timeout_ms: int = 5000
    register_map: dict[str, Any] = field(default_factory=dict)
    auth: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


class ProtocolAdapter(ABC):
    """协议适配器抽象基类，所有具体适配器必须继承并实现。"""

    name: str = "base"
    version: str = "1.0.0"
    supports_batch: bool = False  # 是否支持批量读取

    def __init__(self, config: ProtocolConfig):
        self.config = config
        self._connected = False
        self._last_error: str = ""

    @abstractmethod
    async def connect(self) -> None:
        """建立异步连接，失败抛出 ConnectionError。"""

    @abstractmethod
    async def read_batch(self) -> list[RawReading]:
        """读取一轮数据，返回 RawReading 列表。

        必须在 sample_interval_ms 内完成，否则丢弃或标记 quality='uncertain'。
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """优雅关闭连接，释放资源。"""

    async def health_check(self) -> dict[str, Any]:
        return {"connected": self._connected, "last_error": self._last_error}

    def _now(self) -> datetime:
        return datetime.now(UTC)
