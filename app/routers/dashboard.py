"""大屏聚合数据路由（占位，待实现：最新值、统计卡片）。"""

from app.core.middleware import create_router

router = create_router(prefix="/dashboard", tags=["大屏"])
