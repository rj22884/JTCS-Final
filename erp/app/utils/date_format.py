from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

DISPLAY_DATE_FORMAT = "%d/%m/%Y"
DISPLAY_DATETIME_FORMAT = "%d/%m/%Y %H:%M:%S"
DISPLAY_DATETIME_SHORT_FORMAT = "%d/%m/%Y %H:%M"

_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_ISO_DATETIME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?"
)
_DISPLAY_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_DISPLAY_DATETIME_RE = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{4})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?"
)


def _coerce_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    match = _ISO_DATE_RE.match(raw)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    match = _DISPLAY_DATE_RE.match(raw)
    if match:
        try:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except ValueError:
            return None
    return None


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    raw = str(value).strip()
    if not raw:
        return None
    match = _ISO_DATETIME_RE.match(raw)
    if match:
        try:
            return datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
                int(match.group(4)),
                int(match.group(5)),
                int(match.group(6) or 0),
            )
        except ValueError:
            return None
    match = _DISPLAY_DATETIME_RE.match(raw)
    if match:
        try:
            return datetime(
                int(match.group(3)),
                int(match.group(2)),
                int(match.group(1)),
                int(match.group(4)),
                int(match.group(5)),
                int(match.group(6) or 0),
            )
        except ValueError:
            return None
    parsed = _coerce_date(raw)
    if parsed:
        return datetime.combine(parsed, datetime.min.time())
    return None


def format_display_date(value: Any, *, empty: str = "—") -> str:
    parsed = _coerce_date(value)
    if parsed is None:
        return empty if value in (None, "") else str(value)
    return parsed.strftime(DISPLAY_DATE_FORMAT)


def format_display_datetime(value: Any, *, with_seconds: bool = True, empty: str = "—") -> str:
    parsed = _coerce_datetime(value)
    if parsed is None:
        return empty if value in (None, "") else str(value)
    fmt = DISPLAY_DATETIME_FORMAT if with_seconds else DISPLAY_DATETIME_SHORT_FORMAT
    return parsed.strftime(fmt)


def format_display_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return format_display_datetime(value)
    if isinstance(value, date):
        return format_display_date(value)
    if isinstance(value, str):
        stripped = value.strip()
        if _ISO_DATE_RE.match(stripped):
            if "T" in stripped or " " in stripped and len(stripped) > 10:
                return format_display_datetime(stripped, empty=stripped)
            return format_display_date(stripped, empty=stripped)
    return value


def parse_display_date(value: str) -> date | None:
    return _coerce_date(value)


def to_iso_date(value: Any) -> str:
    parsed = _coerce_date(value)
    return parsed.isoformat() if parsed else ""
