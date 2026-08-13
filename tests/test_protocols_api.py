"""协议元数据 API 测试。"""

from httpx import AsyncClient

from tests.conftest import login_headers


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
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.post(
        "/api/v1/devices",
        json={
            "project_id": 1,
            "device_code": "GW-NO-SUCH-PROTO",
            "protocol": "made_up_protocol",
            "config": {},
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "PROTOCOL_NOT_REGISTERED"


async def test_create_device_unknown_protocol_lists_available(
    client: AsyncClient, admin_user: dict
) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.post(
        "/api/v1/devices",
        json={
            "project_id": 1,
            "device_code": "GW-NO-SUCH-PROTO-2",
            "protocol": "made_up",
            "config": {},
        },
        headers=headers,
    )
    assert "http_json" in resp.json()["message"]
    assert "modbus_tcp" in resp.json()["message"]
