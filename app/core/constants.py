"""全局常量与枚举。"""

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"


class ProjectPermission(StrEnum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class DeviceStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"


class AlertLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    DANGER = "danger"


class Quality(StrEnum):
    GOOD = "good"
    BAD = "bad"
    UNCERTAIN = "uncertain"


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200
