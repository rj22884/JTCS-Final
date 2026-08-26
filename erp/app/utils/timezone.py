from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# India has no DST. A fixed offset works on Windows without the tzdata package.
APP_TZ = timezone(timedelta(hours=5, minutes=30))
APP_TZ_NAME = "Asia/Kolkata"


def now_app() -> datetime:
    """Current date/time in the JTCS business timezone (IST)."""
    return datetime.now(APP_TZ)


def today_app() -> date:
    """Current calendar date in the JTCS business timezone (IST)."""
    return now_app().date()
