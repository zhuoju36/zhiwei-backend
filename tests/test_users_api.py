"""用户管理 API 测试：admin CRUD + SELF_PROTECTED + LAST_ADMIN 守卫。"""

import uuid

from httpx import AsyncClient
from sqlalchemy import delete

from app.core.constants import Role
from app.database import AsyncSessionLocal
from app.models.user import User
from tests.conftest import login_headers


async def _make_user(role: Role = Role.USER) -> dict:
    """创建测试用户，yield {id, username, password, role}，teardown 时删除。"""
    from app.core.security import hash_password

    name = f"u_{uuid.uuid4().hex[:8]}"
    pwd = "user12345"
    async with AsyncSessionLocal() as db:
        u = User(
            username=name,
            email=f"{name}@example.com",
            hashed_password=await hash_password(pwd),
            role=role.value,
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        uid = u.id
    return {"id": uid, "username": name, "password": pwd, "role": role.value}


async def _delete_user(user_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def test_list_users_requires_admin(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 401


async def test_list_users_admin(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    extra = await _make_user(Role.USER)
    try:
        resp = await client.get("/api/v1/users", headers=headers)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["total"] >= 2  # admin + extra
        usernames = {u["username"] for u in body["items"]}
        assert admin_user["username"] in usernames
        assert extra["username"] in usernames
    finally:
        await _delete_user(extra["id"])


async def test_list_users_filter_by_role_and_active(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    inactive = await _make_user(Role.USER)
    async with AsyncSessionLocal() as db:
        u = await db.get(User, inactive["id"])
        u.is_active = False
        await db.commit()
    try:
        resp = await client.get("/api/v1/users?is_active=false", headers=headers)
        ids = {u["id"] for u in resp.json()["data"]["items"]}
        assert inactive["id"] in ids
    finally:
        await _delete_user(inactive["id"])


async def test_create_user(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    name = f"new_{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/users",
        json={"username": name, "email": f"{name}@example.com", "password": "newpass123"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()["data"]
    assert body["username"] == name
    assert body["role"] == "user"
    assert body["is_active"] is True
    await _delete_user(body["id"])


async def test_create_user_duplicate_username_409(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    u = await _make_user()
    try:
        resp = await client.post(
            "/api/v1/users",
            json={
                "username": u["username"],
                "email": "new@example.com",
                "password": "newpass123",
            },
            headers=headers,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "USER_EXISTS"
    finally:
        await _delete_user(u["id"])


async def test_get_user(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    u = await _make_user()
    try:
        resp = await client.get(f"/api/v1/users/{u['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == u["id"]
    finally:
        await _delete_user(u["id"])


async def test_update_user(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    u = await _make_user()
    try:
        resp = await client.put(
            f"/api/v1/users/{u['id']}",
            json={"role": "admin", "is_active": False},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["role"] == "admin"
        assert body["is_active"] is False
    finally:
        await _delete_user(u["id"])


async def test_update_self_role_to_user_409_self_protected(
    client: AsyncClient, admin_user: dict
) -> None:
    """admin 不能把自己降级为 user。"""
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.put(
        f"/api/v1/users/{admin_user['id']}",
        json={"role": "user"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "SELF_PROTECTED"


async def test_update_self_is_active_false_409(client: AsyncClient, admin_user: dict) -> None:
    """admin 不能停用自己。"""
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.put(
        f"/api/v1/users/{admin_user['id']}",
        json={"is_active": False},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "SELF_PROTECTED"


async def test_last_admin_protection(client: AsyncClient, admin_user: dict) -> None:
    """停用自己 → 409 SELF_PROTECTED（先于 LAST_ADMIN 检查）。"""
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.put(
        f"/api/v1/users/{admin_user['id']}",
        json={"is_active": False},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "SELF_PROTECTED"


async def test_last_admin_protection_via_demote(client: AsyncClient, admin_user: dict) -> None:
    """把唯一 admin 降级为 user → SELF_PROTECTED（先于 LAST_ADMIN 检查）。"""
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.put(
        f"/api/v1/users/{admin_user['id']}",
        json={"role": "user"},
        headers=headers,
    )
    assert resp.status_code == 409
    # admin 操作自己：SELF_PROTECTED 优先于 LAST_ADMIN
    assert resp.json()["code"] == "SELF_PROTECTED"


async def test_last_admin_via_demoting_other_admin(client: AsyncClient, admin_user: dict) -> None:
    """存在 2 个 admin 时，admin_a 把 admin_b 降级 → 200（仍剩 admin_a）。"""
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    second = await _make_user(Role.ADMIN)
    try:
        resp = await client.put(
            f"/api/v1/users/{second['id']}",
            json={"role": "user"},
            headers=headers,
        )
        assert resp.status_code == 200
    finally:
        await _delete_user(second["id"])


async def test_admin_can_modify_other_admin(client: AsyncClient, admin_user: dict) -> None:
    """新增第二个 admin，admin_a 修改 admin_b 的 role → 200（允许）。"""
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    # 创建第二个 admin
    second = await _make_user(Role.ADMIN)
    try:
        resp = await client.put(
            f"/api/v1/users/{second['id']}",
            json={"role": "user"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["role"] == "user"
        # 改回来
        await client.put(
            f"/api/v1/users/{second['id']}",
            json={"role": "admin"},
            headers=headers,
        )
    finally:
        await _delete_user(second["id"])


async def test_delete_user(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    u = await _make_user()
    resp = await client.delete(f"/api/v1/users/{u['id']}", headers=headers)
    assert resp.status_code == 204
    # 已删除
    resp = await client.get(f"/api/v1/users/{u['id']}", headers=headers)
    assert resp.status_code == 404


async def test_delete_self_409(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.delete(f"/api/v1/users/{admin_user['id']}", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "SELF_PROTECTED"


async def test_delete_last_admin_409(client: AsyncClient, admin_user: dict) -> None:
    """先创建第二个 admin，删掉自己外的另一个，再删自己 → LAST_ADMIN 守卫。"""
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    second = await _make_user(Role.ADMIN)
    try:
        # 把 second 降级为 user
        await client.put(
            f"/api/v1/users/{second['id']}",
            json={"role": "user"},
            headers=headers,
        )
        # 此时只有 admin_user 一个 admin
        # 删 second
        resp = await client.delete(f"/api/v1/users/{second['id']}", headers=headers)
        assert resp.status_code == 204
        # 现在尝试删 admin_user → 409 LAST_ADMIN
        resp = await client.delete(f"/api/v1/users/{admin_user['id']}", headers=headers)
        assert resp.status_code == 409
        assert resp.json()["code"] == "SELF_PROTECTED"
    finally:
        await _delete_user(second["id"])


async def test_reset_password(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    u = await _make_user()
    try:
        resp = await client.post(
            f"/api/v1/users/{u['id']}/password",
            json={"new_password": "brand-new-pass"},
            headers=headers,
        )
        assert resp.status_code == 204
        # 新密码可登录
        login = await client.post(
            "/api/v1/auth/login",
            data={"username": u["username"], "password": "brand-new-pass"},
        )
        assert login.status_code == 200
        # 旧密码失效
        old = await client.post(
            "/api/v1/auth/login",
            data={"username": u["username"], "password": u["password"]},
        )
        assert old.status_code == 401
    finally:
        await _delete_user(u["id"])


async def test_reset_password_weak_422(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    u = await _make_user()
    try:
        resp = await client.post(
            f"/api/v1/users/{u['id']}/password",
            json={"new_password": "short"},
            headers=headers,
        )
        assert resp.status_code == 422
    finally:
        await _delete_user(u["id"])


async def test_non_admin_token_forbidden(client: AsyncClient, admin_user: dict) -> None:
    """非 admin 角色访问 /users 端点 → 403。"""
    # 创建普通用户
    u = await _make_user(Role.USER)
    try:
        login = await client.post(
            "/api/v1/auth/login",
            data={"username": u["username"], "password": u["password"]},
        )
        token = login.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        for method, url in [
            ("GET", "/api/v1/users"),
            ("POST", "/api/v1/users"),
            ("PUT", f"/api/v1/users/{admin_user['id']}"),
            ("DELETE", f"/api/v1/users/{admin_user['id']}"),
        ]:
            resp = await client.request(method, url, headers=headers, json={})
            assert resp.status_code == 403, (method, url, resp.text)
    finally:
        await _delete_user(u["id"])
