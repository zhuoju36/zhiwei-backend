"""测点 API 集成测试（v0.8b 起 point = 物理位置）。"""

import uuid

from httpx import AsyncClient

from app.database import AsyncSessionLocal
from app.models.device import Device
from app.models.subitem import Subitem
from tests.conftest import login_headers


async def _make_device() -> tuple[int, int]:
    s = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        subitem = Subitem(name=f"point-test-{s}")
        db.add(subitem)
        await db.flush()
        device = Device(
            subitem_id=subitem.id,
            device_code=f"GW-{s}",
            protocol="http_json",
            config={},
        )
        db.add(device)
        await db.commit()
        return subitem.id, device.id


async def test_point_crud(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    subitem_id, device_id = await _make_device()

    # 创建测点（v0.8b 起只有位置字段，无 unit/sampling_rate/alert_rules）
    resp = await client.post(
        "/api/v1/points",
        json={
            "device_id": device_id,
            "point_code": "P01",
            "point_name": "塔 3 第 1 测点",
            "point_type": "structural_joint",
            "position": {"x": 0.0, "y": 0.0, "z": 15.0},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    point = resp.json()["data"]
    point_id = point["id"]
    assert point["point_code"] == "P01"
    assert point["position"] == {"x": 0.0, "y": 0.0, "z": 15.0}
    assert point["is_active"] is True

    # 列表按 device
    resp = await client.get(f"/api/v1/points?device_id={device_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1

    # 列表按 subitem
    resp = await client.get(f"/api/v1/points?subitem_id={subitem_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1

    # 详情
    resp = await client.get(f"/api/v1/points/{point_id}", headers=headers)
    assert resp.status_code == 200

    # 更新位置
    resp = await client.put(
        f"/api/v1/points/{point_id}",
        json={"position": {"x": 1.0, "y": 2.0, "z": 15.0}},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["position"] == {"x": 1.0, "y": 2.0, "z": 15.0}

    # 删除
    resp = await client.delete(f"/api/v1/points/{point_id}", headers=headers)
    assert resp.status_code == 204


async def test_point_list_requires_filter(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.get("/api/v1/points", headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "BAD_REQUEST"
