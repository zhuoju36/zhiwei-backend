"""测点 API 集成测试。"""

import uuid

from httpx import AsyncClient

from app.database import AsyncSessionLocal
from app.models.device import Device
from app.models.subitem import Subitem
from tests.conftest import login_headers


async def _make_device(suffix: str | None = None) -> tuple[int, str, str]:
    s = suffix or uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        proj = Subitem(name=f"point-test-{s}")
        db.add(proj)
        await db.flush()
        device = Device(
            subitem_id=proj.id,
            device_code=f"GW-{s}",
            protocol="http_json",
            config={},
        )
        db.add(device)
        await db.commit()
        await db.refresh(device)
        return proj.id, device.id, f"ACC-{s}"


async def test_point_crud_with_alert_rules(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    subitem_id, device_id, point_code = await _make_device()

    # 创建（带 alert_rules）
    resp = await client.post(
        "/api/v1/points",
        json={
            "device_id": device_id,
            "point_code": point_code,
            "point_name": "加速度-X",
            "point_type": "acceleration",
            "unit": "m/s2",
            "sampling_rate": 100,
            "alert_rules": [
                {"operator": "gt", "threshold": 0.5, "level": "warning", "message": "超阈值"}
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    point = resp.json()["data"]
    point_id = point["id"]
    assert point["alert_rules"][0]["threshold"] == 0.5

    # 按 device 列表
    resp = await client.get(f"/api/v1/points?device_id={device_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1

    # 按 project 列表
    resp = await client.get(f"/api/v1/points?subitem_id={subitem_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1

    # 更新 alert_rules
    resp = await client.put(
        f"/api/v1/points/{point_id}",
        json={
            "alert_rules": [
                {"operator": "gt", "threshold": 0.7, "level": "danger"},
                {"operator": "lt", "threshold": -0.7, "level": "warning"},
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 200
    rules = resp.json()["data"]["alert_rules"]
    assert len(rules) == 2
    assert {r["level"] for r in rules} == {"danger", "warning"}


async def test_point_list_requires_filter(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.get("/api/v1/points", headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "BAD_REQUEST"
