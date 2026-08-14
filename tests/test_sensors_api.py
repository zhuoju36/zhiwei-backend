"""传感器 API 集成测试（v0.9 起 sensor 含原 point 位置字段，挂 device 下）。"""

import uuid

from httpx import AsyncClient

from app.database import AsyncSessionLocal
from app.models.device import Device
from app.models.project import Project
from tests.conftest import login_headers


async def _make_device() -> tuple[int, int]:
    s = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        project = Project(name=f"sensor-test-{s}")
        db.add(project)
        await db.flush()
        device = Device(
            project_id=project.id,
            device_code=f"GW-{s}",
            protocol="http_json",
            config={},
        )
        db.add(device)
        await db.commit()
        return project.id, device.id


async def test_sensor_crud(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    project_id, device_id = await _make_device()

    # 创建传感器（含位置字段：原 point 与 sensor 合一）
    resp = await client.post(
        "/api/v1/sensors",
        json={
            "device_id": device_id,
            "sensor_code": "IMU1",
            "sensor_name": "塔 3 第 1 测点",
            "sensor_type": "structural_joint",
            "model": "XYZ-123",
            "position": {"x": 0.0, "y": 0.0, "z": 15.0},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    sensor = resp.json()["data"]
    sensor_id = sensor["id"]
    assert sensor["sensor_code"] == "IMU1"
    assert sensor["position"] == {"x": 0.0, "y": 0.0, "z": 15.0}
    assert sensor["is_active"] is True

    # 列表按 device
    resp = await client.get(f"/api/v1/sensors?device_id={device_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1

    # 详情
    resp = await client.get(f"/api/v1/sensors/{sensor_id}", headers=headers)
    assert resp.status_code == 200

    # 更新位置与仪器元数据
    resp = await client.put(
        f"/api/v1/sensors/{sensor_id}",
        json={"position": {"x": 1.0, "y": 2.0, "z": 15.0}, "model": "XYZ-456"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["position"] == {"x": 1.0, "y": 2.0, "z": 15.0}
    assert data["model"] == "XYZ-456"

    # 删除
    resp = await client.delete(f"/api/v1/sensors/{sensor_id}", headers=headers)
    assert resp.status_code == 204


async def test_sensor_code_unique_per_device(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    _, device_id = await _make_device()

    resp = await client.post(
        "/api/v1/sensors",
        json={"device_id": device_id, "sensor_code": "IMU1"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    resp = await client.post(
        "/api/v1/sensors",
        json={"device_id": device_id, "sensor_code": "IMU1"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "SENSOR_CODE_EXISTS"


async def test_sensor_list_requires_filter(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    resp = await client.get("/api/v1/sensors", headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "BAD_REQUEST"
