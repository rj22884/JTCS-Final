"""Treat ledger money as the delete blocker.

Rule: if opening balance is 0 and there are no non-zero transaction lines,
the master may be permanently deleted (child links for that ledger are purged).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.utils.master_delete_guard import MasterInUseError

LEDGER_KINDS = ("bank", "customer", "work", "item")
_EPS = Decimal("0.0001")


def ledger_payload(kind: str, entity_id: int) -> dict:
    return {"kind": (kind or "").strip().lower(), "id": int(entity_id)}


def _money(value) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def _is_blocking_txn_line(line: dict) -> bool:
    if (line.get("kind") or "txn") != "txn":
        return False
    return abs(_money(line.get("debit"))) > _EPS or abs(_money(line.get("credit"))) > _EPS


def _preview_all_time(kind: str, entity_id: int) -> dict:
    from app.services.ledger_report_service import LedgerReportService

    kind_key = (kind or "").strip().lower()
    if kind_key not in LEDGER_KINDS:
        return {"lines": [], "closing_balance": 0}
    try:
        with db.session.begin_nested():
            return LedgerReportService().preview_ledger(
                kind_key,
                int(entity_id),
                date_from=date(2000, 1, 1),
                date_to=date.today(),
            )
    except (SQLAlchemyError, ValueError, TypeError):
        return {"lines": [], "closing_balance": 0}


def ledger_state(kind: str, entity_id: int) -> dict:
    """Opening amount, txn count, closing, and whether the ledger is money-empty."""
    kind_key = (kind or "").strip().lower()
    data = _preview_all_time(kind, entity_id)
    opening = Decimal("0.00")
    txn_count = 0
    for line in data.get("lines") or []:
        kind_line = (line.get("kind") or "").strip().lower()
        if kind_line == "opening":
            opening = abs(_money(line.get("debit"))) + abs(_money(line.get("credit")))
            if opening <= _EPS:
                # Some previews put signed amount only in closing on the opening row
                opening = abs(_money(line.get("closing_balance") or line.get("balance") or 0))
        elif _is_blocking_txn_line(line):
            txn_count += 1
    closing = abs(_money(data.get("closing_balance")))
    if closing <= _EPS and data.get("lines"):
        last = data["lines"][-1]
        closing = abs(_money(last.get("closing_balance") or last.get("balance") or closing))
    # Also trust master OpeningBalance when present (work / item / bank).
    try:
        with db.session.begin_nested():
            if kind_key == "work":
                ob = db.session.execute(
                    text("SELECT ISNULL(OpeningBalance, 0) FROM dbo.WorkMaster WHERE WorkID = :id"),
                    {"id": int(entity_id)},
                ).scalar()
                opening = max(opening, abs(_money(ob)))
            elif kind_key == "item":
                ob = db.session.execute(
                    text("SELECT ISNULL(OpeningBalance, 0) FROM dbo.ItemMaster WHERE ItemID = :id"),
                    {"id": int(entity_id)},
                ).scalar()
                opening = max(opening, abs(_money(ob)))
            elif kind_key == "bank":
                ob = db.session.execute(
                    text(
                        "SELECT ISNULL(OpeningBalance, 0) FROM dbo.JtcsBankAccountMaster "
                        "WHERE JtcsBankAccountID = :id"
                    ),
                    {"id": int(entity_id)},
                ).scalar()
                opening = max(opening, abs(_money(ob)))
    except SQLAlchemyError:
        pass

    clear = opening <= _EPS and txn_count == 0 and closing <= _EPS
    return {
        "opening": float(opening),
        "txn_count": int(txn_count),
        "closing": float(closing),
        "clear": clear,
    }


def is_ledger_clear(kind: str, entity_id: int) -> bool:
    return bool(ledger_state(kind, entity_id).get("clear"))


def count_ledger_txn_lines(kind: str, entity_id: int) -> int:
    """All-time preview lines with kind=txn and a non-zero amount."""
    return int(ledger_state(kind, entity_id).get("txn_count") or 0)


def raise_if_ledger_in_use(kind: str, entity_id: int, display_name: str) -> int:
    """Block delete when the ledger has opening money or real postings."""
    state = ledger_state(kind, entity_id)
    if state["clear"]:
        return 0
    name = (display_name or "This master").strip() or "This master"
    parts = []
    if state["opening"] > 0:
        parts.append(f"opening balance Rs. {state['opening']:.2f}")
    if state["txn_count"]:
        parts.append(f"{state['txn_count']} ledger transaction(s)")
    if state["closing"] > 0 and not parts:
        parts.append(f"closing balance Rs. {state['closing']:.2f}")
    detail = " and ".join(parts) if parts else "ledger activity"
    raise MasterInUseError(
        (
            f"Stop: '{name}' has {detail} and cannot be deleted. "
            "Edit those records first."
        ),
        links=[{"table": "ledger", "label": "Ledger", "count": max(1, state["txn_count"])}],
        ledger=ledger_payload(kind, entity_id),
    )


def purge_clear_ledger_refs(kind: str, entity_id: int) -> None:
    """Remove child rows that only block delete when the ledger itself is empty."""
    kind_key = (kind or "").strip().lower()
    eid = int(entity_id)
    if kind_key == "work":
        _purge_work_refs(eid)
    elif kind_key == "item":
        _purge_item_refs(eid)
    elif kind_key == "bank":
        _purge_bank_refs(eid)
    elif kind_key == "customer":
        _purge_customer_refs(eid)


def _exec_delete(sql: str, params: dict) -> None:
    try:
        with db.session.begin_nested():
            db.session.execute(text(sql), params)
    except SQLAlchemyError:
        pass


def _purge_work_refs(work_id: int) -> None:
    params = {"id": work_id}
    # Detail lines first (FK to WorkMaster)
    _exec_delete(
        "DELETE FROM dbo.OthersIncomeExpenseDetail WHERE WorkID = :id",
        params,
    )
    # Re-point parent bills that still have other category lines
    _exec_delete(
        """
        UPDATE m
        SET WorkID = d.WorkID
        FROM dbo.OthersIncomeExpenseMaster m
        CROSS APPLY (
            SELECT TOP (1) WorkID
            FROM dbo.OthersIncomeExpenseDetail x
            WHERE x.EntryID = m.EntryID
            ORDER BY x.LineSequence, x.DetailID
        ) d
        WHERE m.WorkID = :id
        """,
        params,
    )
    # Bills left with no lines (or still stuck on this work) — remove
    _exec_delete(
        """
        DELETE FROM dbo.OthersIncomeExpenseMaster
        WHERE WorkID = :id
           OR NOT EXISTS (
                SELECT 1 FROM dbo.OthersIncomeExpenseDetail d
                WHERE d.EntryID = OthersIncomeExpenseMaster.EntryID
           )
        """,
        params,
    )
    _exec_delete(
        "DELETE FROM dbo.PrintingScanMaster WHERE WorkID = :id",
        params,
    )
    _exec_delete(
        "UPDATE dbo.ChartOfAccountMaster SET WorkID = NULL WHERE WorkID = :id",
        params,
    )


def _purge_item_refs(item_id: int) -> None:
    params = {"id": item_id}
    # Only safe when ledger is clear — no billed amounts remain for this item
    _exec_delete("DELETE FROM dbo.GstInvoiceLine WHERE ItemID = :id", params)


def _purge_bank_refs(account_id: int) -> None:
    params = {"id": account_id}
    _exec_delete(
        """
        DELETE FROM dbo.OthersBankCashTransaction
        WHERE DebitBankAccountID = :id OR CreditBankAccountID = :id
        """,
        params,
    )
    _exec_delete(
        """
        UPDATE dbo.PaymentModeMaster
        SET JtcsBankAccountID = NULL
        WHERE JtcsBankAccountID = :id
        """,
        params,
    )


def _purge_customer_refs(customer_id: int) -> None:
    params = {"id": customer_id}
    _exec_delete(
        "UPDATE dbo.OthersIncomeExpenseMaster SET CustomerID = NULL WHERE CustomerID = :id",
        params,
    )
