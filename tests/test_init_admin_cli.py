"""scripts/init_admin.py CLI 测试。"""

import json
from unittest.mock import patch

import pytest


def test_cli_creates_admin_with_env(
    capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """env 模式：ADMIN_USERNAME/EMAIL/PASSWORD → 调 init-admin 端点。"""
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@x.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin12345")

    class _FakeResp:
        status_code = 201

        def json(self) -> dict:
            return {
                "code": "OK",
                "data": {
                    "admin_id": 1,
                    "username": "admin",
                    "access_token": "fake-access-token-abc",
                    "refresh_token": "fake-refresh-token-xyz",
                    "token_type": "bearer",
                },
            }

    def fake_get(url: str, timeout: int = 5):
        r = _FakeResp()
        r.status_code = 200
        r.raise_for_status = lambda: None  # type: ignore[attr-defined]

        def json2() -> dict:
            return {"code": "OK", "data": {"initialized": False, "password_requirements": {}}}

        r.json = json2  # type: ignore[assignment]
        return r

    def fake_post(url: str, json: dict, timeout: int = 10):
        r = _FakeResp()
        r.raise_for_status = lambda: None  # type: ignore[attr-defined]
        captured["url"] = url
        captured["payload"] = json
        return r

    captured: dict = {}
    with (
        patch("scripts.init_admin.httpx.get", side_effect=fake_get),
        patch("scripts.init_admin.httpx.post", side_effect=fake_post),
    ):
        from scripts.init_admin import main

        rc = main(argv=["--base-url", "http://test"])

    assert rc == 0
    assert captured["url"].endswith("/api/v1/setup/init-admin")
    assert captured["payload"] == {
        "username": "admin",
        "email": "admin@x.com",
        "password": "admin12345",
    }
    out = capsys.readouterr().out
    assert "admin 已创建" in out


def test_cli_idempotent_when_already_initialized(
    capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """已初始化时 CLI 返回 0 + 提示消息。"""
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin12345")
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)

    class _StatusResp:
        status_code = 200

        def json(self) -> dict:
            return {"code": "OK", "data": {"initialized": True, "password_requirements": {}}}

        def raise_for_status(self) -> None:
            return None

    with patch("scripts.init_admin.httpx.get", return_value=_StatusResp()):
        from scripts.init_admin import main

        rc = main(argv=["--base-url", "http://test"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "已初始化" in out


def test_cli_returns_1_on_password_validation_error(
    capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "weak")

    class _StatusResp:
        status_code = 200

        def json(self) -> dict:
            return {"code": "OK", "data": {"initialized": False, "password_requirements": {}}}

        def raise_for_status(self) -> None:
            return None

    class _PostResp:
        status_code = 422

        def json(self) -> dict:
            return {
                "code": "WEAK_PASSWORD",
                "message": "密码至少 8 个字符",
                "data": None,
            }

        def raise_for_status(self) -> None:
            return None

        @property
        def text(self) -> str:
            return json.dumps(self.json())

    with (
        patch("scripts.init_admin.httpx.get", return_value=_StatusResp()),
        patch("scripts.init_admin.httpx.post", return_value=_PostResp()),
    ):
        from scripts.init_admin import main

        rc = main(argv=["--base-url", "http://test"])

    assert rc == 1
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "WEAK_PASSWORD" in out or "弱密码" in out or "密码" in out


def test_cli_returns_2_on_network_error(
    capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    with patch(
        "scripts.init_admin.httpx.get",
        side_effect=httpx.ConnectError("refused"),
    ):
        from scripts.init_admin import main

        rc = main(argv=["--base-url", "http://test"])

    assert rc == 2
