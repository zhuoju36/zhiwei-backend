"""分析插件注册表单测：双层发现（内置目录 + entry_points）、版本守卫。"""

from app.plugins.analyzers.base import AnalysisInput, AnalysisOutput, AnalysisPlugin
from app.plugins.analyzers.registry import AnalyzerRegistry


class _FakePlugin(AnalysisPlugin):
    """模拟社区第三方插件。"""

    name = "community_plugin"
    display_name = "社区插件"
    description = "测试"
    version = "1.0.0"

    async def analyze(self, data: AnalysisInput, config: dict) -> AnalysisOutput:
        return AnalysisOutput(summary={})


class _FakeEntryPoint:
    def __init__(self, name: str, loader):
        self.name = name
        self._loader = loader

    def load(self):
        return self._loader


class _FakeEntryPoints(list):
    def select(self, group: str):
        assert group == "shm_analyzers"
        return self


def _reset_registry() -> None:
    AnalyzerRegistry._analyzers = {}
    AnalyzerRegistry._discovered = False


def test_entry_points_discovery(monkeypatch) -> None:
    """第三方插件经 entry_points 组 shm_analyzers 自动注册，内置插件仍保留。"""
    import importlib.metadata

    fake = _FakeEntryPoints([_FakeEntryPoint("shm-community-plugin", _FakePlugin)])
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda: fake)

    _reset_registry()
    try:
        AnalyzerRegistry.discover()
        names = AnalyzerRegistry.names()
        assert "community_plugin" in names
        assert "fft" in names  # 内置目录扫描不受影响
        assert "statistics" in names
    finally:
        _reset_registry()
        AnalyzerRegistry.discover()  # 恢复：只注册内置插件


def test_api_version_mismatch_skipped(monkeypatch) -> None:
    """plugin_api_version 与框架不一致的插件被拒绝加载。"""

    class _OldPlugin(AnalysisPlugin):
        name = "old_plugin"
        plugin_api_version = "0"

        async def analyze(self, data: AnalysisInput, config: dict) -> AnalysisOutput:
            return AnalysisOutput(summary={})

    import importlib.metadata

    fake = _FakeEntryPoints([_FakeEntryPoint("shm-old-plugin", _OldPlugin)])
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda: fake)

    _reset_registry()
    try:
        AnalyzerRegistry.discover()
        assert "old_plugin" not in AnalyzerRegistry.names()
    finally:
        _reset_registry()
        AnalyzerRegistry.discover()


def test_duplicate_name_keeps_first(monkeypatch) -> None:
    """同名插件保留先注册的（内置优先）。"""

    class _DupPlugin(AnalysisPlugin):
        name = "fft"  # 与内置 fft 重名
        plugin_api_version = "1"

        async def analyze(self, data: AnalysisInput, config: dict) -> AnalysisOutput:
            return AnalysisOutput(summary={})

    import importlib.metadata

    fake = _FakeEntryPoints([_FakeEntryPoint("shm-dup-fft", _DupPlugin)])
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda: fake)

    _reset_registry()
    try:
        AnalyzerRegistry.discover()
        # 内置 fft 保留
        assert AnalyzerRegistry.get("fft").__module__ == "app.plugins.analyzers.fft_analysis"
    finally:
        _reset_registry()
        AnalyzerRegistry.discover()
