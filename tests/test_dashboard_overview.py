"""`GET /api/v1/dashboard/overview` 集成测试。"""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import delete

from app.core.constants import Role
from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models.device import Device
from app.models.project import Project, UserProject
from app.models.user import User
from tests.conftest import login_headers


async def _make_project(
    name: str | None = None,
    description: str | None = "test project",
    location: dict[str, Any] | None = None,
) -> int:
    async with AsyncSessionLocal() as db:
        proj = Project(
            name=name or f"overview-{uuid.uuid4().hex[:8]}",
            description=description,
            location=location,
        )
        db.add(proj)
        await db.commit()
        await db.refresh(proj)
        return proj.id


async def _make_device(project_id: int, status: str = "offline") -> int:
    s = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        dev = Device(
            project_id=project_id,
            device_code=f"GW-OV-{s}",
            protocol="http_json",
            config={},
            status=status,
        )
        db.add(dev)
        await db.commit()
        await db.refresh(dev)
        return dev.id


async def _cleanup_project(project_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Device).where(Device.project_id == project_id))
        await db.execute(delete(UserProject).where(UserProject.project_id == project_id))
        await db.execute(delete(Project).where(Project.id == project_id))
        await db.commit()


async def _make_regular_user() -> tuple[int, dict[str, str]]:
    """创建无项目权限的普通用户，返回 (user_id, login_headers)。"""
    name = f"ovr_reader_{uuid.uuid4().hex[:8]}"
    password = "user12345"
    async with AsyncSessionLocal() as db:
        u = User(
            username=name,
            email=f"{name}@example.com",
            hashed_password=await hash_password(password),
            role=Role.USER.value,
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u.id, {"username": name, "password": password}


async def _cleanup_user(user_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(UserProject).where(UserProject.user_id == user_id))
        u = await db.get(User, user_id)
        if u is not None:
            await db.delete(u)
            await db.commit()


async def test_overview_unauthenticated(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/dashboard/overview")
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_ERROR"


async def test_overview_admin_sees_all(client: AsyncClient, admin_user: dict) -> None:
    """admin 看全量项目（含无位置的）。"""
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    p1 = await _make_project(location={"lat": 30.1, "lng": 120.2, "address": "杭州"})
    p2 = await _make_project(description="无位置")
    p3 = await _make_project()
    try:
        resp = await client.get("/api/v1/dashboard/overview", headers=headers)
        assert resp.status_code == 200, resp.text
        ids = {p["id"] for p in resp.json()["data"]["projects"]}
        assert {p1, p2, p3}.issubset(ids)
        for p in resp.json()["data"]["projects"]:
            if p["id"] == p1:
                assert p["location"]["lat"] == 30.1
            if p["id"] == p2:
                assert p["location"] is None
    finally:
        await _cleanup_project(p1)
        await _cleanup_project(p2)
        await _cleanup_project(p3)


async def test_overview_regular_user_filtered(client: AsyncClient, admin_user: dict) -> None:
    """普通用户仅看自己被授权的项目。"""
    p_authed = await _make_project()
    p_hidden1 = await _make_project()
    p_hidden2 = await _make_project()
    user_id, creds = await _make_regular_user()

    async with AsyncSessionLocal() as db:
        db.add(UserProject(user_id=user_id, project_id=p_authed, permission="read"))
        await db.commit()
    try:
        user_headers = await login_headers(client, creds["username"], creds["password"])
        resp = await client.get("/api/v1/dashboard/overview", headers=user_headers)
        assert resp.status_code == 200
        ids = {p["id"] for p in resp.json()["data"]["projects"]}
        assert p_authed in ids
        assert p_hidden1 not in ids
        assert p_hidden2 not in ids
    finally:
        await _cleanup_user(user_id)
        await _cleanup_project(p_authed)
        await _cleanup_project(p_hidden1)
        await _cleanup_project(p_hidden2)


async def test_overview_location_null_still_appears(client: AsyncClient, admin_user: dict) -> None:
    """location=null 的项目也必须出现。"""
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    p = await _make_project(location=None)
    try:
        resp = await client.get("/api/v1/dashboard/overview", headers=headers)
        assert resp.status_code == 200
        item = next(it for it in resp.json()["data"]["projects"] if it["id"] == p)
        assert item["location"] is None
        assert item["device_stats"] == {
            "total": 0,
            "online": 0,
            "offline": 0,
            "error": 0,
        }
    finally:
        await _cleanup_project(p)


async def test_overview_device_counts_self_consistent(
    client: AsyncClient, admin_user: dict
) -> None:
    """混合状态设备的项目：total == online + offline + error。"""
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    p = await _make_project()
    await _make_device(p, status="online")
    await _make_device(p, status="online")
    await _make_device(p, status="online")
    await _make_device(p, status="offline")
    await _make_device(p, status="error")
    try:
        resp = await client.get("/api/v1/dashboard/overview", headers=headers)
        item = next(it for it in resp.json()["data"]["projects"] if it["id"] == p)
        stats = item["device_stats"]
        assert stats["total"] == stats["online"] + stats["offline"] + stats["error"]
        assert stats == {"total": 5, "online": 3, "offline": 1, "error": 1}
    finally:
        await _cleanup_project(p)


async def test_overview_project_without_devices(client: AsyncClient, admin_user: dict) -> None:
    """无设备项目：四个计数均为 0。"""
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    p = await _make_project()
    try:
        resp = await client.get("/api/v1/dashboard/overview", headers=headers)
        item = next(it for it in resp.json()["data"]["projects"] if it["id"] == p)
        assert item["device_stats"] == {
            "total": 0,
            "online": 0,
            "offline": 0,
            "error": 0,
        }
    finally:
        await _cleanup_project(p)


async def test_overview_counts_aggregate_correctly(client: AsyncClient, admin_user: dict) -> None:
    """多项目并行：每个项目独立计数，不串台。"""
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    p_a = await _make_project()
    p_b = await _make_project()
    # A: 2 online, 1 offline
    await _make_device(p_a, status="online")
    await _make_device(p_a, status="online")
    await _make_device(p_a, status="offline")
    # B: 1 error, 1 offline, 1 online
    await _make_device(p_b, status="online")
    await _make_device(p_b, status="offline")
    await _make_device(p_b, status="error")
    try:
        resp = await client.get("/api/v1/dashboard/overview", headers=headers)
        items = {
            it["id"]: it["device_stats"]
            for it in resp.json()["data"]["projects"]
            if it["id"] in {p_a, p_b}
        }
        assert items[p_a] == {"total": 3, "online": 2, "offline": 1, "error": 0}
        assert items[p_b] == {"total": 3, "online": 1, "offline": 1, "error": 1}
    finally:
        await _cleanup_project(p_a)
        await _cleanup_project(p_b)


async def test_overview_location_field_shape(client: AsyncClient, admin_user: dict) -> None:
    """location 解析为 {lat, lng, address} 三字段；address 可空。"""
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    p_full = await _make_project(location={"lat": 31.0, "lng": 121.0, "address": "上海"})
    p_no_addr = await _make_project(location={"lat": 22.5, "lng": 113.9})
    try:
        resp = await client.get("/api/v1/dashboard/overview", headers=headers)
        items = {
            it["id"]: it
            for it in resp.json()["data"]["projects"]
            if it["id"] in {p_full, p_no_addr}
        }
        assert items[p_full]["location"] == {
            "lat": 31.0,
            "lng": 121.0,
            "address": "上海",
        }
        assert items[p_no_addr]["location"] == {
            "lat": 22.5,
            "lng": 113.9,
            "address": None,
        }
    finally:
        await _cleanup_project(p_full)
        await _cleanup_project(p_no_addr)
