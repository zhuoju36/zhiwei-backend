"""统一注册路由，前缀 /api/v1。

统一响应包装由 app.core.middleware.create_router 在各子路由器上生效
（FastAPI 新版 include_router 延迟挂载，父路由器的 route_class 不会传播）。
"""

from fastapi import APIRouter

from app.routers import (
    alerts,
    analysis,
    auth,
    dashboard,
    data,
    devices,
    models,
    platform,
    points,
    projects,
    protocols,
    setup,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(setup.router)
api_router.include_router(platform.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(projects.router)
api_router.include_router(protocols.router)
api_router.include_router(devices.router)
api_router.include_router(points.router)
api_router.include_router(data.router)
api_router.include_router(alerts.router)
api_router.include_router(analysis.router)
api_router.include_router(dashboard.router)
api_router.include_router(models.router)
