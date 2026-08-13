"""WebSocket 连接管理：project_id -> [WebSocket]，Redis Pub/Sub 跨实例广播。"""

import asyncio
import logging
from collections import defaultdict

import redis.asyncio as aioredis
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[int, list[WebSocket]] = defaultdict(list)
        self._redis: aioredis.Redis | None = None
        self._listener_task: asyncio.Task | None = None

    async def init_redis(self, url: str) -> None:
        self._redis = aioredis.from_url(url, decode_responses=True)
        self._listener_task = asyncio.create_task(self._broadcast_listener())

    async def close(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
        if self._redis:
            await self._redis.aclose()

    async def connect(self, websocket: WebSocket, project_id: int) -> None:
        await websocket.accept()
        self.active_connections[project_id].append(websocket)

    async def disconnect(self, websocket: WebSocket, project_id: int) -> None:
        if websocket in self.active_connections.get(project_id, []):
            self.active_connections[project_id].remove(websocket)

    async def _broadcast_listener(self) -> None:
        """监听 Redis 频道，向本地 WebSocket 连接推送。"""
        assert self._redis is not None
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe("project:*")
        try:
            async for message in pubsub.listen():
                if message["type"] != "pmessage":
                    continue
                project_id = int(message["channel"].split(":")[1])
                data = message["data"]
                disconnected = []
                for ws in self.active_connections.get(project_id, []):
                    try:
                        await ws.send_text(data)
                    except Exception:
                        disconnected.append(ws)
                for ws in disconnected:
                    await self.disconnect(ws, project_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("WebSocket 广播监听异常")


manager = ConnectionManager()
