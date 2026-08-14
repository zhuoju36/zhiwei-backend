"""全局常量与枚举。"""

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"


class SubitemPermission(StrEnum):
    """子项级权限（user_subitems 表的 permission 字段）。"""

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
