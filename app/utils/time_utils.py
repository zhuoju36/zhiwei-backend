"""时区处理与时间戳转换工具。"""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """当前 UTC 时间（带时区）。"""
    return datetime.now(UTC)


def to_utc(dt: datetime) -> datetime:
    """将任意 datetime 规范为 UTC aware；naive 输入按 UTC 解释。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
