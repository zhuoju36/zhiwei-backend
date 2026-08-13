"""协议适配器自动发现与注册。

扫描 app.plugins.protocols 包下所有 *_adapter.py 模块，
将其中的 ProtocolAdapter 子类按类属性 name 注册，无需手动登记。
"""

import importlib
import logging
import pkgutil
from pathlib import Path

from app.plugins.protocols.base import ProtocolAdapter

logger = logging.getLogger(__name__)

_PACKAGE = "app.plugins.protocols"


class AdapterRegistry:
    _adapters: dict[str, type[ProtocolAdapter]] = {}
    _discovered = False

    @classmethod
    def discover(cls) -> None:
        """自动扫描协议包目录，注册所有适配器（幂等）。"""
        if cls._discovered:
            return
        package_path = str(Path(__file__).parent)
        for _, module_name, ispkg in pkgutil.iter_modules([package_path]):
            if ispkg or module_name in ("base", "registry"):
                continue
            module = importlib.import_module(f"{_PACKAGE}.{module_name}")
            for attr in dir(module):
                obj = getattr(module, attr)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, ProtocolAdapter)
                    and obj is not ProtocolAdapter
                    and obj.name != "base"
                ):
                    cls._adapters[obj.name] = obj
                    logger.info("注册协议适配器: %s (%s)", obj.name, module_name)
        cls._discovered = True

    @classmethod
    def get(cls, name: str) -> type[ProtocolAdapter] | None:
        cls.discover()
        return cls._adapters.get(name)

    @classmethod
    def names(cls) -> list[str]:
        cls.discover()
        return sorted(cls._adapters)
