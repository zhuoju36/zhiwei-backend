"""告警路由（占位，待实现：告警查询 + 确认）。"""

from app.core.middleware import create_router

router = create_router(prefix="/alerts", tags=["告警"])
