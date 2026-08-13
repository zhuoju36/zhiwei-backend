"""应用生命周期管理：启动时初始化插件注册表与 WebSocket Redis，关闭时释放资源。"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import engine
from app.plugins.analyzers.registry import AnalyzerRegistry
from app.plugins.protocols.registry import AdapterRegistry
from app.services import data_service
from app.ws.manager import manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # 插件自动发现
    AdapterRegistry.discover()
    AnalyzerRegistry.discover()
    logger.info("协议适配器: %s", AdapterRegistry.names())

    # WebSocket Redis 广播（失败不阻塞启动，实时推送降级为不可用）
    try:
        await manager.init_redis(settings.redis_url)
    except Exception:
        logger.exception("WebSocket Redis 初始化失败")

    yield

    await manager.close()
    await data_service.close()
    await engine.dispose()
