"""FastAPI 应用工厂。"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.middleware import EnvelopeMiddleware, register_exception_handlers
from app.lifespan import lifespan
from app.routers import api_router
from app.ws.endpoints import router as ws_router

logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    app = FastAPI(title="SHM 平台后端", version="0.1.0", lifespan=lifespan)

    # 开发环境 CORS；生产环境禁止 allow_origins=["*"]，由部署配置收敛域名
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # 统一响应包装（最后添加，处于中间件链最内层）
    app.add_middleware(EnvelopeMiddleware)

    register_exception_handlers(app)

    app.include_router(api_router)
    app.include_router(ws_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
