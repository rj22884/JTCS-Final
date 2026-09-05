"""Bank Master Yes/No flags used on forms and Payment Received lists."""

from __future__ import annotations


def form_flag(form: dict, *keys: str) -> bool:
    for key in keys:
        if key in form:
            raw = (form.get(key) or "").strip().lower()
            return raw in {"1", "true", "on", "yes"}
    return False


def is_account_payment_received(account) -> bool:
    return bool(getattr(account, "AccountPaymentReceived", False))
