"""测点管理路由（占位，待实现：测点 CRUD + 三维坐标绑定）。"""

from app.core.middleware import create_router

router = create_router(prefix="/points", tags=["测点"])
