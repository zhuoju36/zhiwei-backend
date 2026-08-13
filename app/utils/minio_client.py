"""MinIO 异步客户端封装（aioboto3，S3 兼容）。

全局单例 + 懒初始化。bucket 缺失时自动创建。
"""

import json
import logging
from typing import Any

import aioboto3

from app.config import settings

logger = logging.getLogger(__name__)

_session: aioboto3.Session | None = None
_initialized: bool = False


def _endpoint_url() -> str:
    ep = settings.minio_endpoint
    if not ep.startswith(("http://", "https://")):
        ep = f"http://{ep}"
    return ep


def _session_new() -> aioboto3.Session:
    return aioboto3.Session()


async def init() -> None:
    """启动时调用：确保 bucket 存在。失败不抛出。"""
    global _initialized, _session
    if _initialized:
        return
    _session = _session_new()
    try:
        async with _session.client(
            "s3",
            endpoint_url=_endpoint_url(),
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
        ) as s3:
            try:
                await s3.head_bucket(Bucket=settings.minio_bucket)
            except Exception:
                try:
                    await s3.create_bucket(Bucket=settings.minio_bucket)
                    logger.info("MinIO bucket 已创建: %s", settings.minio_bucket)
                except Exception:
                    logger.exception("MinIO bucket 创建失败（继续运行）")
        _initialized = True
    except Exception:
        logger.exception("MinIO 初始化失败（功能将不可用）")


async def close() -> None:
    # aioboto3 session 没有 close，由 GC 处理；仅清空引用
    global _session
    _session = None
    _initialized = False


def _require_session() -> aioboto3.Session:
    global _session
    if _session is None:
        _session = _session_new()
    return _session


def _client_kwargs() -> dict[str, Any]:
    return {
        "endpoint_url": _endpoint_url(),
        "aws_access_key_id": settings.minio_access_key,
        "aws_secret_access_key": settings.minio_secret_key,
    }


async def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    sess = _require_session()
    async with sess.client("s3", **_client_kwargs()) as s3:
        await s3.put_object(
            Bucket=settings.minio_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )


async def get_bytes(key: str) -> bytes:
    sess = _require_session()
    async with sess.client("s3", **_client_kwargs()) as s3:
        resp = await s3.get_object(Bucket=settings.minio_bucket, Key=key)
        return await resp["Body"].read()


async def put_json(key: str, obj: Any) -> None:
    await put_bytes(key, json.dumps(obj).encode("utf-8"), content_type="application/json")


async def get_json(key: str) -> Any:
    raw = await get_bytes(key)
    return json.loads(raw)
