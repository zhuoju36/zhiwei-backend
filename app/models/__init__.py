"""统一导出所有模型，供 Alembic 自动发现。"""

from app.models.alert import Alert
from app.models.analysis import AnalysisJob
from app.models.base import Base
from app.models.device import Device
from app.models.point import Point
from app.models.project import Project, UserProject
from app.models.timeseries import SensorFeature, SensorRaw
from app.models.user import User

__all__ = [
    "Alert",
    "AnalysisJob",
    "Base",
    "Device",
    "Point",
    "Project",
    "SensorFeature",
    "SensorRaw",
    "User",
    "UserProject",
]
