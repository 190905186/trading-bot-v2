"""Market session helpers (IST trading hours)."""

from __future__ import annotations

from datetime import datetime


def session_bounds_for_date(
    d: datetime,
    *,
    start_h: int,
    start_m: int,
    end_h: int,
    end_m: int,
) -> tuple[datetime, datetime]:
    tz = d.tzinfo
    if tz is None:
        raise ValueError("session date must be timezone-aware")
    start = d.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = d.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    if end <= start:
        raise ValueError("session end must be after session start")
    return start, end


def is_within_session(
    now: datetime,
    *,
    start_h: int,
    start_m: int,
    end_h: int,
    end_m: int,
) -> bool:
    """True when ``now`` is inside [session_start, session_end) on the same calendar day."""
    session_start, session_end = session_bounds_for_date(
        now,
        start_h=start_h,
        start_m=start_m,
        end_h=end_h,
        end_m=end_m,
    )
    return session_start <= now < session_end
