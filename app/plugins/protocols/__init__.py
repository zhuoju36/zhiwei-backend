"""协议适配器包。新增适配器模块放入本目录即可被 registry 自动发现。"""

from app.plugins.protocols.registry import AdapterRegistry

__all__ = ["AdapterRegistry"]
