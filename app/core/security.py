"""JWT 编解码与密码哈希（bcrypt 同步计算，走线程池避免阻塞事件循环）。"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config import settings
from app.core.exceptions import AuthException

ALGORITHM = "HS256"


def _create_token(
    subject: str, token_type: str, expires: timedelta, extra: dict[str, Any] | None = None
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires,
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: int, role: str) -> str:
    return _create_token(
        str(user_id),
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        extra={"role": role},
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        str(user_id), "refresh", timedelta(days=settings.refresh_token_expire_days)
    )


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthException(f"令牌无效或已过期: {exc}") from exc
    if payload.get("type") != expected_type:
        raise AuthException("令牌类型错误")
    return payload


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


async def hash_password(password: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _hash_password, password)


async def verify_password(password: str, hashed: str) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _verify_password, password, hashed)
