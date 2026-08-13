"""首次部署引导 service：仅在 users 表为空时创建 admin。"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models.user import User
from app.schemas.user import UserCreate

logger = logging.getLogger(__name__)


# 密码策略：≥8 字符 + 同时含字母和数字
PASSWORD_MIN_LENGTH = 8
PASSWORD_REQUIREMENTS: dict[str, Any] = {
    "min_length": PASSWORD_MIN_LENGTH,
    "require_letter": True,
    "require_digit": True,
    "description": "密码至少 8 个字符，且同时包含字母和数字",
}


def validate_password_strength(password: str) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise BizException(
            code="WEAK_PASSWORD",
            message=f"密码至少 {PASSWORD_MIN_LENGTH} 个字符",
            status_code=422,
        )
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise BizException(
            code="WEAK_PASSWORD",
            message="密码必须同时包含字母和数字",
            status_code=422,
        )


async def is_initialized(db: AsyncSession) -> bool:
    """返回 True 表示已经存在至少一个用户（系统已初始化）。"""
    count = (await db.execute(select(func.count(User.id)))).scalar_one()
    return count > 0


async def init_first_admin(
    db: AsyncSession, username: str, email: str, password: str
) -> dict[str, Any]:
    """创建第一个 admin 用户。守卫：仅当 users 表为空时可调用。

    返回 {"user": User, "access_token": str, "refresh_token": str}
    """
    if await is_initialized(db):
        raise BizException(
            code="ALREADY_INITIALIZED",
            message="系统已初始化（至少存在一个用户），拒绝重复创建",
            status_code=409,
        )

    # 复用 user_service 的逻辑做 username 重复检查（虽然 count==0 时不可能，但防御性）
    validate_password_strength(password)
    payload = UserCreate(
        username=username,
        email=email,
        password=password,
        role="admin",
    )

    # 二次检查（处理并发 init 请求）
    count_again = (await db.execute(select(func.count(User.id)))).scalar_one()
    if count_again > 0:
        raise BizException(
            code="ALREADY_INITIALIZED",
            message="系统已初始化",
            status_code=409,
        )

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=await hash_password(payload.password),
        role=payload.role.value,
    )
    db.add(user)
    await db.flush()

    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id)
    logger.info("首次部署：创建 admin 用户 (id=%s, username=%s)", user.id, user.username)
    return {
        "user": user,
        "access_token": access,
        "refresh_token": refresh,
    }
