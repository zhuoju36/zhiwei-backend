"""分析路由（占位，待实现：分析任务提交 + 结果查询）。"""

from app.core.middleware import create_router

router = create_router(prefix="/analysis", tags=["分析"])
