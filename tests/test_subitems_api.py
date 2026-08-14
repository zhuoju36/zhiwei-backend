"""项目 CRUD 集成测试。"""

import uuid

from httpx import AsyncClient

from tests.conftest import login_headers


async def test_project_crud_flow(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    name = f"测试项目-{uuid.uuid4().hex[:8]}"

    # 创建
    resp = await client.post(
        "/api/v1/subitems",
        json={"name": name, "description": "集成测试", "location": {"lat": 31.2, "lng": 121.5}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    project = resp.json()["data"]
    subitem_id = project["id"]
    assert project["name"] == name

    # 列表包含新项目（size 设大避免老测试残留挤压）
    resp = await client.get("/api/v1/subitems?size=200", headers=headers)
    assert resp.status_code == 200
    page = resp.json()["data"]
    assert page["total"] >= 1
    assert any(p["id"] == subitem_id for p in page["items"])

    # 详情
    resp = await client.get(f"/api/v1/subitems/{subitem_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["location"]["lat"] == 31.2

    # 更新
    resp = await client.put(
        f"/api/v1/subitems/{subitem_id}", json={"description": "已更新"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["description"] == "已更新"

    # 删除
    resp = await client.delete(f"/api/v1/subitems/{subitem_id}", headers=headers)
    assert resp.status_code == 204
    resp = await client.get(f"/api/v1/subitems/{subitem_id}", headers=headers)
    assert resp.status_code == 404
