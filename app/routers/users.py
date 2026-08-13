"""用户管理路由（占位，待实现：用户 CRUD，仅 admin）。"""

from app.core.middleware import create_router

router = create_router(prefix="/users", tags=["用户"])
