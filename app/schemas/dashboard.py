"""大屏聚合接口 Schema。"""

from pydantic import BaseModel


class ProjectLocation(BaseModel):
    lat: float
    lng: float
    address: str | None = None


class DeviceStats(BaseModel):
    total: int
    online: int
    offline: int
    error: int


class ProjectOverviewItem(BaseModel):
    id: int
    name: str
    description: str | None
    location: ProjectLocation | None
    device_stats: DeviceStats


class DashboardOverview(BaseModel):
    projects: list[ProjectOverviewItem]
