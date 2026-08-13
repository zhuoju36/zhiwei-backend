"""协议适配器元数据路由：列出已注册的协议，供前端设备配置页动态生成表单。"""

from app.core.middleware import create_router
from app.plugins.protocols.registry import AdapterRegistry
from app.schemas.protocol import CONFIG_SCHEMAS, ProtocolMeta

router = create_router(prefix="/protocols", tags=["协议"])


@router.get("", response_model=list[ProtocolMeta])
async def list_protocols() -> list[ProtocolMeta]:
    """列出所有已注册的协议适配器元数据。"""
    result = []
    for name in AdapterRegistry.names():
        cls = AdapterRegistry.get(name)
        if cls is None:
            continue
        result.append(
            ProtocolMeta(
                name=name,
                version=cls.version,
                supports_batch=cls.supports_batch,
                config_schema=CONFIG_SCHEMAS.get(name, {}),
            )
        )
    return result
