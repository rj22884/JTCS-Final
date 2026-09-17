"""Normalize Tally Bill / Misc entry numbers for lookup and save."""

from __future__ import annotations

import re

_MISC_BILL_RE = re.compile(r"^([MSE])(\d{8}/\d+)$", re.IGNORECASE)


def normalize_tally_bill_key(value: str | None) -> str:
    """Canonical form, e.g. ``M 20062026/004`` → ``M-20062026/004``."""
    raw = (value or "").strip()
    if not raw:
        return ""
    upper = raw.upper()
    compact = re.sub(r"[\s\-]+", "", upper)
    match = _MISC_BILL_RE.match(compact)
    if match:
        return f"{match.group(1).upper()}-{match.group(2)}"
    return upper


def tally_bill_compact(value: str | None) -> str:
    """Space/hyphen-insensitive compare key, e.g. ``M20062026/004``."""
    return re.sub(r"[\s\-]+", "", normalize_tally_bill_key(value))
