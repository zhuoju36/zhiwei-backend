"""通知通道与服务测试。"""

import asyncio
from unittest.mock import MagicMock, patch

import httpx

from app.notifications.base import AlertPayload
from app.notifications.email import EmailChannel
from app.notifications.webhook import WebhookChannel
from app.services import notification_service

SAMPLE: AlertPayload = {
    "alert_id": 1,
    "channel_id": 1,
    "subitem_id": 1,
    "level": "warning",
    "value": 0.99,
    "threshold": 0.5,
    "message": "超阈值",
    "started_at": "2026-08-13T12:00:00+00:00",
    "device_code": "GW-001",
    "channel_code": "ACC-X",
}


def test_webhook_disabled_when_url_empty() -> None:
    with patch("app.notifications.webhook.settings") as s:
        s.webhook_url = ""
        s.webhook_headers = ""
        s.webhook_timeout_seconds = 10.0
        ch = WebhookChannel()
        assert ch.is_enabled() is False


def test_webhook_enabled_with_url() -> None:
    with patch("app.notifications.webhook.settings") as s:
        s.webhook_url = "http://example.com/hook"
        s.webhook_headers = ""
        s.webhook_timeout_seconds = 10.0
        ch = WebhookChannel()
        assert ch.is_enabled() is True


def test_webhook_post_body_and_headers() -> None:
    """httpx MockTransport 验证 POST body 与 headers。"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    with patch("app.notifications.webhook.settings") as s:
        s.webhook_url = "http://hook.local/notify"
        s.webhook_headers = '{"X-Token":"abc"}'
        s.webhook_timeout_seconds = 5.0
        ch = WebhookChannel()

        # 用 httpx 的真实 AsyncClient（绕过 patch）；用 transport 拦截
        real_async_client = httpx.AsyncClient

        class _FakeFactory:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return real_async_client(transport=transport)

            async def __aexit__(self, *args):
                return None

            async def post(self, url, json, headers):
                async with real_async_client(transport=transport) as c:
                    return await c.post(url, json=json, headers=headers)

        with patch("app.notifications.webhook.httpx.AsyncClient", _FakeFactory):
            asyncio.run(ch.send(SAMPLE))

    assert captured["method"] == "POST"
    assert captured["url"] == "http://hook.local/notify"
    assert "x-token" in captured["headers"]
    assert captured["headers"]["x-token"] == "abc"
    import json

    body = json.loads(captured["body"])
    assert body["alert_id"] == 1
    assert body["level"] == "warning"
    assert body["value"] == 0.99


def test_email_disabled_without_config() -> None:
    with patch("app.notifications.email.settings") as s:
        s.smtp_host = ""
        s.smtp_port = 587
        s.smtp_user = ""
        s.smtp_password = ""
        s.smtp_use_tls = True
        s.smtp_from = ""
        s.alert_email_to = ""
        ch = EmailChannel()
        assert ch.is_enabled() is False


def test_email_enabled_with_full_config() -> None:
    with patch("app.notifications.email.settings") as s:
        s.smtp_host = "smtp.example.com"
        s.smtp_port = 587
        s.smtp_user = "u"
        s.smtp_password = "p"
        s.smtp_use_tls = True
        s.smtp_from = "alert@x"
        s.alert_email_to = "ops@x,a@x"
        ch = EmailChannel()
        assert ch.is_enabled() is True


def test_email_send_uses_executor() -> None:
    """验证 EmailChannel.send 把 smtplib 调用交给 executor。"""
    with patch("app.notifications.email.settings") as s:
        s.smtp_host = "smtp.example.com"
        s.smtp_port = 587
        s.smtp_user = "u"
        s.smtp_password = "p"
        s.smtp_use_tls = True
        s.smtp_from = "alert@x"
        s.alert_email_to = "ops@x"
        ch = EmailChannel()
        with patch("app.notifications.email._send_smtp_sync") as mock_send:
            asyncio.run(ch.send(SAMPLE))
            assert mock_send.called
            args, _ = mock_send.call_args
            # args = (host, port, user, password, use_tls, from_addr, to_addrs, subject, html)
            assert args[0] == "smtp.example.com"
            assert args[1] == 587
            assert args[2] == "u"
            assert args[5] == "alert@x"
            assert args[6] == ["ops@x"]
            assert "[SHM] 告警 WARNING" in args[7]
            assert "GW-001" in args[8]


async def test_dispatch_with_no_channels_is_noop() -> None:
    """未配置任何通道时 dispatch 不报错。"""
    notification_service._webhook = None
    notification_service._email = None
    with patch("app.notifications.webhook.settings") as ws:
        ws.webhook_url = ""
        ws.webhook_headers = ""
        ws.webhook_timeout_seconds = 10.0
    with patch("app.notifications.email.settings") as es:
        es.smtp_host = ""
        es.smtp_port = 587
        es.smtp_user = ""
        es.smtp_password = ""
        es.smtp_use_tls = True
        es.smtp_from = ""
        es.alert_email_to = ""
    await notification_service.dispatch_alert(SAMPLE)


async def test_dispatch_one_channel_failure_does_not_block_others() -> None:
    """一通道失败不影响其他通道。"""
    bad_channel = MagicMock()
    bad_channel.name = "bad"
    bad_channel.is_enabled.return_value = True

    async def raise_send(_payload):
        raise RuntimeError("simulated failure")

    bad_channel.send = raise_send

    good_channel = MagicMock()
    good_channel.name = "good"
    good_channel.is_enabled.return_value = True
    good_called = []

    async def good_send(payload):
        good_called.append(payload)

    good_channel.send = good_send

    with patch.object(
        notification_service,
        "list_enabled_channels",
        return_value=[bad_channel, good_channel],
    ):
        await notification_service.dispatch_alert(SAMPLE)

    assert len(good_called) == 1


def test_build_email_html_contains_fields() -> None:
    from app.notifications.email import _build_html

    html = _build_html(dict(SAMPLE))
    assert "WARNING" in html
    assert "GW-001" in html
    assert "ACC-X" in html
    assert "0.99" in html
    assert "0.5" in html
    assert "超阈值" in html
    assert "#fd7e14" in html  # warning 橙色
