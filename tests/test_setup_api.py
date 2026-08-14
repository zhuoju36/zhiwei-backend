"""首次部署 setup API 测试。

每个测试前清空 users 表（模拟首次部署），用独立 admin_user fixture 验证
已初始化后的行为。tests/conftest.py 的 autouse _reset_global_async_resources
会自动 dispose engine。
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient

from app.database import AsyncSessionLocal


async def _wipe_users() -> None:
    """清空所有相关表（先依赖后主体），模拟首次部署。"""
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        # TRUNCATE CASCADE 一次性清空（绕过 FK 依赖）
        await db.execute(
            text(
                "TRUNCATE TABLE alerts, analysis_jobs, sensors, devices, "
                "user_projects, projects, users RESTART IDENTITY CASCADE"
            )
        )
        await db.commit()


@pytest.fixture
async def fresh_db() -> AsyncGenerator[None, None]:
    """每个测试前清空 users 表，模拟首次部署。"""
    await _wipe_users()
    yield
    await _wipe_users()


async def test_get_status_before_init_returns_uninitialized(
    client: AsyncClient, fresh_db: None
) -> None:
    resp = await client.get("/api/v1/setup/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["initialized"] is False
    assert body["password_requirements"]["min_length"] == 8
    assert body["password_requirements"]["require_letter"] is True
    assert body["password_requirements"]["require_digit"] is True


async def test_init_admin_creates_first_user(client: AsyncClient, fresh_db: None) -> None:
    resp = await client.post(
        "/api/v1/setup/init-admin",
        json={
            "username": "admin",
            "email": "admin@example.com",
            "password": "admin12345",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["admin_id"] > 0
    assert body["username"] == "admin"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"

    # 验证 status 已变为已初始化
    resp = await client.get("/api/v1/setup/status")
    assert resp.json()["data"]["initialized"] is True


async def test_init_admin_returns_409_when_already_initialized(
    client: AsyncClient, fresh_db: None
) -> None:
    # 先创建一个
    await client.post(
        "/api/v1/setup/init-admin",
        json={"username": "admin", "email": "a@example.com", "password": "admin12345"},
    )
    # 再创建一次应 409
    resp = await client.post(
        "/api/v1/setup/init-admin",
        json={"username": "admin2", "email": "b@example.com", "password": "admin12345"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "ALREADY_INITIALIZED"


async def test_init_admin_weak_password_too_short(client: AsyncClient, fresh_db: None) -> None:
    """密码 7 字符（不足 8）：Pydantic min_length 校验 → 422。"""
    resp = await client.post(
        "/api/v1/setup/init-admin",
        json={"username": "admin", "email": "a@example.com", "password": "Aa1shor"},
    )
    assert resp.status_code == 422


async def test_init_admin_weak_password_no_letter(client: AsyncClient, fresh_db: None) -> None:
    resp = await client.post(
        "/api/v1/setup/init-admin",
        json={"username": "admin", "email": "a@example.com", "password": "12345678"},
    )
    assert resp.status_code == 422
    # Pydantic schema 通过（8 字符），service 层 WEAK_PASSWORD
    assert resp.json()["code"] == "WEAK_PASSWORD"


async def test_init_admin_weak_password_no_digit(client: AsyncClient, fresh_db: None) -> None:
    resp = await client.post(
        "/api/v1/setup/init-admin",
        json={"username": "admin", "email": "a@example.com", "password": "abcdefgh"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "WEAK_PASSWORD"


async def test_init_admin_invalid_username_pattern(client: AsyncClient, fresh_db: None) -> None:
    """username 含非法字符 → Pydantic 422（pattern 校验）。"""
    resp = await client.post(
        "/api/v1/setup/init-admin",
        json={"username": "ad min!", "email": "a@example.com", "password": "admin12345"},
    )
    assert resp.status_code == 422


async def test_init_admin_missing_email(client: AsyncClient, fresh_db: None) -> None:
    resp = await client.post(
        "/api/v1/setup/init-admin",
        json={"username": "admin", "password": "admin12345"},
    )
    assert resp.status_code == 422  # Pydantic missing field


async def test_setup_then_login(client: AsyncClient, fresh_db: None) -> None:
    """setup 创建的 admin 可以立即用 /auth/login 登录。"""
    await client.post(
        "/api/v1/setup/init-admin",
        json={"username": "admin", "email": "a@example.com", "password": "admin12345"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin12345"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()["data"]
