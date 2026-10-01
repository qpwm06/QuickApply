from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

LOCAL_TIMEZONE = ZoneInfo("America/Chicago")
LOCAL_TIMEZONE_LABEL = "America/Chicago"


def _coerce_datetime(dt: datetime | str | None) -> datetime | None:
    if dt is None or isinstance(dt, datetime):
        return dt
    normalized = dt.strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None


def to_local_time(dt: datetime | str | None) -> datetime | None:
    dt = _coerce_datetime(dt)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TIMEZONE)


def format_local_time(dt: datetime | str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    local_dt = to_local_time(dt)
    if local_dt is None:
        return ""
    return local_dt.strftime(fmt)


def parse_date_input(raw: str | None) -> date | None:
    """中文注释：解析 <input type="date"> 的 YYYY-MM-DD；空值或非法值返回 None。"""
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def normalize_date_range(
    start_date: date | None,
    end_date: date | None,
) -> tuple[date | None, date | None]:
    """中文注释：只给一个日期时保持开区间（只给起始=从该日往后，只给截止=到该日为止）；
    两个都给但填反了就自动交换。"""
    if start_date and end_date and start_date > end_date:
        return end_date, start_date
    return start_date, end_date


def date_in_range(value: date | None, start_date: date | None, end_date: date | None) -> bool:
    if start_date is None and end_date is None:
        return True
    if value is None:
        return False
    if start_date is not None and value < start_date:
        return False
    if end_date is not None and value > end_date:
        return False
    return True


def local_date(dt: datetime | str | None) -> date | None:
    local_dt = to_local_time(dt)
    return local_dt.date() if local_dt is not None else None
