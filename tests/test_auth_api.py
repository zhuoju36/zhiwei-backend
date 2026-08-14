"""认证接口集成测试。"""

from httpx import AsyncClient

from tests.conftest import login_headers


async def test_login_and_refresh(client: AsyncClient, admin_user: dict) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": admin_user["username"], "password": admin_user["password"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "OK"
    tokens = body["data"]
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["access_token"]


async def test_login_wrong_password(client: AsyncClient, admin_user: dict) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": admin_user["username"], "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_ERROR"


async def test_access_without_token_rejected(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/subitems")
    assert resp.status_code == 401


async def test_login_headers_helper(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    assert headers["Authorization"].startswith("Bearer ")
