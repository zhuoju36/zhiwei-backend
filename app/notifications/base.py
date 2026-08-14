"""通知通道抽象。"""

from __future__ import annotations

from typing import Protocol, TypedDict


class AlertPayload(TypedDict, total=False):
    """告警通知的统一负载。"""

    alert_id: int
    point_id: int
    subitem_id: int
    level: str
    value: float
    threshold: float
    message: str | None
    started_at: str  # ISO 8601
    device_code: str
    point_code: str


class NotificationChannel(Protocol):
    """通知通道抽象。send() 失败仅记日志；调用方用 gather 收集结果。"""

    name: str

    async def send(self, payload: AlertPayload) -> None: ...
