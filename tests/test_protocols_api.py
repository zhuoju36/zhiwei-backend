"""协议元数据 API 测试。"""

import uuid

from httpx import AsyncClient
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.subitem import Subitem
from tests.conftest import login_headers


async def _create_project() -> int:
    s = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        proj = Subitem(name=f"proto-test-{s}")
        db.add(proj)
        await db.commit()
        await db.refresh(proj)
        return proj.id


async def _cleanup_project(subitem_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Subitem).where(Subitem.id == subitem_id))
        await db.commit()


async def test_list_protocols_returns_registered(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.get("/api/v1/protocols", headers=headers)
    assert resp.status_code == 200, resp.text
    names = {p["name"] for p in resp.json()["data"]}
    assert {"http_json", "modbus_tcp", "mqtt"}.issubset(names)
    for p in resp.json()["data"]:
        assert p["version"]
        assert isinstance(p["supports_batch"], bool)
        assert isinstance(p["config_schema"], dict)


async def test_create_device_unknown_protocol_rejected(
    client: AsyncClient, admin_user: dict
) -> None:
    subitem_id = await _create_project()
    try:
        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        resp = await client.post(
            "/api/v1/devices",
            json={
                "subitem_id": subitem_id,
                "device_code": "GW-NO-SUCH-PROTO",
                "protocol": "made_up_protocol",
                "config": {},
            },
            headers=headers,
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "PROTOCOL_NOT_REGISTERED"
    finally:
        await _cleanup_project(subitem_id)


async def test_create_device_unknown_protocol_lists_available(
    client: AsyncClient, admin_user: dict
) -> None:
    subitem_id = await _create_project()
    try:
        headers = await login_headers(client, admin_user["username"], admin_user["password"])
        resp = await client.post(
            "/api/v1/devices",
            json={
                "subitem_id": subitem_id,
                "device_code": "GW-NO-SUCH-PROTO-2",
                "protocol": "made_up",
                "config": {},
            },
            headers=headers,
        )
        assert "http_json" in resp.json()["message"]
        assert "modbus_tcp" in resp.json()["message"]
    finally:
        await _cleanup_project(subitem_id)
