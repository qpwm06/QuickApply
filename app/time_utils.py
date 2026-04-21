from __future__ import annotations

from datetime import datetime, timezone
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
