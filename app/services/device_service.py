"""设备业务逻辑。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizException
from app.models.device import Device
from app.models.project import Project
from app.plugins.protocols.registry import AdapterRegistry
from app.schemas.device import DeviceCreate, DeviceUpdate


class DeviceService:
    @staticmethod
    async def get(db: AsyncSession, device_id: int) -> Device:
        device = await db.get(Device, device_id)
        if device is None:
            raise BizException(code="DEVICE_NOT_FOUND", message="设备不存在", status_code=404)
        return device

    @staticmethod
    async def list_by_project(
        db: AsyncSession, project_id: int, page: int, size: int
    ) -> tuple[list[Device], int]:
        total = (
            await db.execute(
                select(func.count()).select_from(Device).where(Device.project_id == project_id)
            )
        ).scalar_one()
        rows = (
            (
                await db.execute(
                    select(Device)
                    .where(Device.project_id == project_id)
                    .order_by(Device.id)
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    @staticmethod
    async def create(db: AsyncSession, payload: DeviceCreate) -> Device:
        if await db.get(Project, payload.project_id) is None:
            raise BizException(code="PROJECT_NOT_FOUND", message="项目不存在", status_code=404)
        if payload.protocol not in AdapterRegistry.names():
            raise BizException(
                code="PROTOCOL_NOT_REGISTERED",
                message=f"未注册的协议: {payload.protocol}；可用: {AdapterRegistry.names()}",
                status_code=422,
            )
        # 唯一性：device_code 全局唯一（与数据库约束一致）
        existing = (
            await db.execute(select(Device).where(Device.device_code == payload.device_code))
        ).scalar_one_or_none()
        if existing is not None:
            raise BizException(code="DEVICE_CODE_EXISTS", message="设备编码已存在", status_code=409)
        device = Device(
            project_id=payload.project_id,
            device_code=payload.device_code,
            device_name=payload.device_name,
            protocol=payload.protocol,
            config=payload.config,
        )
        db.add(device)
        await db.flush()
        return device

    @staticmethod
    async def update(db: AsyncSession, device_id: int, payload: DeviceUpdate) -> Device:
        device = await DeviceService.get(db, device_id)
        data = payload.model_dump(exclude_unset=True)
        if "protocol" in data and data["protocol"] not in AdapterRegistry.names():
            raise BizException(
                code="PROTOCOL_NOT_REGISTERED",
                message=f"未注册的协议: {data['protocol']}",
                status_code=422,
            )
        for field, value in data.items():
            setattr(device, field, value)
        await db.flush()
        return device

    @staticmethod
    async def delete(db: AsyncSession, device_id: int) -> None:
        device = await DeviceService.get(db, device_id)
        await db.delete(device)
        await db.flush()
