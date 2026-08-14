"""时区工具单元测试。"""

from datetime import UTC, datetime, timedelta, timezone

from app.utils.time_utils import to_utc, utc_now


def test_utc_now_is_aware_utc() -> None:
    now = utc_now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_to_utc_naive_treated_as_utc() -> None:
    naive = datetime(2026, 8, 14, 10, 0, 0)
    result = to_utc(naive)
    assert result.tzinfo == UTC
    assert result == naive.replace(tzinfo=UTC)


def test_to_utc_converts_other_tz() -> None:
    tokyo = timezone(timedelta(hours=9))
    local = datetime(2026, 8, 14, 19, 0, 0, tzinfo=tokyo)
    result = to_utc(local)
    assert result.tzinfo == UTC
    assert result.hour == 10  # 19:00 +09:00 == 10:00 UTC
