"""JWT 与密码哈希单元测试。"""

import pytest

from app.core.exceptions import AuthException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_access_token_roundtrip() -> None:
    token = create_access_token(42, "admin")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_refresh_token_type_isolated() -> None:
    refresh = create_refresh_token(42)
    # refresh 令牌不能当 access 用
    with pytest.raises(AuthException):
        decode_token(refresh, expected_type="access")
    payload = decode_token(refresh, expected_type="refresh")
    assert payload["sub"] == "42"


def test_decode_invalid_token() -> None:
    with pytest.raises(AuthException):
        decode_token("not-a-token")


async def test_password_hash_roundtrip() -> None:
    hashed = await hash_password("secret-123")
    assert hashed != "secret-123"
    assert await verify_password("secret-123", hashed)
    assert not await verify_password("wrong", hashed)
