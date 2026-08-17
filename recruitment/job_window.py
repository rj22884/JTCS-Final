"""Single source of truth for whether a job is accepting applications.

All public CTA, job, apply, and submit paths must use these helpers.
Closing is evaluated in the job timezone (default Asia/Kolkata), never in the
visitor's browser timezone.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

# India has no DST; used if the host OS has no tzdata (common on Windows).
IST = timezone(timedelta(hours=5, minutes=30))

from recruitment.models import Job

DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_CLOSING_TIME = "23:59:59"
CLOSED_MESSAGE = "Applications for the Sales Executive position are now closed."


def _parse_closing_time(raw: str | None) -> time:
    text = (raw or DEFAULT_CLOSING_TIME).strip() or DEFAULT_CLOSING_TIME
    parts = text.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(parts[2]) if len(parts) > 2 else 0
        return time(hour, minute, second)
    except (ValueError, IndexError):
        return time(23, 59, 59)


def job_timezone(job: Job | None):
    name = (getattr(job, "timezone", None) or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name)
    except Exception:
        try:
            return ZoneInfo(DEFAULT_TIMEZONE)
        except Exception:
            return IST


def job_closing_datetime(job: Job | None) -> datetime | None:
    if job is None or not job.closing_date:
        return None
    tz = job_timezone(job)
    return datetime.combine(job.closing_date, _parse_closing_time(getattr(job, "closing_time", None)), tzinfo=tz)


def now_in_job_tz(job: Job | None = None) -> datetime:
    return datetime.now(job_timezone(job))


def is_job_application_open(job: Job | None, now: datetime | None = None) -> bool:
    if job is None:
        return False
    if (job.status or "").lower() in {"draft", "closed"}:
        return False
    closes = job_closing_datetime(job)
    if closes is None:
        return (job.status or "").lower() == "open"
    current = now or now_in_job_tz(job)
    if current.tzinfo is None:
        current = current.replace(tzinfo=closes.tzinfo)
    else:
        current = current.astimezone(closes.tzinfo)
    return current <= closes


def last_date_label(job: Job | None) -> str:
    if job is None or not job.closing_date:
        return ""
    return job.closing_date.strftime("%d %B %Y")


def job_window_payload(job: Job | None) -> dict:
    open_now = is_job_application_open(job)
    closes = job_closing_datetime(job)
    return {
        "slug": job.slug if job else None,
        "job_title": job.job_title if job else "Sales Executive",
        "open": open_now,
        "status": "open" if open_now else "closed",
        "last_date_label": last_date_label(job),
        "closing_date": job.closing_date.isoformat() if job and job.closing_date else None,
        "closing_time": (getattr(job, "closing_time", None) or DEFAULT_CLOSING_TIME),
        "timezone": (getattr(job, "timezone", None) or DEFAULT_TIMEZONE),
        "closes_at": closes.isoformat() if closes else None,
        "message": None if open_now else CLOSED_MESSAGE,
    }


def ensure_sales_executive_closing(job: Job) -> None:
    """Set the default Sales Executive deadline if it has not been configured."""
    if job.closing_date is None:
        job.closing_date = date(2026, 10, 31)
    if not getattr(job, "closing_time", None):
        job.closing_time = DEFAULT_CLOSING_TIME
    if not getattr(job, "timezone", None):
        job.timezone = DEFAULT_TIMEZONE
