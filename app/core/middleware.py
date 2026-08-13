"""统一响应包装与全局异常处理。"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import BizException

logger = logging.getLogger(__name__)

# 不参与统一包装的路径前缀（文档、健康检查等）
ENVELOPE_EXCLUDE_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json")


def create_router(**kwargs) -> APIRouter:
    """创建业务路由器（统一响应包装由应用级 EnvelopeMiddleware 完成）。

    说明：FastAPI 新版对 include_router 采用延迟挂载，自定义 route_class
    在设置 response_model 的路由上不会生效，因此包装放在 ASGI 中间件层。
    """
    return APIRouter(**kwargs)


def envelope(data: Any, code: str = "OK", message: str = "success") -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": data,
        "timestamp": datetime.now(UTC).isoformat(),
    }


class EnvelopeMiddleware:
    """ASGI 中间件：将 2xx JSON 响应自动包装为统一结构。

    204/空响应/非 JSON 响应（如文件流）与文档、健康检查路径保持原样；
    错误响应由各异常处理器统一包装，此处不重复处理。
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(ENVELOPE_EXCLUDE_PREFIXES):
            await self.app(scope, receive, send)
            return

        status: int = 0
        headers: list[list[bytes]] = []
        body = bytearray()

        async def buffered_send(message: Message) -> None:
            nonlocal status, headers
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = message["headers"]
                return  # 暂缓发送，等 body 收齐后统一决定
            if message["type"] == "http.response.body":
                body.extend(message.get("body", b""))
                if message.get("more_body"):
                    return
                await self._flush(send, status, headers, bytes(body))
                return
            await send(message)

        await self.app(scope, receive, buffered_send)

    @staticmethod
    async def _flush(send: Send, status: int, headers: list[list[bytes]], body: bytes) -> None:
        content_type = next((v for k, v in headers if k.lower() == b"content-type"), b"")
        wrap = (
            200 <= status < 300 and status != 204 and body and b"application/json" in content_type
        )
        if wrap:
            body = json.dumps(envelope(json.loads(body))).encode()
            headers = [(k, v) for k, v in headers if k.lower() != b"content-length"]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BizException, biz_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


async def biz_exception_handler(request: Request, exc: BizException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope(None, code=exc.code, message=exc.message),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=envelope(None, code="VALIDATION_ERROR", message=str(exc.errors())),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未捕获异常: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=envelope(None, code="INTERNAL_ERROR", message="服务器内部错误"),
    )
