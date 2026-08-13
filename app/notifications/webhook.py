"""Webhook 通知通道：httpx 异步 POST JSON。"""

import json
import logging

import httpx

from app.config import settings
from app.notifications.base import AlertPayload

logger = logging.getLogger(__name__)


class WebhookChannel:
    name = "webhook"

    def __init__(self) -> None:
        self._url: str = settings.webhook_url
        self._headers: dict[str, str] = {}
        if settings.webhook_headers.strip():
            try:
                parsed = json.loads(settings.webhook_headers)
                if isinstance(parsed, dict):
                    self._headers = {str(k): str(v) for k, v in parsed.items()}
            except json.JSONDecodeError:
                logger.warning("WEBHOOK_HEADERS 不是合法 JSON，已忽略")
        self._timeout: float = settings.webhook_timeout_seconds

    def is_enabled(self) -> bool:
        return bool(self._url)

    async def send(self, payload: AlertPayload) -> None:
        if not self.is_enabled():
            return
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.post(self._url, json=payload, headers=self._headers)
                if resp.status_code >= 400:
                    logger.warning(
                        "Webhook 返回非 2xx: %s body=%s", resp.status_code, resp.text[:200]
                    )
            except Exception:
                logger.exception("Webhook 发送失败")
