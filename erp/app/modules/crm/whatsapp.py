"""WhatsApp deep-link helpers for CRM."""

from __future__ import annotations

import re


def wa_me_url(mobile: str | None) -> str | None:
    """Build https://wa.me/ URL from mobile; India 10-digit numbers get 91 prefix."""
    digits = re.sub(r"\D", "", mobile or "")
    if not digits:
        return None
    if len(digits) == 10:
        digits = f"91{digits}"
    elif len(digits) > 10:
        digits = f"91{digits[-10:]}"
    else:
        return None
    return f"https://wa.me/{digits}"
