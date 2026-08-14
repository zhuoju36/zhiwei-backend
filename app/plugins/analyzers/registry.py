"""分析插件自动发现与注册（双层）。

1. 内置插件：扫描 app/plugins/analyzers 包目录下所有 AnalysisPlugin 子类
2. 第三方插件：读取 Python entry_points 组 `shm_analyzers`——社区开发者把插件
   打包成独立包并声明 entry point 即可接入（pip install 后自动发现），无需改核心仓库

插件类属性 name 冲突时保留先注册的（内置优先），并记 warning。
"""

import importlib
import importlib.metadata
import logging
import pkgutil
from pathlib import Path

from app.plugins.analyzers.base import PLUGIN_API_VERSION, AnalysisPlugin

logger = logging.getLogger(__name__)

_PACKAGE = "app.plugins.analyzers"
_ENTRY_GROUP = "shm_analyzers"


class AnalyzerRegistry:
    _analyzers: dict[str, type[AnalysisPlugin]] = {}
    _discovered = False

    @classmethod
    def discover(cls) -> None:
        if cls._discovered:
            return
        cls._discover_builtin()
        cls._discover_entry_points()
        cls._discovered = True

    @classmethod
    def _discover_builtin(cls) -> None:
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
                    cls._register(obj, source=module_name)

    @classmethod
    def _discover_entry_points(cls) -> None:
        eps = importlib.metadata.entry_points()
        if hasattr(eps, "select"):
            group = eps.select(group=_ENTRY_GROUP)
        else:  # Python < 3.10
            group = eps.get(_ENTRY_GROUP, [])
        for ep in group:
            try:
                plugin_cls = ep.load()
            except Exception:
                logger.exception("加载第三方分析插件失败: %s", ep.name)
                continue
            if (
                isinstance(plugin_cls, type)
                and issubclass(plugin_cls, AnalysisPlugin)
                and plugin_cls is not AnalysisPlugin
            ):
                cls._register(plugin_cls, source=ep.name)
            else:
                logger.warning("entry point %s 不是 AnalysisPlugin 子类，忽略", ep.name)

    @classmethod
    def _register(cls, plugin_cls: type[AnalysisPlugin], source: str) -> None:
        if plugin_cls.plugin_api_version != PLUGIN_API_VERSION:
            logger.warning(
                "插件 %s (api=%s) 与框架接口版本 %s 不匹配，跳过",
                plugin_cls.name,
                plugin_cls.plugin_api_version,
                PLUGIN_API_VERSION,
            )
            return
        if plugin_cls.name in cls._analyzers:
            logger.warning(
                "插件名 %s 已注册（%s），跳过 %s",
                plugin_cls.name,
                cls._analyzers[plugin_cls.name],
                source,
            )
            return
        cls._analyzers[plugin_cls.name] = plugin_cls
        logger.info("注册分析插件: %s (%s)", plugin_cls.name, source)

    @classmethod
    def get(cls, name: str) -> type[AnalysisPlugin] | None:
        cls.discover()
        return cls._analyzers.get(name)

    @classmethod
    def names(cls) -> list[str]:
        cls.discover()
        return sorted(cls._analyzers)
