"""Treat ledger transaction lines (not opening balance) as the delete blocker."""

from __future__ import annotations

from datetime import date

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.utils.master_delete_guard import MasterInUseError

LEDGER_KINDS = ("bank", "customer", "work", "item")


def ledger_payload(kind: str, entity_id: int) -> dict:
    return {"kind": (kind or "").strip().lower(), "id": int(entity_id)}


def _is_blocking_txn_line(line: dict) -> bool:
    if (line.get("kind") or "txn") != "txn":
        return False
    try:
        debit = float(line.get("debit") or 0)
    except (TypeError, ValueError):
        debit = 0.0
    try:
        credit = float(line.get("credit") or 0)
    except (TypeError, ValueError):
        credit = 0.0
    return abs(debit) > 0.0001 or abs(credit) > 0.0001


def count_ledger_txn_lines(kind: str, entity_id: int) -> int:
    """All-time preview lines with kind=txn and a non-zero amount."""
    from app.services.ledger_report_service import LedgerReportService

    kind_key = (kind or "").strip().lower()
    if kind_key not in LEDGER_KINDS:
        return 0
    try:
        with db.session.begin_nested():
            data = LedgerReportService().preview_ledger(
                kind_key,
                int(entity_id),
                date_from=date(2000, 1, 1),
                date_to=date.today(),
            )
        return sum(1 for line in (data.get("lines") or []) if _is_blocking_txn_line(line))
    except (SQLAlchemyError, ValueError, TypeError):
        return 0


def raise_if_ledger_in_use(kind: str, entity_id: int, display_name: str) -> int:
    """Block delete when the ledger has real postings. Opening balance is not a txn."""
    n = count_ledger_txn_lines(kind, entity_id)
    if n:
        name = (display_name or "This master").strip() or "This master"
        raise MasterInUseError(
            (
                f"Stop: '{name}' has {n} ledger transaction(s) and cannot be deleted. "
                "Edit those records first."
            ),
            links=[{"table": "ledger", "label": "Ledger Transaction", "count": n}],
            ledger=ledger_payload(kind, entity_id),
        )
    return n
