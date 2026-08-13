"""通知子系统：通道抽象 + 内置通道实现。

通道实现：
- WebhookChannel（httpx 异步 POST）
- EmailChannel（smtplib in executor，HTML 模板）

调度入口在 `app.services.notification_service.dispatch_alert`。
"""

from app.notifications.base import AlertPayload, NotificationChannel
from app.notifications.email import EmailChannel
from app.notifications.webhook import WebhookChannel

__all__ = [
    "AlertPayload",
    "EmailChannel",
    "NotificationChannel",
    "WebhookChannel",
]
