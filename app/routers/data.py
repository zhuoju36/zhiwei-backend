"""时序数据查询与批量接入。"""

from datetime import datetime
from typing import Annotated

from fastapi import Depends, Query

from app.core.middleware import create_router
from app.dependencies import CurrentUser, DbSession, check_subitem_access, verify_api_key
from app.schemas.data import DataBatchIngest, TimeSeriesOut
from app.services import data_service

router = create_router(prefix="/data", tags=["时序数据"])


@router.get("/timeseries", response_model=TimeSeriesOut)
async def get_timeseries(
    db: DbSession,
    current_user: CurrentUser,
    channel_id: int = Query(..., description="通道 ID"),
    start: datetime = Query(..., description="开始时间 ISO8601"),
    end: datetime = Query(..., description="结束时间 ISO8601"),
    interval: str = Query("raw", description="聚合间隔: raw/100ms/1s/1m/1h/1d"),
) -> TimeSeriesOut:
    # 权限检查：用户是否有该通道所属子项的权限
    subitem_id = await data_service.check_channel_subitem(channel_id)
    await check_subitem_access(db, current_user, subitem_id)

    data = await data_service.query_timeseries(channel_id, start, end, interval)
    return TimeSeriesOut(channel_id=channel_id, interval=interval, data=data)


@router.get("/latest/{channel_id}")
async def get_latest_value(
    channel_id: int, db: DbSession, current_user: CurrentUser
) -> dict | None:
    subitem_id = await data_service.check_channel_subitem(channel_id)
    await check_subitem_access(db, current_user, subitem_id)
    return await data_service.get_latest(channel_id)


@router.post("/ingest", status_code=200)
async def ingest_batch(
    payload: DataBatchIngest,
    api_key: Annotated[str, Depends(verify_api_key)],
) -> dict[str, int]:
    """边缘网关批量数据接入端点，高频调用，必须极致轻量（API Key 认证，非 JWT）。"""
    written = await data_service.batch_ingest(payload.readings)
    return {"written": written}
