"""3D 模型 API 测试：上传、转换、列表、下载、删除。"""

import uuid

import pytest
from httpx import AsyncClient

from app.database import AsyncSessionLocal
from app.models.model import Model
from app.models.subitem import Subitem
from tests.conftest import login_headers

# 三角形立方体（8 顶点 / 12 面），trimesh 可直接加载
CUBE_OBJ = b"""v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
v 0 0 1
v 1 0 1
v 1 1 1
v 0 1 1
f 1 2 3
f 1 3 4
f 5 8 7
f 5 7 6
f 1 5 6
f 1 6 2
f 2 6 7
f 2 7 3
f 3 7 8
f 3 8 4
f 4 8 5
f 4 5 1
"""


async def _create_subitem() -> int:
    async with AsyncSessionLocal() as db:
        sub = Subitem(name=f"model-test-{uuid.uuid4().hex[:8]}")
        db.add(sub)
        await db.commit()
        await db.refresh(sub)
        return sub.id


async def _upload(client: AsyncClient, headers: dict, subitem_id: int, filename: str, data: bytes):
    return await client.post(
        f"/api/v1/models/{subitem_id}/upload",
        files={"file": (filename, data, "application/octet-stream")},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_upload_obj_converts_to_glb(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    subitem_id = await _create_subitem()

    resp = await _upload(client, headers, subitem_id, "cube.obj", CUBE_OBJ)
    assert resp.status_code == 201, resp.text
    model_id = resp.json()["data"]["model_id"]

    # eager 模式下转换任务已同步完成
    resp = await client.get(f"/api/v1/models/{model_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["status"] == "success", body
    assert body["source_format"] == "obj"
    assert body["glb_key"].startswith("models/")
    assert body["finished_at"] is not None

    # 下载 GLB：魔数 "glTF"
    resp = await client.get(f"/api/v1/models/{model_id}/file", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "model/gltf-binary"
    assert resp.content[:4] == b"glTF"


@pytest.mark.asyncio
async def test_subitem_multiple_models(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    subitem_id = await _create_subitem()

    for name in ("a.obj", "b.obj"):
        resp = await _upload(client, headers, subitem_id, name, CUBE_OBJ)
        assert resp.status_code == 201, resp.text

    resp = await client.get(f"/api/v1/models?subitem_id={subitem_id}", headers=headers)
    assert resp.status_code == 200
    page = resp.json()["data"]
    assert page["total"] == 2
    keys = {m["glb_key"] for m in page["items"]}
    assert len(keys) == 2  # 各自独立 GLB 产物


@pytest.mark.asyncio
async def test_upload_ifc_rejected(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    subitem_id = await _create_subitem()

    resp = await _upload(client, headers, subitem_id, "model.ifc", b"ISO-10303-21;")
    assert resp.status_code == 400
    assert resp.json()["code"] == "MODEL_FORMAT_UNSUPPORTED"


@pytest.mark.asyncio
async def test_upload_forbidden_for_unlinked_user(client: AsyncClient) -> None:
    from app.core.constants import Role
    from app.core.security import hash_password
    from app.models.user import User

    subitem_id = await _create_subitem()

    # 普通用户（无任何子项授权）
    name = f"u_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        u = User(
            username=name,
            email=f"{name}@example.com",
            hashed_password=await hash_password("user12345"),
            role=Role.USER.value,
        )
        db.add(u)
        await db.commit()
        user_id = u.id
    try:
        login = await client.post(
            "/api/v1/auth/login",
            data={"username": name, "password": "user12345"},
        )
        user_headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
        resp = await _upload(client, user_headers, subitem_id, "cube.obj", CUBE_OBJ)
        assert resp.status_code == 403, resp.text
    finally:
        async with AsyncSessionLocal() as db:
            await db.delete(await db.get(User, user_id))
            await db.commit()


@pytest.mark.asyncio
async def test_download_not_ready(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    subitem_id = await _create_subitem()
    async with AsyncSessionLocal() as db:
        m = Model(
            subitem_id=subitem_id,
            original_key=f"models/{subitem_id}/x.obj",
            original_name="x.obj",
            source_format="obj",
            status="pending",
        )
        db.add(m)
        await db.commit()
        await db.refresh(m)
        model_id = m.id

    resp = await client.get(f"/api/v1/models/{model_id}/file", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "MODEL_NOT_READY"


@pytest.mark.asyncio
async def test_delete_model(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    subitem_id = await _create_subitem()

    resp = await _upload(client, headers, subitem_id, "cube.obj", CUBE_OBJ)
    model_id = resp.json()["data"]["model_id"]

    resp = await client.delete(f"/api/v1/models/{model_id}", headers=headers)
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/models?subitem_id={subitem_id}", headers=headers)
    assert resp.json()["data"]["total"] == 0

    resp = await client.delete(f"/api/v1/models/{model_id}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_requires_admin(client: AsyncClient, admin_user: dict) -> None:
    headers = await login_headers(client, admin_user["username"], admin_user["password"])
    subitem_id = await _create_subitem()
    resp = await _upload(client, headers, subitem_id, "cube.obj", CUBE_OBJ)
    model_id = resp.json()["data"]["model_id"]

    # 无 token -> 401
    resp = await client.delete(f"/api/v1/models/{model_id}")
    assert resp.status_code == 401
