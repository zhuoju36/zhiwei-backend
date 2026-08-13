"""开发种子数据：admin 用户、演示项目、设备与测点（幂等）。

用法：.venv/bin/python scripts/seed.py
"""

import asyncio
import logging

from sqlalchemy import select

from app.core.constants import Role
from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models import Device, Point, Project, User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123456"  # 仅开发环境


async def main() -> None:
    async with AsyncSessionLocal() as db:
        admin = (
            await db.execute(select(User).where(User.username == ADMIN_USERNAME))
        ).scalar_one_or_none()
        if admin is None:
            admin = User(
                username=ADMIN_USERNAME,
                email="admin@shm.local",
                hashed_password=await hash_password(ADMIN_PASSWORD),
                role=Role.ADMIN.value,
            )
            db.add(admin)
            await db.flush()
            logger.info("创建 admin 用户 (id=%s)", admin.id)

        project = (
            await db.execute(select(Project).where(Project.name == "演示项目"))
        ).scalar_one_or_none()
        if project is None:
            project = Project(name="演示项目", description="开发联调演示", created_by=admin.id)
            db.add(project)
            await db.flush()
            logger.info("创建演示项目 (id=%s)", project.id)

        device = (
            await db.execute(select(Device).where(Device.device_code == "GW-001"))
        ).scalar_one_or_none()
        if device is None:
            device = Device(
                project_id=project.id,
                device_code="GW-001",
                device_name="演示网关",
                protocol="http_json",
                config={"host": "http://localhost", "port": 9000},
            )
            db.add(device)
            await db.flush()
            logger.info("创建设备 GW-001 (id=%s)", device.id)

        point = (
            await db.execute(
                select(Point).where(Point.device_id == device.id, Point.point_code == "ACC-X")
            )
        ).scalar_one_or_none()
        if point is None:
            point = Point(
                device_id=device.id,
                point_code="ACC-X",
                point_name="加速度-X",
                point_type="acceleration",
                unit="m/s2",
                position={"x": 0.0, "y": 0.0, "z": 0.0},
                sampling_rate=100,
            )
            db.add(point)
            await db.flush()
            logger.info("创建测点 ACC-X (id=%s)", point.id)

        await db.commit()
        logger.info("种子数据完成")


if __name__ == "__main__":
    asyncio.run(main())
