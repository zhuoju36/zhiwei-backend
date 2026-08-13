"""通知调度：dispatch_alert 并发发送到所有已启用通道。"""

import asyncio
import logging
from typing import Any

from app.notifications.base import AlertPayload
from app.notifications.email import EmailChannel
from app.notifications.webhook import WebhookChannel

logger = logging.getLogger(__name__)

# 模块级单例：避免重复创建
_webhook: WebhookChannel | None = None
_email: EmailChannel | None = None


def list_enabled_channels() -> list[Any]:
    """返回已配置、可发送的通道列表。"""
    global _webhook, _email
    if _webhook is None:
        _webhook = WebhookChannel()
    if _email is None:
        _email = EmailChannel()
    channels = []
    if _webhook.is_enabled():
        channels.append(_webhook)
    if _email.is_enabled():
        channels.append(_email)
    return channels


async def dispatch_alert(payload: AlertPayload) -> None:
    """并发发送到所有已启用通道；任一通道失败不影响其他通道。"""
    channels = list_enabled_channels()
    if not channels:
        return
    results = await asyncio.gather(*(ch.send(payload) for ch in channels), return_exceptions=True)
    for ch, r in zip(channels, results, strict=False):
        if isinstance(r, Exception):
            logger.warning("通知通道 %s 失败: %s", ch.name, r)
