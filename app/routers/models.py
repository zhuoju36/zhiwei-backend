"""3D 模型路由（占位，待实现：模型文件上传/转换状态查询）。"""

from app.core.middleware import create_router

router = create_router(prefix="/models", tags=["模型"])
