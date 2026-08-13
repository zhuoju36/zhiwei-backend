"""Email 通知通道：smtplib（线程池异步化），HTML 模板。"""

# flake8: noqa: E501  (HTML 模板内行长)

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from app.config import settings
from app.notifications.base import AlertPayload

logger = logging.getLogger(__name__)


def _build_html(payload: dict[str, Any]) -> str:
    level = payload.get("level", "")
    color = {"info": "#0d6efd", "warning": "#fd7e14", "danger": "#dc3545"}.get(level, "#6c757d")
    return f"""
    <html><body style="font-family: -apple-system, sans-serif; color: #222;">
      <h2 style="color: {color}; margin: 0 0 16px;">[SHM] 告警 {level.upper()}</h2>
      <table style="border-collapse: collapse; font-size: 14px;">
        <tr>
          <td style="padding: 4px 12px; color: #666;">告警 ID</td>
          <td style="padding: 4px 12px;">#{payload.get("alert_id")}</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; color: #666;">项目</td>
          <td style="padding: 4px 12px;">{payload.get("project_id")}</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; color: #666;">设备 / 测点</td>
          <td style="padding: 4px 12px;">
            {payload.get("device_code")} / {payload.get("point_code")}
          </td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; color: #666;">当前值</td>
          <td style="padding: 4px 12px; font-weight: bold; color: {color};">
            {payload.get("value")}
          </td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; color: #666;">阈值</td>
          <td style="padding: 4px 12px;">{payload.get("threshold")}</td>
        </tr>
        <tr>
          <td style="padding: 4px 12px; color: #666;">开始时间</td>
          <td style="padding: 4px 12px;">{payload.get("started_at")}</td>
        </tr>
        {f'<tr><td style="padding: 4px 12px; color: #666;">说明</td><td style="padding: 4px 12px;">{payload.get("message")}</td></tr>' if payload.get("message") else ""}
      </table>
    </body></html>
    """.strip()


def _send_smtp_sync(
    host: str,
    port: int,
    user: str,
    password: str,
    use_tls: bool,
    from_addr: str,
    to_addrs: list[str],
    subject: str,
    html: str,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(html, "html"))

    if use_tls:
        client = smtplib.SMTP_SSL(host, port, timeout=15)
    else:
        client = smtplib.SMTP(host, port, timeout=15)
    try:
        if not use_tls:
            client.starttls()
        if user:
            client.login(user, password)
        client.sendmail(from_addr, to_addrs, msg.as_string())
    finally:
        client.quit()


class EmailChannel:
    name = "email"

    def __init__(self) -> None:
        self._host: str = settings.smtp_host
        self._port: int = settings.smtp_port
        self._user: str = settings.smtp_user
        self._password: str = settings.smtp_password
        self._use_tls: bool = settings.smtp_use_tls
        self._from: str = settings.smtp_from or settings.smtp_user
        self._to: list[str] = [
            addr.strip() for addr in settings.alert_email_to.split(",") if addr.strip()
        ]

    def is_enabled(self) -> bool:
        return bool(self._host) and bool(self._to) and bool(self._from)

    async def send(self, payload: AlertPayload) -> None:
        if not self.is_enabled():
            return
        level = payload.get("level", "info")
        subject = f"[SHM] 告警 {level.upper()} - {payload.get('point_code', '')}"
        html = _build_html(dict(payload))
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                _send_smtp_sync,
                self._host,
                self._port,
                self._user,
                self._password,
                self._use_tls,
                self._from,
                self._to,
                subject,
                html,
            )
        except Exception:
            logger.exception("Email 发送失败")
