"""Reports & Analysis → Ledger Report (search + invoice-style preview)."""

from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from xml.dom import minidom

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import text

from app.extensions import db
from app.services.ledger_export_service import LedgerExportService
from app.services.payment_accounting_service import (
    sql_customer_receipt_expr,
    sql_unpaid_followup_exclusion,
)
from app.utils.opening_balance import apply_account_running, is_credit_normal_nature


def _iso(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class LedgerReportService:
    """Ledger search and preview for bank / customer / work-category / item."""

    KINDS = ("bank", "customer", "work", "item")

    @staticmethod
    def _money(value) -> Decimal:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))

    @staticmethod
    def _parse_date(raw: str | None, fallback: date) -> date:
        value = (raw or "").strip()
        if not value:
            return fallback
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return fallback

    @staticmethod
    def _resolve_period(
        date_from: date | None, date_to: date | None
    ) -> tuple[date, date]:
        today = date.today()
        return date_from or date(2000, 1, 1), date_to or today

    def _sort_date_value(self, date_str: str) -> str:
        raw = (date_str or "").strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                continue
        return raw

    def _decorate_line(self, line: dict[str, Any], *, link: dict[str, Any] | None = None) -> dict[str, Any]:
        line["sort_date"] = self._sort_date_value(str(line.get("date") or ""))
        kind = (line.get("kind") or "txn").strip()
        if kind != "txn":
            line["can_edit"] = False
            line["can_delete"] = False
            line["source_url"] = ""
            line["source_module"] = ""
            line["source_module_id"] = ""
            line["work_type"] = ""
            return line
        link = link or {}
        module = (link.get("source_module") or "").strip()
        mid = link.get("source_module_id")
        line["can_edit"] = bool(link.get("can_open") and link.get("source_url"))
        line["can_delete"] = bool(module and mid)
        line["source_url"] = link.get("source_url") or ""
        line["source_module"] = module
        line["source_module_id"] = mid or ""
        line["work_type"] = (link.get("work_type") or "").strip()
        return line

    def _period_fields(self, date_from: date | None, date_to: date | None) -> dict[str, Any]:
        return {
            "date_from": date_from,
            "date_to": date_to,
            "date_from_iso": _iso(date_from),
            "date_to_iso": _iso(date_to),
        }

    @staticmethod
    def _meta_label(item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("label") or "")
        if isinstance(item, (list, tuple)) and item:
            return str(item[0] or "")
        return ""

    def _period_txn_totals(self, lines: list[dict[str, Any]]) -> tuple[Decimal, Decimal]:
        debit = Decimal("0.00")
        credit = Decimal("0.00")
        for line in lines or []:
            if (line.get("kind") or "txn") != "txn":
                continue
            debit += self._money(line.get("debit"))
            credit += self._money(line.get("credit"))
        return self._money(debit), self._money(credit)

    @staticmethod
    def _as_of_display(date_to: Any) -> str:
        if date_to is None or date_to == "":
            return ""
        if hasattr(date_to, "strftime"):
            return date_to.strftime("%d/%m/%Y")
        raw = str(date_to).strip()
        if len(raw) >= 10 and raw[4] == "-":
            try:
                return datetime.strptime(raw[:10], "%Y-%m-%d").date().strftime("%d/%m/%Y")
            except ValueError:
                return raw
        return raw

    @staticmethod
    def _is_closing_meta_label(label: str) -> bool:
        text = (label or "").strip()
        return text in {"Ledger Balance", "Closing Balance"} or text.startswith(
            "Closing Balance as of"
        )

    def _meta_with_period_totals(
        self,
        meta: list,
        lines: list[dict[str, Any]],
        *,
        closing: Any = None,
        date_to: Any = None,
    ) -> list:
        """Refresh period totals and closing-as-of-To-Date without dropping Closing Balance."""
        total_debit, total_credit = self._period_txn_totals(lines)
        totals = {
            "Total Credit": f"{total_credit:,.2f}",
            "Total Debit": f"{total_debit:,.2f}",
        }
        as_of = self._as_of_display(date_to)
        closing_label = f"Closing Balance as of {as_of}" if as_of else "Closing Balance"
        closing_value = None if closing is None else f"{self._money(closing):,.2f}"
        out: list = []
        closing_written = False
        for item in meta or []:
            label = self._meta_label(item)
            if self._is_closing_meta_label(label):
                if closing_value is not None and not closing_written:
                    out.append((closing_label, closing_value))
                    closing_written = True
                continue
            if label in totals:
                out.append((label, totals[label]))
                continue
            out.append(item)
        if closing_value is not None and not closing_written:
            inserted = False
            with_closing: list = []
            for item in out:
                if not inserted and self._meta_label(item) == "Period":
                    with_closing.append((closing_label, closing_value))
                    inserted = True
                with_closing.append(item)
            if not inserted:
                with_closing.append((closing_label, closing_value))
            return with_closing
        return out

    def _dash(self):
        from app.services.dashboard_service import DashboardService

        return DashboardService()

    @staticmethod
    def _fy_start(today: date | None = None) -> date:
        today = today or date.today()
        year = today.year if today.month >= 4 else today.year - 1
        return date(year, 4, 1)

    def search_ledgers(
        self,
        *,
        kind: str | None = None,
        search: str | None = None,
        limit: int = 100,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[dict[str, Any]]:
        kind_key = (kind or "all").strip().lower()
        needle = (search or "").strip()
        listing_all = not needle
        if listing_all:
            lim = 10000
            per_kind = lim if kind_key != "all" else 5000
        else:
            lim = max(1, min(int(limit or 100), 300))
            per_kind = lim if kind_key != "all" else min(lim, 50)
        rows: list[dict[str, Any]] = []

        if kind_key in ("all", "bank"):
            rows.extend(self._search_banks(needle, per_kind))
        if kind_key in ("all", "customer"):
            rows.extend(self._search_customers(needle, per_kind))
        if kind_key in ("all", "work"):
            rows.extend(self._search_works(needle, per_kind))
        if kind_key in ("all", "item"):
            rows.extend(self._search_items(needle, per_kind))

        if not listing_all:
            rows = rows[:lim]
        if date_from is not None or date_to is not None:
            period_from, period_to = self._resolve_period(date_from, date_to)
            self._attach_search_closings(rows, period_from, period_to)
        return rows

    def _search_banks(self, search: str, limit: int) -> list[dict[str, Any]]:
        export = LedgerExportService()
        banks = export.list_bank_accounts(search=search or None)
        result = []
        for row in banks[:limit]:
            if not bool(row.get("active", True)):
                continue
            result.append(
                {
                    "kind": "bank",
                    "id": row["account_id"],
                    "label": row["label"],
                    "subtitle": row.get("account_holder") or row.get("account_type") or "Bank Account",
                    "meta": row.get("masked_account") or "",
                    "txn_count": int(row.get("txn_count") or 0),
                    "active": True,
                }
            )
        return result

    def _search_customers(self, search: str, limit: int) -> list[dict[str, Any]]:
        export = LedgerExportService()
        customers = export.list_customers(search=search or None, limit=limit)
        result = []
        for row in customers:
            if (row.get("status") or "Active").strip().lower() != "active":
                continue
            bits = [b for b in (row.get("mobile_number"), row.get("pan_number")) if b]
            result.append(
                {
                    "kind": "customer",
                    "id": row["customer_id"],
                    "label": row["customer_name"],
                    "subtitle": " · ".join(bits) if bits else "Customer",
                    "meta": row.get("status") or "",
                    "txn_count": int(row.get("txn_count") or 0),
                    "active": True,
                }
            )
        return result

    def _search_works(self, search: str, limit: int) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"lim": limit}
        search_sql = ""
        needle = (search or "").strip()
        if needle:
            params["like"] = f"%{needle}%"
            search_sql = """
              AND (
                w.WorkName LIKE :like
                OR w.LedgerKind LIKE :like
              )
            """
        rows = db.session.execute(
            text(
                f"""
                SELECT TOP (:lim)
                    w.WorkID,
                    w.WorkName,
                    w.LedgerKind,
                    ISNULL(w.ActiveStatus, 1) AS ActiveStatus,
                    (
                        SELECT COUNT(1)
                        FROM dbo.JTCSDailyTransaction d
                        WHERE d.Status = N'Posted'
                          AND (
                            d.WorkType = w.WorkName
                            OR d.SubWorkType = w.WorkName
                            OR d.SubWorkType LIKE N'%' + w.WorkName + N'%'
                          )
                    ) AS txn_count
                FROM dbo.WorkMaster w
                WHERE ISNULL(w.ActiveStatus, 1) = 1
                  {search_sql}
                ORDER BY
                    CASE WHEN ISNULL(w.ActiveStatus, 1) = 1 THEN 0 ELSE 1 END,
                    w.WorkName,
                    w.WorkID
                """
            ),
            params,
        ).mappings().all()
        return [
            {
                "kind": "work",
                "id": int(row["WorkID"]),
                "label": (row["WorkName"] or "").strip(),
                "subtitle": f"Work / Category · {(row['LedgerKind'] or '').strip() or '—'}",
                "meta": (row["LedgerKind"] or "").strip(),
                "txn_count": int(row["txn_count"] or 0),
                "active": bool(row["ActiveStatus"]),
            }
            for row in rows
        ]

    def _search_items(self, search: str, limit: int) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"lim": limit}
        search_sql = ""
        needle = (search or "").strip()
        if needle:
            params["like"] = f"%{needle}%"
            search_sql = """
              AND (
                i.ItemCode LIKE :like
                OR i.ItemName LIKE :like
                OR ISNULL(i.HsnSac, N'') LIKE :like
              )
            """
        rows = db.session.execute(
            text(
                f"""
                SELECT TOP (:lim)
                    i.ItemID,
                    i.ItemCode,
                    i.ItemName,
                    i.HsnSac,
                    ISNULL(i.IsActive, 1) AS IsActive,
                    (
                        SELECT COUNT(1)
                        FROM dbo.GstInvoiceLine l
                        WHERE l.ItemID = i.ItemID
                    ) AS txn_count
                FROM dbo.ItemMaster i
                WHERE ISNULL(i.IsActive, 1) = 1
                  {search_sql}
                ORDER BY
                    CASE WHEN ISNULL(i.IsActive, 1) = 1 THEN 0 ELSE 1 END,
                    i.OrderNo,
                    i.ItemName,
                    i.ItemID
                """
            ),
            params,
        ).mappings().all()
        return [
            {
                "kind": "item",
                "id": int(row["ItemID"]),
                "label": (row["ItemName"] or "").strip(),
                "subtitle": f"Item · {(row['ItemCode'] or '').strip()}"
                + (f" · HSN/SAC {(row['HsnSac'] or '').strip()}" if row["HsnSac"] else ""),
                "meta": (row["ItemCode"] or "").strip(),
                "txn_count": int(row["txn_count"] or 0),
                "active": bool(row["IsActive"]),
            }
            for row in rows
        ]

    @staticmethod
    def _sql_id_list(ids: list[Any]) -> str:
        clean: list[int] = []
        seen: set[int] = set()
        for raw in ids:
            try:
                n = int(raw)
            except (TypeError, ValueError):
                continue
            if n <= 0 or n in seen:
                continue
            seen.add(n)
            clean.append(n)
        return ", ".join(str(n) for n in clean)

    @staticmethod
    def _dr_cr_side(amount: Decimal, *, credit_normal: bool = False) -> str:
        if abs(amount) < Decimal("0.01"):
            return ""
        if credit_normal:
            return "Cr" if amount > 0 else "Dr"
        return "Dr" if amount > 0 else "Cr"

    def _attach_search_closings(
        self, rows: list[dict[str, Any]], date_from: date, date_to: date
    ) -> None:
        """Add period closing (as of To Date) for the search grid."""
        for row in rows:
            row.setdefault("closing", None)
        by_kind: dict[str, list[int]] = {"bank": [], "customer": [], "work": [], "item": []}
        for row in rows:
            kind = (row.get("kind") or "").strip().lower()
            if kind not in by_kind:
                continue
            try:
                by_kind[kind].append(int(row.get("id")))
            except (TypeError, ValueError):
                continue

        closings: dict[tuple[str, int], dict[str, Any]] = {}
        if by_kind["bank"]:
            closings.update(self._search_bank_closings(by_kind["bank"], date_from, date_to))
        if by_kind["customer"]:
            closings.update(self._search_customer_closings(by_kind["customer"], date_from, date_to))
        if by_kind["work"]:
            closings.update(self._search_work_closings(by_kind["work"], date_from, date_to))
        if by_kind["item"]:
            closings.update(self._search_item_closings(by_kind["item"], date_from, date_to))

        for row in rows:
            kind = (row.get("kind") or "").strip().lower()
            try:
                key = (kind, int(row.get("id")))
            except (TypeError, ValueError):
                continue
            info = closings.get(key)
            if not info:
                continue
            amount = self._money(info.get("amount"))
            row["closing"] = float(amount)
            row["closing_dr_cr"] = info.get("dr_cr") or self._dr_cr_side(amount)

    def _search_bank_closings(
        self, ids: list[int], date_from: date, date_to: date
    ) -> dict[tuple[str, int], dict[str, Any]]:
        id_sql = self._sql_id_list(ids)
        if not id_sql:
            return {}
        group_select = """
                    CAST(NULL AS NVARCHAR(20)) AS UnderType,
                    CAST(N'Asset' AS NVARCHAR(20)) AS GroupNature
        """
        group_join = ""
        try:
            has_group = bool(
                db.session.execute(
                    text(
                        """
                        SELECT CASE
                            WHEN COL_LENGTH(N'dbo.JtcsBankAccountMaster', N'ChartGroupID') IS NULL THEN 0
                            WHEN OBJECT_ID(N'dbo.ChartOfGroupMaster', N'U') IS NULL THEN 0
                            ELSE 1
                        END
                        """
                    )
                ).scalar()
            )
        except Exception:
            db.session.rollback()
            has_group = False
        if has_group:
            group_select = """
                    g.UnderType,
                    ISNULL(
                        NULLIF(g.GroupNature, N''),
                        CASE
                            WHEN g.UnderType = N'Liabilities' THEN N'Liability'
                            WHEN g.UnderType = N'Assets' THEN N'Asset'
                            ELSE N'Asset'
                        END
                    ) AS GroupNature
            """
            group_join = "LEFT JOIN dbo.ChartOfGroupMaster g ON g.GroupID = a.ChartGroupID"
        date_to_next = date_to + timedelta(days=1)
        try:
            rows = db.session.execute(
                text(
                    f"""
                    SELECT
                        a.JtcsBankAccountID AS account_id,
                        CASE
                            WHEN a.OpeningBalanceDate IS NULL OR a.OpeningBalanceDate <= :date_from
                            THEN ISNULL(a.OpeningBalance, 0)
                            ELSE 0
                        END AS opening_balance,
                        ISNULL((
                            SELECT SUM(ISNULL(t.Debit, 0))
                            FROM dbo.JtcsBankTransaction t
                            WHERE t.JtcsBankAccountID = a.JtcsBankAccountID
                              AND t.TransactionDate >= ISNULL(a.OpeningBalanceDate, '20000101')
                              AND t.TransactionDate < :date_to_next
                        ), 0) AS debit_sum,
                        ISNULL((
                            SELECT SUM(ISNULL(t.Credit, 0))
                            FROM dbo.JtcsBankTransaction t
                            WHERE t.JtcsBankAccountID = a.JtcsBankAccountID
                              AND t.TransactionDate >= ISNULL(a.OpeningBalanceDate, '20000101')
                              AND t.TransactionDate < :date_to_next
                        ), 0) AS credit_sum,
                        {group_select}
                    FROM dbo.JtcsBankAccountMaster a
                    {group_join}
                    WHERE a.JtcsBankAccountID IN ({id_sql})
                    """
                ),
                {"date_from": date_from, "date_to_next": date_to_next},
            ).mappings().all()
        except Exception:
            db.session.rollback()
            return {}
        result: dict[tuple[str, int], dict[str, Any]] = {}
        for row in rows:
            credit_normal = is_credit_normal_nature(row.get("GroupNature"), row.get("UnderType"))
            closing = apply_account_running(
                self._money(row["opening_balance"]),
                self._money(row["debit_sum"]),
                self._money(row["credit_sum"]),
                credit_normal=credit_normal,
            )
            result[("bank", int(row["account_id"]))] = {
                "amount": closing,
                "dr_cr": self._dr_cr_side(closing, credit_normal=credit_normal),
            }
        return result

    def _search_customer_closings(
        self, ids: list[int], date_from: date, date_to: date
    ) -> dict[tuple[str, int], dict[str, Any]]:
        id_sql = self._sql_id_list(ids)
        if not id_sql:
            return {}
        try:
            has_ob = bool(
                db.session.execute(
                    text(
                        "SELECT CASE WHEN COL_LENGTH(N'dbo.CustomerMaster', N'OpeningBalance') "
                        "IS NULL THEN 0 ELSE 1 END"
                    )
                ).scalar()
            )
        except Exception:
            db.session.rollback()
            has_ob = False

        openings: dict[int, Decimal] = {}
        asset_meta: dict[int, dict[str, Any]] = {}
        if has_ob:
            try:
                from app.repositories.customer_repository import CustomerRepository

                CustomerRepository().ensure_schema()
            except Exception:
                db.session.rollback()
            try:
                for row in db.session.execute(
                    text(
                        f"""
                        SELECT
                            c.CustomerID,
                            ISNULL(c.OpeningBalance, 0) AS OpeningBalance,
                            c.OpeningBalanceDate,
                            c.OpeningBalanceDrCr,
                            c.PurchaseDate,
                            c.DepreciationRate,
                            c.AppreciationRate
                        FROM dbo.CustomerMaster c
                        WHERE c.CustomerID IN ({id_sql})
                        """
                    )
                ).mappings().all():
                    cid = int(row["CustomerID"])
                    ob_date = row["OpeningBalanceDate"]
                    if hasattr(ob_date, "date"):
                        ob_date = ob_date.date()
                    ob_amount = self._money(row["OpeningBalance"])
                    ob_type = (row["OpeningBalanceDrCr"] or "Dr").strip()
                    signed = ob_amount if ob_type.upper().startswith("D") else -ob_amount
                    if ob_amount != 0 and (ob_date is None or ob_date <= date_from):
                        openings[cid] = signed
                    else:
                        openings[cid] = Decimal("0.00")
                    asset_meta[cid] = {
                        "opening_date": ob_date,
                        "purchase_date": row.get("PurchaseDate"),
                        "depreciation_rate": self._money(row.get("DepreciationRate")),
                        "appreciation_rate": self._money(row.get("AppreciationRate")),
                    }
            except Exception:
                db.session.rollback()

        ob_date_sql = ""
        if has_ob:
            ob_date_sql = "AND (c.OpeningBalanceDate IS NULL OR d.TransactionDate > c.OpeningBalanceDate)"
        billed: dict[int, Decimal] = {}
        received: dict[int, Decimal] = {}
        try:
            for row in db.session.execute(
                text(
                    f"""
                    SELECT
                        d.CustomerID,
                        ISNULL(SUM(ISNULL(d.SaleAmount, 0) + ISNULL(d.IncomeAmount, 0)), 0) AS billed,
                        ISNULL(SUM({sql_customer_receipt_expr("d", "b")}), 0) AS received
                    FROM dbo.JTCSDailyTransaction d
                    LEFT JOIN dbo.JtcsBankTransaction b
                        ON b.JtcsBankTransactionID = d.BankTransactionID
                    INNER JOIN dbo.CustomerMaster c ON c.CustomerID = d.CustomerID
                    WHERE d.CustomerID IN ({id_sql})
                      AND d.Status = N'Posted'
                      AND d.TransactionDate <= :date_to
                      {ob_date_sql}
                    GROUP BY d.CustomerID
                    """
                ),
                {"date_to": date_to},
            ).mappings().all():
                cid = int(row["CustomerID"])
                billed[cid] = self._money(row["billed"])
                received[cid] = self._money(row["received"])
        except Exception:
            db.session.rollback()

        followup: dict[int, Decimal] = {}
        fu_date_sql = ""
        if has_ob:
            fu_date_sql = (
                "AND (c.OpeningBalanceDate IS NULL "
                "OR ISNULL(f.BillDate, f.WorkDate) > c.OpeningBalanceDate)"
            )
        try:
            if db.session.execute(text("SELECT OBJECT_ID(N'dbo.FollowupEntryMaster', N'U')")).scalar():
                for row in db.session.execute(
                    text(
                        f"""
                        SELECT
                            f.CustomerID,
                            ISNULL(SUM(ISNULL(f.BillAmount, 0)), 0) AS billed
                        FROM dbo.FollowupEntryMaster f
                        INNER JOIN dbo.CustomerMaster c ON c.CustomerID = f.CustomerID
                        WHERE f.CustomerID IN ({id_sql})
                          AND ISNULL(f.IsActive, 1) = 1
                          AND f.BillNo IS NOT NULL
                          AND LTRIM(RTRIM(f.BillNo)) <> N''
                          AND ISNULL(f.BillAmount, 0) > 0
                          AND ISNULL(f.BillDate, f.WorkDate) <= :date_to
                          {fu_date_sql}
                          {sql_unpaid_followup_exclusion()}
                        GROUP BY f.CustomerID
                        """
                    ),
                    {"date_to": date_to},
                ).mappings().all():
                    followup[int(row["CustomerID"])] = self._money(row["billed"])
        except Exception:
            db.session.rollback()

        result: dict[tuple[str, int], dict[str, Any]] = {}
        for raw_id in ids:
            try:
                cid = int(raw_id)
            except (TypeError, ValueError):
                continue
            closing = self._money(
                openings.get(cid, Decimal("0.00"))
                + billed.get(cid, Decimal("0.00"))
                + followup.get(cid, Decimal("0.00"))
                - received.get(cid, Decimal("0.00"))
            )
            result[("customer", cid)] = {
                "amount": closing,
                "dr_cr": self._dr_cr_side(closing),
            }
        self._adjust_customer_asset_class_closings(result, asset_meta, date_to)
        return result

    def _customer_asset_class_calc(
        self,
        group_ids: list[int],
        meta: dict[str, Any],
        book: Decimal,
        date_to: date,
        fa_ids: set[int],
        inv_ids: set[int],
        dep_svc,
    ) -> dict[str, Any] | None:
        if book <= Decimal("0.00") or not group_ids:
            return None
        gids = []
        for raw in group_ids:
            try:
                gids.append(int(raw))
            except (TypeError, ValueError):
                continue
        is_fa = any(gid in fa_ids for gid in gids)
        is_inv = (not is_fa) and any(gid in inv_ids for gid in gids)
        if not is_fa and not is_inv:
            return None
        rate = self._money(
            meta.get("depreciation_rate") if is_fa else meta.get("appreciation_rate")
        )
        if rate <= Decimal("0.00"):
            return None
        purchase = meta.get("purchase_date")
        opening = meta.get("opening_date")
        if purchase is None and opening is None:
            return None
        if is_fa:
            calc = dep_svc.calculate(
                cost=book,
                rate=rate,
                purchase_date=purchase,
                opening_date=opening,
                as_of=date_to,
            )
            cy = self._money(calc["current_year"])
            if cy <= Decimal("0.00"):
                return None
            return {
                "kind": "depreciation",
                "rate": rate,
                "current_year": cy,
                "closing": self._money(book - cy),
            }
        calc = dep_svc.calculate_appreciation(
            cost=book,
            rate=rate,
            purchase_date=purchase,
            opening_date=opening,
            as_of=date_to,
        )
        cy = self._money(calc["current_year"])
        if cy <= Decimal("0.00"):
            return None
        return {
            "kind": "appreciation",
            "rate": rate,
            "current_year": cy,
            "closing": self._money(book + cy),
        }

    def _adjust_customer_asset_class_closings(
        self,
        result: dict[tuple[str, int], dict[str, Any]],
        asset_meta: dict[int, dict[str, Any]],
        date_to: date,
    ) -> None:
        if not result:
            return
        try:
            from app.services.depreciation_service import DepreciationService

            dep_svc = DepreciationService()
            fa_ids = dep_svc.fixed_asset_group_ids()
            inv_ids = dep_svc.investment_group_ids()
        except Exception:
            db.session.rollback()
            return
        if not fa_ids and not inv_ids:
            return
        ids = [cid for (_kind, cid) in result.keys()]
        mapping: dict[int, dict] = {}
        try:
            from app.services.chart_account_service import ChartAccountService

            mapping = ChartAccountService().repo.map_customer_chart_groups(ids)
        except Exception:
            db.session.rollback()
            mapping = {}
        for key, row in result.items():
            cid = key[1]
            adj = self._customer_asset_class_calc(
                (mapping.get(cid) or {}).get("chart_group_ids") or [],
                asset_meta.get(cid) or {},
                self._money(row.get("amount")),
                date_to,
                fa_ids,
                inv_ids,
                dep_svc,
            )
            if not adj:
                continue
            row["amount"] = adj["closing"]
            row["dr_cr"] = self._dr_cr_side(adj["closing"])

    def _append_customer_asset_class_line(
        self, data: dict[str, Any], customer_id: int, date_to: date | None
    ) -> dict[str, Any]:
        as_of = date_to or date.today()
        try:
            from app.repositories.customer_repository import CustomerRepository

            CustomerRepository().ensure_schema()
            from app.services.depreciation_service import DepreciationService

            dep_svc = DepreciationService()
            fa_ids = dep_svc.fixed_asset_group_ids()
            inv_ids = dep_svc.investment_group_ids()
            from app.services.chart_account_service import ChartAccountService

            linked = ChartAccountService().get_customer_record(int(customer_id))
            row = db.session.execute(
                text(
                    """
                    SELECT
                        ISNULL(OpeningBalance, 0) AS OpeningBalance,
                        OpeningBalanceDate,
                        PurchaseDate,
                        DepreciationRate,
                        AppreciationRate
                    FROM dbo.CustomerMaster
                    WHERE CustomerID = :id
                    """
                ),
                {"id": int(customer_id)},
            ).mappings().first()
        except Exception:
            db.session.rollback()
            return data
        if not row:
            return data
        book = self._money(data.get("closing"))
        adj = self._customer_asset_class_calc(
            list(linked.get("group_ids") or []),
            {
                "opening_date": row.get("OpeningBalanceDate"),
                "purchase_date": row.get("PurchaseDate"),
                "depreciation_rate": self._money(row.get("DepreciationRate")),
                "appreciation_rate": self._money(row.get("AppreciationRate")),
            },
            book,
            as_of,
            fa_ids,
            inv_ids,
            dep_svc,
        )
        if not adj:
            return data
        running = adj["closing"]
        desc = (
            f"Depreciation @ {adj['rate']}% WDV"
            if adj["kind"] == "depreciation"
            else f"Appreciation @ {adj['rate']}%"
        )
        debit = Decimal("0.00") if adj["kind"] == "depreciation" else adj["current_year"]
        credit = adj["current_year"] if adj["kind"] == "depreciation" else Decimal("0.00")
        data.setdefault("lines", []).append(
            self._decorate_line(
                {
                    "date": as_of.strftime("%d/%m/%Y"),
                    "description": desc,
                    "debit": debit,
                    "credit": credit,
                    "balance": running,
                    "kind": "txn",
                }
            )
        )
        data["closing"] = running
        data["meta"] = self._meta_with_period_totals(
            data.get("meta") or [],
            data.get("lines") or [],
            closing=running,
            date_to=data.get("date_to"),
        )
        return data

    def _search_work_closings(
        self, ids: list[int], date_from: date, date_to: date
    ) -> dict[tuple[str, int], dict[str, Any]]:
        id_sql = self._sql_id_list(ids)
        if not id_sql:
            return {}
        try:
            rows = db.session.execute(
                text(
                    f"""
                    SELECT
                        w.WorkID,
                        w.LedgerKind,
                        ISNULL(SUM(CASE
                            WHEN d.TransactionDate < :date_from
                            THEN ISNULL(d.SaleAmount, 0) + ISNULL(d.IncomeAmount, 0)
                            ELSE 0
                        END), 0) AS prior_income,
                        ISNULL(SUM(CASE
                            WHEN d.TransactionDate < :date_from
                            THEN ISNULL(d.ExpenseAmount, 0)
                            ELSE 0
                        END), 0) AS prior_expense,
                        ISNULL(SUM(CASE
                            WHEN d.TransactionDate < :date_from
                            THEN ISNULL(pay.paid_amt, 0)
                            ELSE 0
                        END), 0) AS prior_paid,
                        ISNULL(SUM(CASE
                            WHEN d.TransactionDate >= :date_from
                            THEN ISNULL(d.SaleAmount, 0) + ISNULL(d.IncomeAmount, 0)
                            ELSE 0
                        END), 0) AS period_income,
                        ISNULL(SUM(CASE
                            WHEN d.TransactionDate >= :date_from
                            THEN ISNULL(d.ExpenseAmount, 0)
                            ELSE 0
                        END), 0) AS period_expense,
                        ISNULL(SUM(CASE
                            WHEN d.TransactionDate >= :date_from
                            THEN ISNULL(pay.paid_amt, 0)
                            ELSE 0
                        END), 0) AS period_paid
                    FROM dbo.WorkMaster w
                    LEFT JOIN dbo.JTCSDailyTransaction d
                        ON d.Status = N'Posted'
                       AND d.TransactionDate <= :date_to
                       AND (
                            d.WorkType = w.WorkName
                         OR d.SubWorkType = w.WorkName
                         OR d.SubWorkType LIKE N'%' + w.WorkName + N'%'
                       )
                    LEFT JOIN (
                        SELECT TransactionID, SUM(Amount) AS paid_amt
                        FROM dbo.JTCSDailyTransactionPayment
                        GROUP BY TransactionID
                    ) pay ON pay.TransactionID = d.TransactionID
                    WHERE w.WorkID IN ({id_sql})
                    GROUP BY w.WorkID, w.LedgerKind
                    """
                ),
                {"date_from": date_from, "date_to": date_to},
            ).mappings().all()
        except Exception:
            db.session.rollback()
            return {}
        result: dict[tuple[str, int], dict[str, Any]] = {}
        for row in rows:
            ledger_kind = (row["LedgerKind"] or "").strip().upper()
            if ledger_kind.startswith("E"):
                prior = self._money(row["prior_expense"]) - self._money(row["prior_paid"])
                closing = self._money(
                    prior + self._money(row["period_expense"]) - self._money(row["period_paid"])
                )
            else:
                prior = self._money(row["prior_income"]) - self._money(row["prior_paid"])
                closing = self._money(
                    prior + self._money(row["period_paid"]) - self._money(row["period_income"])
                )
            result[("work", int(row["WorkID"]))] = {
                "amount": closing,
                "dr_cr": self._dr_cr_side(closing),
            }
        return result

    def _search_item_closings(
        self, ids: list[int], date_from: date, date_to: date
    ) -> dict[tuple[str, int], dict[str, Any]]:
        id_sql = self._sql_id_list(ids)
        if not id_sql:
            return {}
        try:
            from app.repositories.item_master_repository import ItemMasterRepository

            ItemMasterRepository().ensure_schema()
        except Exception:
            db.session.rollback()
        try:
            rows = db.session.execute(
                text(
                    f"""
                    SELECT
                        i.ItemID,
                        ISNULL(i.OpeningBalance, 0) AS OpeningBalance,
                        i.OpeningBalanceDate,
                        i.PurchaseDate,
                        i.DepreciationRate,
                        i.AppreciationRate,
                        i.ChartGroupID,
                        ISNULL((
                            SELECT SUM(ISNULL(l.TaxableValue, 0))
                            FROM dbo.GstInvoiceLine l
                            INNER JOIN dbo.GstInvoice inv ON inv.InvoiceID = l.InvoiceID
                            WHERE l.ItemID = i.ItemID
                              AND inv.InvoiceDate <= :date_to
                        ), 0) AS billed
                    FROM dbo.ItemMaster i
                    WHERE i.ItemID IN ({id_sql})
                    """
                ),
                {"date_to": date_to},
            ).mappings().all()
        except Exception:
            db.session.rollback()
            return {}
        result: dict[tuple[str, int], dict[str, Any]] = {}
        fa_ids: set[int] = set()
        inv_ids: set[int] = set()
        dep_svc = None
        try:
            from app.services.depreciation_service import DepreciationService

            dep_svc = DepreciationService()
            fa_ids = dep_svc.fixed_asset_group_ids()
            inv_ids = dep_svc.investment_group_ids()
        except Exception:
            db.session.rollback()
            dep_svc = None
        for row in rows:
            ob_date = row["OpeningBalanceDate"]
            if hasattr(ob_date, "date"):
                ob_date = ob_date.date()
            opening = Decimal("0.00")
            if ob_date is None or ob_date <= date_from:
                opening = self._money(row["OpeningBalance"])
            closing = self._money(opening - self._money(row["billed"]))
            gid = row.get("ChartGroupID")
            if dep_svc and gid and closing > 0:
                try:
                    gid_int = int(gid)
                except (TypeError, ValueError):
                    gid_int = 0
                if gid_int in fa_ids:
                    rate = self._money(row.get("DepreciationRate"))
                    if rate > 0:
                        calc = dep_svc.calculate(
                            cost=closing,
                            rate=rate,
                            purchase_date=row.get("PurchaseDate"),
                            opening_date=ob_date,
                            as_of=date_to,
                        )
                        closing = self._money(calc["wdv"])
                elif gid_int in inv_ids:
                    rate = self._money(row.get("AppreciationRate"))
                    if rate > 0:
                        calc = dep_svc.calculate_appreciation(
                            cost=closing,
                            rate=rate,
                            purchase_date=row.get("PurchaseDate"),
                            opening_date=ob_date,
                            as_of=date_to,
                        )
                        closing = self._money(calc["current_value"])
            result[("item", int(row["ItemID"]))] = {
                "amount": closing,
                "dr_cr": self._dr_cr_side(closing),
            }
        return result

    def preview_ledger(
        self,
        kind: str,
        entity_id: int,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        kind_key = (kind or "").strip().lower()
        if kind_key not in self.KINDS:
            raise ValueError("Invalid ledger type.")
        if kind_key == "bank":
            return self._simplify_export_ledger(
                LedgerExportService().bank_ledger_preview_data(
                    entity_id, date_from=date_from, date_to=date_to
                ),
                title="Bank Account Ledger",
            )
        if kind_key == "customer":
            data = self._simplify_export_ledger(
                LedgerExportService().customer_ledger_preview_data(
                    entity_id, date_from=date_from, date_to=date_to
                ),
                title="Customer Ledger",
            )
            return self._append_customer_asset_class_line(data, entity_id, date_to)
        if kind_key == "work":
            return self._work_ledger_data(entity_id, date_from=date_from, date_to=date_to)
        return self._item_ledger_data(entity_id, date_from=date_from, date_to=date_to)

    def _prefetch_daily_source_rows(self, record_ids: list[int]) -> dict[int, dict[str, Any]]:
        ids = []
        seen: set[int] = set()
        for raw in record_ids:
            try:
                tid = int(raw)
            except (TypeError, ValueError):
                continue
            if tid <= 0 or tid in seen:
                continue
            seen.add(tid)
            ids.append(tid)
        if not ids:
            return {}
        result: dict[int, dict[str, Any]] = {}
        chunk_size = 400
        for start in range(0, len(ids), chunk_size):
            chunk = ids[start : start + chunk_size]
            placeholders = ", ".join(str(tid) for tid in chunk)
            rows = db.session.execute(
                text(
                    f"""
                    SELECT TransactionID, WorkType, SubWorkType, StampID, ReferenceNo
                    FROM JTCSDailyTransaction
                    WHERE TransactionID IN ({placeholders})
                    """
                )
            ).mappings().all()
            for row in rows:
                result[int(row["TransactionID"])] = dict(row)
        return result

    def _simplify_export_ledger(self, data: dict[str, Any], *, title: str) -> dict[str, Any]:
        """Map admin export ledger rows to Date / Description / Debit / Credit / Closing Balance."""
        dash = self._dash()
        kind_key = (data.get("kind") or "").strip().lower()
        daily_map: dict[int, dict[str, Any]] = {}
        if kind_key == "bank":
            daily_map = self._prefetch_daily_source_rows(
                [
                    line.get("source_record_id")
                    for line in (data.get("lines") or [])
                    if (line.get("kind") or "txn") == "txn"
                    and (line.get("source") or "").strip().lower()
                    in {"", "jtcsdailytransaction", "shcil"}
                    and line.get("source_record_id")
                ]
            )
        lines: list[dict[str, Any]] = []
        for line in data.get("lines") or []:
            kind = (line.get("kind") or "txn").strip()
            if kind in ("day_total", "month_total", "desc_total"):
                continue
            desc_parts = []
            if line.get("description"):
                desc_parts.append(str(line["description"]).strip())
            if line.get("bill"):
                desc_parts.append(f"Ref: {str(line['bill']).strip()}")
            if line.get("work"):
                desc_parts.append(str(line["work"]).strip())
            if line.get("reference") and kind == "txn":
                desc_parts.append(str(line["reference"]).strip())
            out = {
                "date": line.get("date") or "",
                "description": " · ".join([p for p in desc_parts if p]) or "—",
                "debit": line.get("debit"),
                "credit": line.get("credit"),
                "balance": line.get("balance"),
                "kind": kind,
            }
            link = None
            if kind == "txn":
                try:
                    if kind_key == "bank":
                        rec_id = line.get("source_record_id")
                        rec_int = int(rec_id) if rec_id else 0
                        daily = daily_map.get(rec_int)
                        if daily:
                            link = dash._source_link_for_daily(
                                transaction_id=int(daily["TransactionID"]),
                                work_type=daily.get("WorkType"),
                                sub_work_type=daily.get("SubWorkType"),
                                stamp_id=daily.get("StampID"),
                                reference=daily.get("ReferenceNo"),
                            )
                        else:
                            link = dash._source_link_for_bank_leg(
                                source_table=line.get("source"),
                                source_record_id=rec_int if rec_int else None,
                                bank_transaction_id=line.get("bank_transaction_id"),
                            )
                    elif kind_key == "customer":
                        txn_id = line.get("transaction_id")
                        stamp_id = line.get("stamp_id")
                        txn_int = int(txn_id) if txn_id not in (None, "") else 0
                        link = dash._source_link_for_daily(
                            transaction_id=txn_int if txn_int > 0 else None,
                            work_type=line.get("work_type"),
                            sub_work_type=line.get("sub_work_type"),
                            stamp_id=int(stamp_id) if stamp_id else None,
                            reference=line.get("bill") or line.get("reference"),
                        )
                        if not link.get("can_open") and line.get("obc_entry_id"):
                            link = dash._source_link_for_bank_cash_entry(int(line["obc_entry_id"]))
                except Exception:
                    link = None
            lines.append(self._decorate_line(out, link=link))
        period = self._period_fields(data.get("date_from"), data.get("date_to"))
        return {
            "kind": data.get("kind") or "ledger",
            "title": title,
            "entity_name": data.get("entity_name") or "",
            "entity_id": data.get("entity_id"),
            "meta": self._meta_with_period_totals(
                data.get("meta") or [],
                lines,
                closing=data.get("closing"),
                date_to=data.get("date_to"),
            ),
            "headers": ["Date", "Description", "Debit", "Credit", "Closing Balance"],
            "lines": lines,
            "closing": data.get("closing") or Decimal("0.00"),
            **period,
        }

    def _work_ledger_data(
        self,
        work_id: int,
        *,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        work = db.session.execute(
            text(
                """
                SELECT WorkID, WorkName, LedgerKind, ISNULL(ActiveStatus, 1) AS ActiveStatus
                FROM dbo.WorkMaster
                WHERE WorkID = :work_id
                """
            ),
            {"work_id": work_id},
        ).mappings().first()
        if work is None:
            raise ValueError("Work / Category not found.")

        date_from, date_to = self._resolve_period(date_from, date_to)
        work_name = (work["WorkName"] or "").strip()
        ledger_kind = (work["LedgerKind"] or "").strip().upper()

        # SQL Server forbids SUM( (SELECT SUM(...)) ); join payment totals instead.
        prior = db.session.execute(
            text(
                """
                SELECT
                    ISNULL(SUM(ISNULL(d.SaleAmount, 0) + ISNULL(d.IncomeAmount, 0)), 0) AS income_amt,
                    ISNULL(SUM(ISNULL(d.ExpenseAmount, 0)), 0) AS expense_amt,
                    ISNULL(SUM(ISNULL(pay.paid_amt, 0)), 0) AS paid_amt
                FROM dbo.JTCSDailyTransaction d
                LEFT JOIN (
                    SELECT TransactionID, SUM(Amount) AS paid_amt
                    FROM dbo.JTCSDailyTransactionPayment
                    GROUP BY TransactionID
                ) pay ON pay.TransactionID = d.TransactionID
                WHERE d.Status = N'Posted'
                  AND d.TransactionDate < :date_from
                  AND (
                    d.WorkType = :work_name
                    OR d.SubWorkType = :work_name
                    OR d.SubWorkType LIKE N'%' + :work_name + N'%'
                  )
                """
            ),
            {"work_name": work_name, "date_from": date_from},
        ).mappings().first()

        prior_income = self._money(prior["income_amt"] if prior else 0)
        prior_expense = self._money(prior["expense_amt"] if prior else 0)
        prior_paid = self._money(prior["paid_amt"] if prior else 0)
        # Income/Misc → credit nature; Expense → debit nature
        if ledger_kind.startswith("E"):
            opening = self._money(prior_expense - prior_paid)
        else:
            opening = self._money(prior_income - prior_paid)

        rows = db.session.execute(
            text(
                """
                SELECT
                    d.TransactionID, d.TransactionDate, d.WorkType, d.SubWorkType,
                    d.StampID, d.ReferenceNo, d.Description, d.Remarks,
                    ISNULL(d.SaleAmount, 0) AS SaleAmount,
                    ISNULL(d.IncomeAmount, 0) AS IncomeAmount,
                    ISNULL(d.ExpenseAmount, 0) AS ExpenseAmount,
                    (
                        SELECT ISNULL(SUM(p.Amount), 0)
                        FROM dbo.JTCSDailyTransactionPayment p
                        WHERE p.TransactionID = d.TransactionID
                    ) AS PaymentTotal
                FROM dbo.JTCSDailyTransaction d
                WHERE d.Status = N'Posted'
                  AND d.TransactionDate >= :date_from
                  AND d.TransactionDate <= :date_to
                  AND (
                    d.WorkType = :work_name
                    OR d.SubWorkType = :work_name
                    OR d.SubWorkType LIKE N'%' + :work_name + N'%'
                  )
                ORDER BY d.TransactionDate ASC, d.TransactionID ASC
                """
            ),
            {"work_name": work_name, "date_from": date_from, "date_to": date_to},
        ).mappings().all()

        lines: list[dict[str, Any]] = []
        running = opening
        lines.append(
            self._decorate_line(
                {
                    "date": date_from.strftime("%d/%m/%Y"),
                    "description": "Opening Balance",
                    "debit": Decimal("0.00"),
                    "credit": Decimal("0.00"),
                    "balance": running,
                    "kind": "opening",
                }
            )
        )

        dash = self._dash()
        for row in rows:
            income = self._money(row["SaleAmount"]) + self._money(row["IncomeAmount"])
            expense = self._money(row["ExpenseAmount"])
            payment = self._money(row["PaymentTotal"])
            if ledger_kind.startswith("E"):
                debit = expense
                credit = payment
            else:
                debit = payment
                credit = income
            if debit == 0 and credit == 0:
                # Fallback: show whichever amount exists
                if income > 0:
                    credit = income
                elif expense > 0:
                    debit = expense
            running = self._money(running + debit - credit)
            work_label = (row["WorkType"] or "").strip()
            sub = (row["SubWorkType"] or "").strip()
            if sub:
                work_label = f"{work_label} / {sub}" if work_label else sub
            desc_bits = [
                (row["Description"] or row["Remarks"] or "").strip(),
                work_label,
                (row["ReferenceNo"] or "").strip() or f"TXN-{row['TransactionID']}",
            ]
            txn_date = row["TransactionDate"]
            lines.append(
                self._decorate_line(
                    {
                        "date": txn_date.strftime("%d/%m/%Y") if txn_date else "",
                        "description": " · ".join([b for b in desc_bits if b]) or "Transaction",
                        "debit": debit,
                        "credit": credit,
                        "balance": running,
                        "kind": "txn",
                    },
                    link=dash._source_link_for_daily(
                        transaction_id=row["TransactionID"],
                        work_type=row["WorkType"],
                        sub_work_type=row["SubWorkType"],
                        stamp_id=row["StampID"],
                        reference=row["ReferenceNo"],
                    ),
                )
            )

        period = self._period_fields(date_from, date_to)
        return {
            "kind": "work",
            "title": "Work / Category Ledger",
            "entity_name": work_name,
            "entity_id": work_id,
            "meta": [
                ("Work / Category", work_name),
                ("Ledger Kind", (work["LedgerKind"] or "").strip() or "—"),
                ("Period", f"{date_from.strftime('%d/%m/%Y')} to {date_to.strftime('%d/%m/%Y')}"),
            ],
            "headers": ["Date", "Description", "Debit", "Credit", "Closing Balance"],
            "lines": lines,
            "closing": running,
            **period,
        }

    def _item_ledger_data(
        self,
        item_id: int,
        *,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        try:
            from app.repositories.item_master_repository import ItemMasterRepository

            ItemMasterRepository().ensure_schema()
        except Exception:
            db.session.rollback()
        item = db.session.execute(
            text(
                """
                SELECT
                    ItemID, ItemCode, ItemName, HsnSac, Unit,
                    ISNULL(OpeningBalance, 0) AS OpeningBalance,
                    OpeningBalanceDate,
                    PurchaseDate,
                    DepreciationRate,
                    AppreciationRate,
                    ChartGroupID,
                    ISNULL(IsActive, 1) AS IsActive
                FROM dbo.ItemMaster
                WHERE ItemID = :item_id
                """
            ),
            {"item_id": item_id},
        ).mappings().first()
        if item is None:
            raise ValueError("Item not found.")

        date_from, date_to = self._resolve_period(date_from, date_to)
        item_name = (item["ItemName"] or "").strip()
        item_code = (item["ItemCode"] or "").strip()

        opening = Decimal("0.00")
        ob_date = item["OpeningBalanceDate"]
        if ob_date is None or ob_date <= date_from:
            opening = self._money(item["OpeningBalance"])

        prior = db.session.execute(
            text(
                """
                SELECT ISNULL(SUM(ISNULL(l.TaxableValue, 0)), 0)
                FROM dbo.GstInvoiceLine l
                INNER JOIN dbo.GstInvoice inv ON inv.InvoiceID = l.InvoiceID
                WHERE l.ItemID = :item_id
                  AND inv.InvoiceDate < :date_from
                """
            ),
            {"item_id": item_id, "date_from": date_from},
        ).scalar()
        # Sales reduce stock value / credit the item ledger
        opening = self._money(opening - self._money(prior))

        rows = db.session.execute(
            text(
                """
                SELECT
                    inv.InvoiceID,
                    inv.InvoiceNo,
                    inv.InvoiceDate,
                    inv.CustomerName,
                    l.Particulars,
                    l.Qty,
                    l.Unit,
                    l.Rate,
                    ISNULL(l.TaxableValue, 0) AS TaxableValue,
                    ISNULL(l.DiscountAmount, 0) AS DiscountAmount
                FROM dbo.GstInvoiceLine l
                INNER JOIN dbo.GstInvoice inv ON inv.InvoiceID = l.InvoiceID
                WHERE l.ItemID = :item_id
                  AND inv.InvoiceDate >= :date_from
                  AND inv.InvoiceDate <= :date_to
                ORDER BY inv.InvoiceDate ASC, inv.InvoiceID ASC, l.SrNo ASC
                """
            ),
            {"item_id": item_id, "date_from": date_from, "date_to": date_to},
        ).mappings().all()

        lines: list[dict[str, Any]] = []
        running = opening
        lines.append(
            self._decorate_line(
                {
                    "date": date_from.strftime("%d/%m/%Y"),
                    "description": "Opening Balance",
                    "debit": Decimal("0.00"),
                    "credit": Decimal("0.00"),
                    "balance": running,
                    "kind": "opening",
                }
            )
        )

        from flask import url_for

        for row in rows:
            credit = self._money(row["TaxableValue"])
            debit = Decimal("0.00")
            running = self._money(running + debit - credit)
            qty = self._money(row["Qty"])
            unit = (row["Unit"] or item["Unit"] or "").strip()
            cust = (row["CustomerName"] or "").strip()
            inv_no = (row["InvoiceNo"] or "").strip()
            particulars = (row["Particulars"] or item_name).strip()
            desc = f"{particulars} · Inv {inv_no}"
            if cust:
                desc = f"{desc} · {cust}"
            if qty:
                desc = f"{desc} · Qty {qty}" + (f" {unit}" if unit else "")
            txn_date = row["InvoiceDate"]
            invoice_id = int(row["InvoiceID"])
            lines.append(
                self._decorate_line(
                    {
                        "date": txn_date.strftime("%d/%m/%Y") if txn_date else "",
                        "description": desc,
                        "debit": debit,
                        "credit": credit,
                        "balance": running,
                        "kind": "txn",
                    },
                    link={
                        "can_open": True,
                        "source_module": "invoice",
                        "source_module_id": invoice_id,
                        "source_url": url_for(
                            "accounting_invoice.invoice_sale", edit=invoice_id
                        ),
                        "work_type": "",
                    },
                )
            )

        try:
            from app.services.depreciation_service import DepreciationService

            dep_svc = DepreciationService()
            if dep_svc.is_fixed_asset_group(item.get("ChartGroupID")):
                rate = self._money(item.get("DepreciationRate"))
                if rate > 0 and running > 0:
                    calc = dep_svc.calculate(
                        cost=running,
                        rate=rate,
                        purchase_date=item.get("PurchaseDate"),
                        opening_date=ob_date,
                        as_of=date_to,
                    )
                    cy = self._money(calc["current_year"])
                    if cy > 0:
                        running = self._money(running - cy)
                        lines.append(
                            self._decorate_line(
                                {
                                    "date": date_to.strftime("%d/%m/%Y"),
                                    "description": f"Depreciation @ {rate}% WDV",
                                    "debit": Decimal("0.00"),
                                    "credit": cy,
                                    "balance": running,
                                    "kind": "txn",
                                }
                            )
                        )
            elif dep_svc.is_investment_group(item.get("ChartGroupID")):
                rate = self._money(item.get("AppreciationRate"))
                if rate > 0 and running > 0:
                    calc = dep_svc.calculate_appreciation(
                        cost=running,
                        rate=rate,
                        purchase_date=item.get("PurchaseDate"),
                        opening_date=ob_date,
                        as_of=date_to,
                    )
                    cy = self._money(calc["current_year"])
                    if cy > 0:
                        running = self._money(running + cy)
                        lines.append(
                            self._decorate_line(
                                {
                                    "date": date_to.strftime("%d/%m/%Y"),
                                    "description": f"Appreciation @ {rate}%",
                                    "debit": cy,
                                    "credit": Decimal("0.00"),
                                    "balance": running,
                                    "kind": "txn",
                                }
                            )
                        )
        except Exception:
            db.session.rollback()

        period = self._period_fields(date_from, date_to)
        return {
            "kind": "item",
            "title": "Item Ledger",
            "entity_name": item_name,
            "entity_id": item_id,
            "meta": [
                ("Item", item_name),
                ("Item Code", item_code or "—"),
                ("HSN / SAC", (item["HsnSac"] or "").strip() or "—"),
                ("Period", f"{date_from.strftime('%d/%m/%Y')} to {date_to.strftime('%d/%m/%Y')}"),
            ],
            "headers": ["Date", "Description", "Debit", "Credit", "Closing Balance"],
            "lines": lines,
            "closing": running,
            **period,
        }

    # ── Export (PDF / XLSX / CSV / XML) ─────────────────────────────────────

    EXPORT_FORMATS = ("pdf", "xlsx", "csv", "xml")

    @staticmethod
    def _safe_filename(name: str) -> str:
        cleaned = re.sub(r"[^\w\-]+", "_", (name or "ledger").strip())[:50]
        return cleaned or "ledger"

    @staticmethod
    def _fmt_export_money(value: Any) -> str:
        if value is None:
            return ""
        return f"{Decimal(str(value or 0)):.2f}"

    def export_ledger(
        self,
        kind: str,
        entity_id: int,
        *,
        fmt: str,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[bytes, str, str]:
        fmt_key = (fmt or "").strip().lower()
        if fmt_key not in self.EXPORT_FORMATS:
            raise ValueError("Unsupported export format. Use pdf, xlsx, csv, or xml.")
        ledger = self.preview_ledger(
            kind, entity_id, date_from=date_from, date_to=date_to
        )
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        base = (
            f"Ledger_{self._safe_filename(str(ledger.get('entity_name') or kind))}_{stamp}"
        )
        if fmt_key == "pdf":
            return self._export_pdf(ledger), f"{base}.pdf", "application/pdf"
        if fmt_key == "xlsx":
            return (
                self._export_xlsx(ledger),
                f"{base}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        if fmt_key == "csv":
            return self._export_csv(ledger), f"{base}.csv", "text/csv; charset=utf-8"
        return self._export_xml(ledger), f"{base}.xml", "application/xml"

    def _export_xlsx(self, ledger: dict[str, Any]) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "Ledger"
        headers = ledger.get("headers") or [
            "Date",
            "Description",
            "Debit",
            "Credit",
            "Closing Balance",
        ]
        thin = Border(
            left=Side(style="thin", color="5D6D7E"),
            right=Side(style="thin", color="5D6D7E"),
            top=Side(style="thin", color="5D6D7E"),
            bottom=Side(style="thin", color="5D6D7E"),
        )
        header_fill = PatternFill("solid", fgColor="154375")
        header_font = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
        title_font = Font(name="Calibri", bold=True, size=14, color="154375")
        meta_font = Font(name="Calibri", size=10, color="1C2833")
        open_fill = PatternFill("solid", fgColor="EAF2F8")

        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        ws["A1"] = "Joshi Tax Consultancy & Services"
        ws["A1"].font = Font(name="Calibri", bold=True, size=12, color="148F77")

        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
        ws["A2"] = f"{ledger.get('title') or 'Ledger'} — {ledger.get('entity_name') or ''}"
        ws["A2"].font = title_font

        row_idx = 4
        for label, value in ledger.get("meta") or []:
            ws.cell(row=row_idx, column=1, value=f"{label}:").font = Font(
                name="Calibri", bold=True, size=10
            )
            ws.merge_cells(
                start_row=row_idx, start_column=2, end_row=row_idx, end_column=len(headers)
            )
            cell = ws.cell(row=row_idx, column=2, value=str(value or ""))
            cell.font = meta_font
            row_idx += 1

        row_idx += 1
        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=row_idx, column=col, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")
            cell.border = thin
        row_idx += 1

        for line in ledger.get("lines") or []:
            values = [
                line.get("date") or "",
                line.get("description") or "",
                float(line["debit"]) if line.get("debit") is not None else None,
                float(line["credit"]) if line.get("credit") is not None else None,
                float(line["balance"]) if line.get("balance") is not None else None,
            ]
            for col, value in enumerate(values, start=1):
                cell = ws.cell(row=row_idx, column=col, value=value)
                cell.border = thin
                cell.font = Font(name="Calibri", size=10)
                if col >= 3 and value is not None:
                    cell.number_format = "#,##0.00"
                    cell.alignment = Alignment(horizontal="right")
                if (line.get("kind") or "") == "opening":
                    cell.fill = open_fill
                    cell.font = Font(name="Calibri", bold=True, size=10)
            row_idx += 1

        row_idx += 1
        ws.cell(row=row_idx, column=1, value="Closing Balance").font = Font(
            name="Calibri", bold=True, size=11
        )
        close_cell = ws.cell(
            row=row_idx, column=5, value=float(self._money(ledger.get("closing")))
        )
        close_cell.font = Font(name="Calibri", bold=True, size=11, color="0E6655")
        close_cell.number_format = "#,##0.00"

        ws.column_dimensions["A"].width = 14
        ws.column_dimensions["B"].width = 55
        ws.column_dimensions["C"].width = 14
        ws.column_dimensions["D"].width = 14
        ws.column_dimensions["E"].width = 16

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def _export_csv(self, ledger: dict[str, Any]) -> bytes:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Joshi Tax Consultancy & Services"])
        writer.writerow([ledger.get("title") or "Ledger"])
        writer.writerow([ledger.get("entity_name") or ""])
        for label, value in ledger.get("meta") or []:
            writer.writerow([label, value])
        writer.writerow([])
        headers = ledger.get("headers") or [
            "Date",
            "Description",
            "Debit",
            "Credit",
            "Closing Balance",
        ]
        writer.writerow(headers)
        for line in ledger.get("lines") or []:
            writer.writerow(
                [
                    line.get("date") or "",
                    line.get("description") or "",
                    self._fmt_export_money(line.get("debit")),
                    self._fmt_export_money(line.get("credit")),
                    self._fmt_export_money(line.get("balance")),
                ]
            )
        writer.writerow([])
        writer.writerow(
            ["Closing Balance", "", "", "", self._fmt_export_money(ledger.get("closing"))]
        )
        return ("\ufeff" + buf.getvalue()).encode("utf-8")

    def _export_xml(self, ledger: dict[str, Any]) -> bytes:
        root = ET.Element("LedgerReport")
        ET.SubElement(root, "Company").text = "Joshi Tax Consultancy & Services"
        ET.SubElement(root, "Title").text = str(ledger.get("title") or "Ledger")
        ET.SubElement(root, "EntityName").text = str(ledger.get("entity_name") or "")
        ET.SubElement(root, "EntityId").text = str(ledger.get("entity_id") or "")
        ET.SubElement(root, "Kind").text = str(ledger.get("kind") or "")
        ET.SubElement(root, "ClosingBalance").text = self._fmt_export_money(
            ledger.get("closing")
        )

        meta_el = ET.SubElement(root, "Meta")
        for label, value in ledger.get("meta") or []:
            item = ET.SubElement(meta_el, "Item")
            item.set("label", str(label))
            item.text = str(value or "")

        lines_el = ET.SubElement(root, "Lines")
        for line in ledger.get("lines") or []:
            row = ET.SubElement(lines_el, "Line")
            row.set("kind", str(line.get("kind") or "txn"))
            ET.SubElement(row, "Date").text = str(line.get("date") or "")
            ET.SubElement(row, "Description").text = str(line.get("description") or "")
            ET.SubElement(row, "Debit").text = self._fmt_export_money(line.get("debit"))
            ET.SubElement(row, "Credit").text = self._fmt_export_money(line.get("credit"))
            ET.SubElement(row, "ClosingBalance").text = self._fmt_export_money(
                line.get("balance")
            )

        rough = ET.tostring(root, encoding="utf-8")
        pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding="utf-8")
        return pretty

    def _export_pdf(self, ledger: dict[str, Any]) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=14 * mm,
        )
        styles = getSampleStyleSheet()
        brand = ParagraphStyle(
            "LrBrand",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=colors.HexColor("#148F77"),
            spaceAfter=2,
        )
        title = ParagraphStyle(
            "LrTitle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            textColor=colors.HexColor("#154375"),
            spaceAfter=6,
        )
        meta_style = ParagraphStyle(
            "LrMeta",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.HexColor("#1C2833"),
            leading=12,
        )
        cell_style = ParagraphStyle(
            "LrCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#1C2833"),
        )

        story: list[Any] = [
            Paragraph("Joshi Tax Consultancy &amp; Services", brand),
            Paragraph(
                f"{ledger.get('title') or 'Ledger'} — {ledger.get('entity_name') or ''}",
                title,
            ),
        ]
        meta_bits = " &nbsp;&nbsp;|&nbsp;&nbsp; ".join(
            f"<b>{label}:</b> {value}" for label, value in (ledger.get("meta") or [])
        )
        if meta_bits:
            story.append(Paragraph(meta_bits, meta_style))
        story.append(
            Paragraph(
                f"<b>Closing Balance:</b> Rs. {self._fmt_export_money(ledger.get('closing'))}",
                meta_style,
            )
        )
        story.append(Spacer(1, 8))

        table_data: list[list[Any]] = [
            ["Date", "Description", "Debit", "Credit", "Closing Balance"]
        ]
        for line in ledger.get("lines") or []:
            table_data.append(
                [
                    str(line.get("date") or ""),
                    Paragraph(
                        str(line.get("description") or "—")
                        .replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;"),
                        cell_style,
                    ),
                    self._fmt_export_money(line.get("debit")),
                    self._fmt_export_money(line.get("credit")),
                    self._fmt_export_money(line.get("balance")),
                ]
            )

        table = Table(table_data, colWidths=[55, 250, 58, 58, 72])
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#154375")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#5D6D7E")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FBFC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
        for i, line in enumerate(ledger.get("lines") or [], start=1):
            if (line.get("kind") or "") == "opening":
                style_cmds.append(
                    ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#EAF2F8"))
                )
                style_cmds.append(("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"))
        table.setStyle(TableStyle(style_cmds))
        story.append(table)
        story.append(Spacer(1, 10))
        story.append(
            Paragraph(
                f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')} · JTCS ERP",
                meta_style,
            )
        )
        doc.build(story)
        return buffer.getvalue()
