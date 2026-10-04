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


def entry_created_at(user_date: date | datetime | str | None = None) -> datetime:
    """Calendar date the user entered, with the current IST clock time.

    Stored as a naive datetime so SQL Server keeps that clock time as entered.
    """
    local_now = now_app().replace(tzinfo=None)
    entered: date | None = None
    if isinstance(user_date, datetime):
        entered = user_date.date()
    elif isinstance(user_date, date):
        entered = user_date
    elif isinstance(user_date, str) and user_date.strip():
        try:
            entered = date.fromisoformat(user_date.strip()[:10])
        except ValueError:
            entered = None
    if entered is None:
        return local_now
    return datetime.combine(entered, local_now.time())
