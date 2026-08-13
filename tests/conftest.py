"""pytest 公共 fixture：异步测试客户端与测试用户。

集成测试连接 docker compose 拉起的本地 TimescaleDB/Redis（见 .env）。
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.main import app
from app.models.user import User


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def admin_user() -> AsyncGenerator[dict, None]:
    """创建唯一的 admin 测试用户，用后删除。"""
    username = f"admin_{uuid.uuid4().hex[:8]}"
    password = "test-pass-123"
    async with AsyncSessionLocal() as db:
        user = User(
            username=username,
            email=f"{username}@test.local",
            hashed_password=await hash_password(password),
            role="admin",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id
    yield {"id": user_id, "username": username, "password": password}
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if user is not None:
            await db.delete(user)
            await db.commit()


async def login_headers(client: AsyncClient, username: str, password: str) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
