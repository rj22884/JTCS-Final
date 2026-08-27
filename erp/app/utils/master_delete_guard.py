"""Block master deletes when the row is referenced by any other table.

Scans SQL Server foreign keys plus columns that share the master PK name
(even without an FK), then optional extra WHERE checks for name-based links.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_TABLE_LABELS = {
    "JTCSDailyTransaction": "Daily Transaction",
    "JTCSDailyTransactionPayment": "Daily Transaction Payment",
    "JtcsBankTransaction": "Bank Transaction",
    "JtcsBankAccountMaster": "Bank Master",
    "FollowupEntryMaster": "Follow-up Work",
    "FollowupEntryStage": "Follow-up Stage",
    "FollowupWorkflowStage": "Follow-up Stage Master",
    "GstInvoice": "GST Invoice",
    "GstInvoiceLine": "GST Invoice Line",
    "WorkMaster": "Work / Category Master",
    "WorkTypeMaster": "Sub Work Master",
    "PrintingScanMaster": "Printing & Scanning",
    "OthersIncomeExpenseMaster": "Income / Expense",
    "OthersIncomeExpenseDetail": "Income / Expense Detail",
    "OthersBankCashTransaction": "Bank / Cash Transaction",
    "ChartOfAccountMaster": "Chart of Account Master",
    "ChartOfAccountGroupLink": "Chart of Account Group",
    "ChartOfGroupMaster": "Chart of Group Master",
    "CustomerMaster": "Customer Master",
    "CustomerGroupMaster": "Customer Group Master",
    "ItemMaster": "Item Master",
    "PurposeMaster": "Purpose Master",
    "RdAccountMaster": "RD Account Master",
    "PaymentModeMaster": "Payment Mode",
    "StampMaster": "Stamp Activity",
    "ECourtSale": "e-Court Sale",
    "CrmTask": "CRM Task",
    "CrmFollowUp": "CRM Follow-up",
    "CrmConversation": "Conversation",
    "CrmLead": "Lead",
    "CrmDocument": "Document",
    "HrEmployee": "HR Employee",
}


class MasterInUseError(ValueError):
    """Raised when a master row is linked from another table."""

    def __init__(
        self,
        message: str,
        *,
        links: list[dict] | None = None,
        usage: dict | None = None,
    ):
        super().__init__(message)
        self.links = list(links or [])
        self.usage = usage if usage is not None else {
            "can_delete": False,
            "links": self.links,
        }


def json_in_use_response(exc: MasterInUseError):
    from flask import jsonify

    payload = {
        "ok": False,
        "error": str(exc),
        "in_use": True,
        "links": exc.links,
    }
    if exc.usage:
        payload["usage"] = exc.usage
    return jsonify(payload), 409


def integrity_blocks_delete(exc: IntegrityError) -> bool:
    raw = str(getattr(exc, "orig", None) or exc).lower()
    return (
        "reference constraint" in raw
        or "conflicted with the reference" in raw
        or "foreign key" in raw
        or "fk_" in raw
    )


def raise_if_integrity_in_use(exc: IntegrityError, display_name: str) -> None:
    if integrity_blocks_delete(exc):
        raise MasterInUseError(
            _stop_message(display_name, []),
            links=[],
        ) from exc
    raise exc


def assert_master_unused(
    *,
    table: str,
    pk_column: str,
    pk_value: int | str,
    display_name: str,
    column_aliases: list[str] | None = None,
    skip_tables: set[str] | None = None,
    extra_checks: list[dict[str, Any]] | None = None,
) -> list[dict]:
    """Raise MasterInUseError if any other table still references this row."""
    links = find_master_usage(
        table=table,
        pk_column=pk_column,
        pk_value=pk_value,
        column_aliases=column_aliases,
        skip_tables=skip_tables,
        extra_checks=extra_checks,
    )
    if links:
        raise MasterInUseError(_stop_message(display_name, links), links=links)
    return links


def find_master_usage(
    *,
    table: str,
    pk_column: str,
    pk_value: int | str,
    column_aliases: list[str] | None = None,
    skip_tables: set[str] | None = None,
    extra_checks: list[dict[str, Any]] | None = None,
) -> list[dict]:
    source = _safe_ident(table)
    pk = _safe_ident(pk_column)
    if not source or not pk:
        return []
    skip = {source, *(skip_tables or set())}
    aliases = list(dict.fromkeys(column_aliases if column_aliases is not None else [pk]))
    aliases = [col for col in (_safe_ident(c) for c in aliases) if col]

    counts: dict[str, int] = {}
    labels: dict[str, str] = {}

    for tbl, col in _catalog_column_refs(aliases):
        if tbl == source and col == pk:
            continue
        if tbl in skip:
            continue
        n = _count_column(tbl, col, pk_value)
        if n:
            _add_count(counts, labels, tbl, n)

    for tbl, col in _catalog_fk_refs(source):
        if tbl in skip:
            continue
        n = _count_column(tbl, col, pk_value)
        if n:
            _add_count(counts, labels, tbl, n)

    for check in extra_checks or []:
        tbl = _safe_ident(check.get("table") or "")
        where_sql = (check.get("where") or "").strip()
        if not tbl or not where_sql:
            continue
        params = check.get("params") or {}
        if any(isinstance(v, str) and not str(v).strip() for v in params.values()):
            continue
        n = _count_where(tbl, where_sql, params)
        if n:
            label = (check.get("label") or "").strip() or _TABLE_LABELS.get(tbl, tbl)
            _add_count(counts, labels, tbl, n, label=label)

    links = [
        {"table": tbl, "label": labels.get(tbl, _TABLE_LABELS.get(tbl, tbl)), "count": counts[tbl]}
        for tbl in sorted(counts, key=lambda name: labels.get(name, name).lower())
    ]
    return links


def _stop_message(display_name: str, links: list[dict]) -> str:
    name = (display_name or "This master").strip() or "This master"
    if not links:
        return (
            f"Stop: '{name}' is linked to other records and cannot be deleted. "
            "Edit those records first."
        )
    parts = [f"{item['label']} ({item['count']})" for item in links[:8]]
    extra = ""
    if len(links) > 8:
        extra = f" and {len(links) - 8} more"
    return (
        f"Stop: '{name}' is linked to other records and cannot be deleted. "
        f"Used in: {', '.join(parts)}{extra}."
    )


def _safe_ident(value: str) -> str:
    text_value = str(value or "").strip().strip("[]")
    if not _IDENT_RE.match(text_value):
        return ""
    return text_value


def _add_count(
    counts: dict[str, int],
    labels: dict[str, str],
    table: str,
    count: int,
    *,
    label: str | None = None,
) -> None:
    counts[table] = counts.get(table, 0) + int(count)
    if label and table not in labels:
        labels[table] = label


def _catalog_column_refs(columns: list[str]) -> list[tuple[str, str]]:
    if not columns:
        return []
    placeholders = ", ".join(f":c{i}" for i in range(len(columns)))
    params = {f"c{i}": col for i, col in enumerate(columns)}
    try:
        rows = db.session.execute(
            text(
                f"""
                SELECT t.name AS table_name, c.name AS column_name
                FROM sys.columns c
                INNER JOIN sys.tables t ON t.object_id = c.object_id
                INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
                WHERE s.name = N'dbo'
                  AND c.name IN ({placeholders})
                """
            ),
            params,
        ).mappings().all()
    except SQLAlchemyError:
        db.session.rollback()
        return []
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        tbl = _safe_ident(row.get("table_name") or "")
        col = _safe_ident(row.get("column_name") or "")
        if not tbl or not col or (tbl, col) in seen:
            continue
        seen.add((tbl, col))
        out.append((tbl, col))
    return out


def _catalog_fk_refs(table: str) -> list[tuple[str, str]]:
    try:
        rows = db.session.execute(
            text(
                """
                SELECT
                    OBJECT_NAME(fk.parent_object_id) AS table_name,
                    COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS column_name
                FROM sys.foreign_keys fk
                INNER JOIN sys.foreign_key_columns fkc
                    ON fkc.constraint_object_id = fk.object_id
                INNER JOIN sys.tables rt ON rt.object_id = fk.referenced_object_id
                INNER JOIN sys.schemas rs ON rs.schema_id = rt.schema_id
                WHERE rs.name = N'dbo'
                  AND rt.name = :table
                """
            ),
            {"table": table},
        ).mappings().all()
    except SQLAlchemyError:
        db.session.rollback()
        return []
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        tbl = _safe_ident(row.get("table_name") or "")
        col = _safe_ident(row.get("column_name") or "")
        if not tbl or not col or (tbl, col) in seen:
            continue
        seen.add((tbl, col))
        out.append((tbl, col))
    return out


def _count_column(table: str, column: str, pk_value: int | str) -> int:
    return _count_where(table, f"[{column}] = :id", {"id": pk_value})


def _count_where(table: str, where_sql: str, params: dict[str, Any]) -> int:
    tbl = _safe_ident(table)
    if not tbl or not (where_sql or "").strip():
        return 0
    try:
        count = db.session.execute(
            text(f"SELECT COUNT(1) FROM dbo.[{tbl}] WHERE {where_sql}"),
            params,
        ).scalar()
        return int(count or 0)
    except SQLAlchemyError:
        db.session.rollback()
        return 0
