"""统一导出所有模型，供 Alembic 自动发现。"""

from app.models.alert import Alert
from app.models.analysis import AnalysisJob
from app.models.base import Base
from app.models.channel import Channel
from app.models.device import Device
from app.models.model import Model
from app.models.platform import PlatformSettings
from app.models.project import Project, UserProject
from app.models.reading import Reading
from app.models.sensor import Sensor
from app.models.user import User

__all__ = [
    "Alert",
    "AnalysisJob",
    "Base",
    "Channel",
    "Device",
    "Model",
    "PlatformSettings",
    "Project",
    "Reading",
    "Sensor",
    "User",
    "UserProject",
]
