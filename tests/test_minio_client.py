"""MinIO 客户端测试（依赖 compose 已起的 shm-minio）。"""

import uuid

import pytest

from app.utils import minio_client


@pytest.fixture
async def ensure_minio() -> None:
    await minio_client.init()


async def test_put_get_json_roundtrip(ensure_minio) -> None:
    key = f"test/{uuid.uuid4().hex}.json"
    payload = {"hello": "world", "n": 42, "lst": [1, 2, 3]}
    await minio_client.put_json(key, payload)
    fetched = await minio_client.get_json(key)
    assert fetched == payload


async def test_put_get_bytes_roundtrip(ensure_minio) -> None:
    key = f"test/{uuid.uuid4().hex}.bin"
    raw = b"\x00\x01\x02\x03binary"
    await minio_client.put_bytes(key, raw, content_type="application/octet-stream")
    fetched = await minio_client.get_bytes(key)
    assert fetched == raw


async def test_bucket_creation_idempotent(ensure_minio) -> None:
    """重复 init() 不应抛错。"""
    await minio_client.init()
    await minio_client.init()
