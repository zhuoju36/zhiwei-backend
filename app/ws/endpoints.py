"""WebSocket 端点：/ws/data?token=<access_token>

握手：token → 加载 user → accept → 等待订阅指令。
订阅：cmd:subscribe 携带 subitem_id，校验用户对该项目有权限（4403 拒绝）。
"""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.database import AsyncSessionLocal
from app.dependencies import check_subitem_access
from app.models.user import User
from app.ws.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/data")
async def ws_data(websocket: WebSocket, token: str = "") -> None:
    # 1. token 校验 + 加载 user
    try:
        payload = decode_token(token, expected_type="access")
        user_id = int(payload["sub"])
    except Exception:
        await websocket.close(code=4401)
        return

    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if user is None or not user.is_active:
            await websocket.close(code=4401)
            return

    # 2. 握手（前端反馈：之前从未 accept 导致 500）
    await websocket.accept()

    subscribed_project: int | None = None
    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            if message.get("type") == "cmd:subscribe":
                subitem_id = int(message["subitem_id"])
                # 3. 项目权限校验
                async with AsyncSessionLocal() as db:
                    try:
                        await check_subitem_access(db, user, subitem_id)
                    except Exception as exc:
                        logger.info(
                            "WS 订阅被拒绝: user=%s project=%s reason=%s",
                            user.username,
                            subitem_id,
                            exc,
                        )
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "cmd:error",
                                    "code": "FORBIDDEN",
                                    "message": "无权订阅该项目",
                                    "subitem_id": subitem_id,
                                }
                            )
                        )
                        continue

                if subscribed_project is None:
                    await manager.connect(websocket, subitem_id)
                    subscribed_project = subitem_id
                    await websocket.send_text(
                        json.dumps({"type": "cmd:subscribed", "subitem_id": subitem_id})
                    )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket 处理异常")
    finally:
        if subscribed_project is not None:
            await manager.disconnect(websocket, subscribed_project)
