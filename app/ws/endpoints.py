"""WebSocket 端点：/ws/data?token=<access_token>

客户端连接后发送订阅指令：
    {"type": "cmd:subscribe", "project_id": 1}
"""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.ws.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/data")
async def ws_data(websocket: WebSocket, token: str = "") -> None:
    # WebSocket 无法用 Depends 注入，手动校验 JWT
    try:
        decode_token(token, expected_type="access")
    except Exception:
        await websocket.close(code=4401)
        return

    # 先完成握手，再进入接收循环（前端反馈：之前从未 accept 导致 500）
    await websocket.accept()

    subscribed_project: int | None = None
    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            if message.get("type") == "cmd:subscribe":
                project_id = int(message["project_id"])
                # TODO: 校验当前用户对该项目的权限后再放行
                if subscribed_project is None:
                    await manager.connect(websocket, project_id)
                    subscribed_project = project_id
                    await websocket.send_text(
                        json.dumps({"type": "cmd:subscribed", "project_id": project_id})
                    )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket 处理异常")
    finally:
        if subscribed_project is not None:
            await manager.disconnect(websocket, subscribed_project)
