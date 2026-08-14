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
from app.utils import minio_client
from app.ws.manager import manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # 插件自动发现
    AdapterRegistry.discover()
    AnalyzerRegistry.discover()
    logger.info("协议适配器: %s", AdapterRegistry.names())
    logger.info("分析插件: %s", AnalyzerRegistry.names())

    # WebSocket Redis 广播（失败不阻塞启动，实时推送降级为不可用）
    try:
        await manager.init_redis(settings.redis_url)
    except Exception:
        logger.exception("WebSocket Redis 初始化失败")

    # MinIO 客户端初始化（bucket 不存在自动创建；失败仅记日志）
    try:
        await minio_client.init()
    except Exception:
        logger.exception("MinIO 初始化失败")

    # 平台元数据单行表初始化
    try:
        from app.database import AsyncSessionLocal
        from app.services import platform_service

        async with AsyncSessionLocal() as db:
            await platform_service.ensure_singleton(db)
    except Exception:
        logger.exception("platform_settings 初始化失败")

    yield

    await manager.close()
    await minio_client.close()
    await data_service.close()
    await engine.dispose()
