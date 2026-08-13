"""分析插件自动发现与注册（与协议适配器同一模式）。"""

import importlib
import logging
import pkgutil
from pathlib import Path

from app.plugins.analyzers.base import AnalysisPlugin

logger = logging.getLogger(__name__)

_PACKAGE = "app.plugins.analyzers"


class AnalyzerRegistry:
    _analyzers: dict[str, type[AnalysisPlugin]] = {}
    _discovered = False

    @classmethod
    def discover(cls) -> None:
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
                    and issubclass(obj, AnalysisPlugin)
                    and obj is not AnalysisPlugin
                    and obj.name != "base"
                ):
                    cls._analyzers[obj.name] = obj
                    logger.info("注册分析插件: %s (%s)", obj.name, module_name)
        cls._discovered = True

    @classmethod
    def get(cls, name: str) -> type[AnalysisPlugin] | None:
        cls.discover()
        return cls._analyzers.get(name)

    @classmethod
    def names(cls) -> list[str]:
        cls.discover()
        return sorted(cls._analyzers)
