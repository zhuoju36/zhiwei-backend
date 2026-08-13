"""设备 API 集成测试。"""

import uuid

from httpx import AsyncClient

from app.database import AsyncSessionLocal
from app.models.project import Project
from tests.conftest import login_headers


async def _create_project(db_name: str | None = None) -> int:
    async with AsyncSessionLocal() as db:
        proj = Project(name=f"device-test-{uuid.uuid4().hex[:8]}")
        db.add(proj)
        await db.commit()
        await db.refresh(proj)
        return proj.id


async def test_device_crud_flow(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    project_id = await _create_project()
    code = f"GW-{uuid.uuid4().hex[:8]}"

    # 创建
    resp = await client.post(
        "/api/v1/devices",
        json={
            "project_id": project_id,
            "device_code": code,
            "device_name": "测试网关",
            "protocol": "http_json",
            "config": {"host": "http://example.com"},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    device = resp.json()["data"]
    device_id = device["id"]

    # 列表
    resp = await client.get(f"/api/v1/devices?project_id={project_id}", headers=headers)
    assert resp.status_code == 200
    page = resp.json()["data"]
    assert any(d["id"] == device_id for d in page["items"])

    # 详情
    resp = await client.get(f"/api/v1/devices/{device_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["device_code"] == code

    # 更新
    resp = await client.put(
        f"/api/v1/devices/{device_id}",
        json={"device_name": "新名字"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["device_name"] == "新名字"

    # 删除
    resp = await client.delete(f"/api/v1/devices/{device_id}", headers=headers)
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/devices/{device_id}", headers=headers)
    assert resp.status_code == 404


async def test_device_duplicate_code_rejected(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    project_id = await _create_project()
    code = f"GW-{uuid.uuid4().hex[:8]}"
    body = {
        "project_id": project_id,
        "device_code": code,
        "protocol": "http_json",
        "config": {},
    }
    r1 = await client.post("/api/v1/devices", json=body, headers=headers)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/devices", json=body, headers=headers)
    assert r2.status_code == 409
    assert r2.json()["code"] == "DEVICE_CODE_EXISTS"


async def test_non_admin_cannot_create(client: AsyncClient) -> None:
    """无 admin token 直接被 401 拦截；普通用户场景需要单独绑定 project 写权限（v0.3+）。"""
    resp = await client.post(
        "/api/v1/devices",
        json={"project_id": 1, "device_code": "X", "protocol": "http_json", "config": {}},
    )
    assert resp.status_code == 401
