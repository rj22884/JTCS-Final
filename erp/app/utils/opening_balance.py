"""Opening balance helpers for masters (Dr/Cr defaults from Chart of Group)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation


def default_dr_cr_for_under_type(under_type: str | None) -> str:
    """Assets → Dr, Liabilities → Cr (Tally-style nature)."""
    if (under_type or "").strip().casefold() == "liabilities":
        return "Cr"
    return "Dr"


def normalize_dr_cr(raw) -> str | None:
    token = str(raw or "").strip().upper()
    if not token:
        return None
    if token in {"DR", "D", "DEBIT"}:
        return "Dr"
    if token in {"CR", "C", "CREDIT"}:
        return "Cr"
    raise ValueError("Opening Balance type must be Dr or Cr.")


def parse_opening_balance_amount(raw) -> Decimal | None:
    if raw in (None, ""):
        return None
    text_val = str(raw).strip().replace(",", "")
    if not text_val:
        return None
    try:
        amount = Decimal(text_val)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Opening Balance must be a valid number.") from exc
    if amount < 0:
        raise ValueError("Opening Balance cannot be negative. Use Dr / Cr.")
    return amount.quantize(Decimal("0.01"))


def parse_opening_balance_date(raw) -> date | None:
    if raw in (None, ""):
        return None
    text_val = str(raw).strip()
    if not text_val:
        return None
    try:
        return date.fromisoformat(text_val[:10])
    except ValueError as exc:
        raise ValueError("Opening Balance Date is invalid.") from exc


def parse_opening_balance_fields(payload: dict) -> dict:
    """
    Extract OpeningBalance / OpeningBalanceDate / OpeningBalanceDrCr from a form payload.
    Keys accepted: opening_balance*, OpeningBalance*.
    """
    amount_raw = (
        payload.get("opening_balance")
        if "opening_balance" in payload
        else payload.get("OpeningBalance")
    )
    date_raw = (
        payload.get("opening_balance_date")
        if "opening_balance_date" in payload
        else payload.get("OpeningBalanceDate")
    )
    dr_cr_raw = (
        payload.get("opening_balance_dr_cr")
        if "opening_balance_dr_cr" in payload
        else payload.get("OpeningBalanceDrCr")
    )

    amount = parse_opening_balance_amount(amount_raw)
    ob_date = parse_opening_balance_date(date_raw)
    dr_cr = normalize_dr_cr(dr_cr_raw)

    if amount is not None and amount != Decimal("0.00") and not dr_cr:
        raise ValueError("Select Dr or Cr for Opening Balance.")
    if amount is not None and amount != Decimal("0.00") and not ob_date:
        raise ValueError("Opening Balance Date is required when Opening Balance is entered.")

    if (amount is None or amount == Decimal("0.00")) and not ob_date:
        return {
            "OpeningBalance": None if amount is None else amount,
            "OpeningBalanceDate": None,
            "OpeningBalanceDrCr": dr_cr,
        }

    return {
        "OpeningBalance": amount,
        "OpeningBalanceDate": ob_date,
        "OpeningBalanceDrCr": dr_cr or "Dr",
    }
