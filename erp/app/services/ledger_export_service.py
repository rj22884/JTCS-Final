"""Admin Role → Import/Export → Ledger Export (styled Excel + watermarked PDF)."""

from __future__ import annotations

import io
import math
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import text

from app.extensions import db

# Brand palette (professional, colourful — not purple/glow AI defaults)
COLOR_NAVY = "1B4F72"
COLOR_TEAL = "148F77"
COLOR_HEADER_BG = "1A5276"
COLOR_HEADER_FG = "FFFFFF"
COLOR_META_LABEL = "1B4F72"
COLOR_META_BG = "EBF5FB"
COLOR_ALT_ROW = "E8F6F3"
COLOR_OPENING = "FCF3CF"
COLOR_CLOSING = "D5F5E3"
COLOR_DEBIT = "922B21"
COLOR_CREDIT = "196F3D"
COLOR_BALANCE = "1A5276"
COLOR_BORDER = "5D6D7E"


class LedgerExportService:
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
    def _last4(masked: str | None, account_number: str | None) -> str:
        raw = (masked or account_number or "").strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) >= 4:
            return digits[-4:]
        alnum = "".join(ch for ch in raw if ch.isalnum())
        return alnum[-4:] if len(alnum) >= 4 else (alnum or "")

    @staticmethod
    def _fmt_money(value: Decimal | float | int) -> str:
        return f"{Decimal(str(value or 0)):.2f}"

    def list_bank_accounts(self, *, search: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        search_sql = ""
        needle = (search or "").strip()
        if needle:
            params["like"] = f"%{needle}%"
            search_sql = """
              AND (
                a.BankName LIKE :like
                OR a.AccountNumber LIKE :like
                OR a.MaskedAccountNumber LIKE :like
                OR a.AccountHolderName LIKE :like
                OR a.AccountType LIKE :like
              )
            """
        rows = db.session.execute(
            text(
                f"""
                SELECT
                    a.JtcsBankAccountID AS account_id,
                    a.BankName,
                    a.MaskedAccountNumber,
                    a.AccountNumber,
                    a.AccountType,
                    a.AccountHolderName,
                    ISNULL(a.OpeningBalance, 0) AS OpeningBalance,
                    a.OpeningBalanceDate,
                    ISNULL(a.ActiveStatus, 1) AS ActiveStatus,
                    (
                        SELECT COUNT(1)
                        FROM dbo.JtcsBankTransaction t
                        WHERE t.JtcsBankAccountID = a.JtcsBankAccountID
                    ) AS txn_count
                FROM dbo.JtcsBankAccountMaster a
                WHERE 1 = 1
                  {search_sql}
                ORDER BY
                    CASE WHEN LOWER(LTRIM(RTRIM(ISNULL(a.BankName, N'')))) = N'cash' THEN 0 ELSE 1 END,
                    a.DisplayOrder,
                    a.BankName,
                    a.JtcsBankAccountID
                """
            ),
            params,
        ).mappings().all()

        result = []
        for row in rows:
            bank_name = (row["BankName"] or "Account").strip() or "Account"
            last4 = self._last4(row["MaskedAccountNumber"], row["AccountNumber"])
            account_type = (row["AccountType"] or "").strip()
            label_parts = [bank_name]
            if last4:
                label_parts.append(f"({last4})")
            if account_type:
                label_parts.append(f"[{account_type}]")
            result.append(
                {
                    "account_id": int(row["account_id"]),
                    "bank_name": bank_name,
                    "masked_account": (row["MaskedAccountNumber"] or row["AccountNumber"] or "").strip(),
                    "account_type": account_type,
                    "account_holder": (row["AccountHolderName"] or "").strip(),
                    "label": " ".join(label_parts),
                    "opening_balance": str(self._money(row["OpeningBalance"])),
                    "txn_count": int(row["txn_count"] or 0),
                    "active": bool(row["ActiveStatus"]),
                }
            )
        return result

    def list_customers(self, *, search: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"lim": max(1, min(int(limit or 200), 500))}
        search_sql = ""
        needle = (search or "").strip()
        if needle:
            mobile = re.sub(r"\D", "", needle)
            params["like"] = f"%{needle}%"
            params["like_upper"] = f"%{needle.upper()}%"
            params["mobile_like"] = f"%{mobile}%" if mobile else f"%{needle}%"
            search_sql = """
              AND (
                UPPER(LTRIM(RTRIM(c.CustomerName))) LIKE UPPER(:like)
                OR ISNULL(c.MobileNumber, N'') LIKE :mobile_like
                OR UPPER(LTRIM(RTRIM(ISNULL(c.PANNumber, N'')))) LIKE :like_upper
              )
            """
        rows = db.session.execute(
            text(
                f"""
                SELECT TOP (:lim)
                    c.CustomerID,
                    c.CustomerName,
                    c.MobileNumber,
                    c.PANNumber,
                    c.CustomerStatus,
                    (
                        SELECT COUNT(1)
                        FROM dbo.JTCSDailyTransaction d
                        WHERE d.CustomerID = c.CustomerID
                          AND d.Status = N'Posted'
                    ) AS txn_count
                FROM dbo.CustomerMaster c
                WHERE ISNULL(c.CustomerStatus, N'Active') <> N'Rejected'
                  {search_sql}
                ORDER BY
                    CASE WHEN ISNULL(c.CustomerStatus, N'Active') = N'Active' THEN 0 ELSE 1 END,
                    c.CustomerName,
                    c.CustomerID
                """
            ),
            params,
        ).mappings().all()
        return [
            {
                "customer_id": int(row["CustomerID"]),
                "customer_name": (row["CustomerName"] or "").strip(),
                "mobile_number": (row["MobileNumber"] or "").strip(),
                "pan_number": (row["PANNumber"] or "").strip(),
                "status": (row["CustomerStatus"] or "").strip(),
                "txn_count": int(row["txn_count"] or 0),
            }
            for row in rows
        ]

    def _resolve_period(
        self, date_from: date | None, date_to: date | None
    ) -> tuple[date, date]:
        today = date.today()
        return date_from or date(2000, 1, 1), date_to or today

    def _bank_ledger_data(
        self,
        account_id: int,
        *,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        account = db.session.execute(
            text(
                """
                SELECT JtcsBankAccountID, BankName, MaskedAccountNumber, AccountNumber,
                       AccountType, AccountHolderName, OpeningBalance, OpeningBalanceDate
                FROM dbo.JtcsBankAccountMaster
                WHERE JtcsBankAccountID = :account_id
                """
            ),
            {"account_id": account_id},
        ).mappings().first()
        if account is None:
            raise ValueError("Bank account not found.")

        date_from, date_to = self._resolve_period(date_from, date_to)
        bank_name = (account["BankName"] or "Account").strip() or "Account"
        last4 = self._last4(account["MaskedAccountNumber"], account["AccountNumber"])
        account_type = (account["AccountType"] or "").strip()
        label_parts = [bank_name]
        if last4:
            label_parts.append(f"({last4})")
        if account_type:
            label_parts.append(f"[{account_type}]")
        label = " ".join(label_parts)

        opening = Decimal("0.00")
        ob_date = account["OpeningBalanceDate"]
        if ob_date is None or ob_date <= date_from:
            opening = self._money(account["OpeningBalance"])
        # Prior movements only on/after OpeningBalanceDate — never double-count
        # Bank Master Opening Balance with pre-opening (or corrupt-dated) rows.
        prior_sql = """
                SELECT ISNULL(SUM(ISNULL(Debit, 0) - ISNULL(Credit, 0)), 0)
                FROM dbo.JtcsBankTransaction
                WHERE JtcsBankAccountID = :account_id
                  AND TransactionDate < :date_from
            """
        prior_params = {"account_id": account_id, "date_from": date_from}
        if ob_date is not None:
            prior_sql += " AND TransactionDate >= :ob_date"
            prior_params["ob_date"] = ob_date
        prior = db.session.execute(text(prior_sql), prior_params).scalar()
        opening = self._money(opening + self._money(prior))

        txn_sql = """
                SELECT
                    JtcsBankTransactionID, TransactionDate, Description, Remarks,
                    SourceTable, SourceType, SourceRecordID, LedgerKind,
                    ISNULL(Debit, 0) AS DebitValue,
                    ISNULL(Credit, 0) AS CreditValue
                FROM dbo.JtcsBankTransaction
                WHERE JtcsBankAccountID = :account_id
                  AND TransactionDate >= :date_from
                  AND TransactionDate <= :date_to
            """
        txn_params = {
            "account_id": account_id,
            "date_from": date_from,
            "date_to": date_to,
        }
        if ob_date is not None:
            # Keep period rows consistent with opening-date floor.
            txn_sql = txn_sql.replace(
                "AND TransactionDate >= :date_from",
                "AND TransactionDate >= :date_from AND TransactionDate >= :ob_date",
            )
            txn_params["ob_date"] = ob_date
        txn_sql += " ORDER BY TransactionDate ASC, JtcsBankTransactionID ASC"
        txn_rows = db.session.execute(text(txn_sql), txn_params).mappings().all()

        lines: list[dict[str, Any]] = []
        running = opening
        lines.append(
            {
                "date": date_from.strftime("%d/%m/%Y"),
                "description": "Opening Balance",
                "reference": "OPENING",
                "source": "Bank Master",
                "ledger_kind": "",
                "debit": Decimal("0.00"),
                "credit": Decimal("0.00"),
                "balance": running,
                "kind": "opening",
            }
        )

        def _day_total_row(day: date, debit_sum: Decimal, credit_sum: Decimal) -> dict[str, Any]:
            return {
                "date": day.strftime("%d/%m/%Y"),
                "description": f"{day.strftime('%d/%m/%Y')} Total",
                "reference": "",
                "source": "",
                "ledger_kind": "",
                "debit": debit_sum,
                "credit": credit_sum,
                "balance": None,  # blank on total rows
                "kind": "day_total",
            }

        def _month_total_row(year: int, month: int, debit_sum: Decimal, credit_sum: Decimal) -> dict[str, Any]:
            label_m = f"{month:02d}/{year}"
            return {
                "date": label_m,
                "description": f"{label_m} Total",
                "reference": "",
                "source": "",
                "ledger_kind": "",
                "debit": debit_sum,
                "credit": credit_sum,
                "balance": None,  # blank on total rows
                "kind": "month_total",
            }

        cur_day: date | None = None
        cur_month: tuple[int, int] | None = None
        day_debit = Decimal("0.00")
        day_credit = Decimal("0.00")
        month_debit = Decimal("0.00")
        month_credit = Decimal("0.00")

        for row in txn_rows:
            txn_date = row["TransactionDate"]
            if txn_date is None:
                continue
            debit = self._money(row["DebitValue"])
            credit = self._money(row["CreditValue"])

            # Day changed → flush previous day total
            if cur_day is not None and txn_date != cur_day:
                lines.append(_day_total_row(cur_day, day_debit, day_credit))
                day_debit = Decimal("0.00")
                day_credit = Decimal("0.00")
                # Month changed after day flush → flush previous month total
                if cur_month is not None and (txn_date.year, txn_date.month) != cur_month:
                    lines.append(
                        _month_total_row(cur_month[0], cur_month[1], month_debit, month_credit)
                    )
                    month_debit = Decimal("0.00")
                    month_credit = Decimal("0.00")

            cur_day = txn_date
            cur_month = (txn_date.year, txn_date.month)
            day_debit = self._money(day_debit + debit)
            day_credit = self._money(day_credit + credit)
            month_debit = self._money(month_debit + debit)
            month_credit = self._money(month_credit + credit)

            running = self._money(running + debit - credit)
            desc = (row["Description"] or row["Remarks"] or "Bank transaction").strip()
            ref = f"BT-{row['JtcsBankTransactionID']}"
            if row["SourceRecordID"]:
                ref = f"{ref} / Rec#{row['SourceRecordID']}"
            lines.append(
                {
                    "date": txn_date.strftime("%d/%m/%Y"),
                    "description": desc,
                    "reference": ref,
                    "source": (row["SourceTable"] or row["SourceType"] or "").strip(),
                    "ledger_kind": (row["LedgerKind"] or "").strip(),
                    "debit": debit,
                    "credit": credit,
                    "balance": running,
                    "kind": "txn",
                }
            )

        if cur_day is not None:
            lines.append(_day_total_row(cur_day, day_debit, day_credit))
        if cur_month is not None:
            lines.append(_month_total_row(cur_month[0], cur_month[1], month_debit, month_credit))

        grouped_lines = self._bank_desc_group_lines(
            txn_rows, opening=opening, date_from=date_from
        )
        pivot = self._bank_pivot_matrix(txn_rows)

        return {
            "kind": "bank",
            "title": "Bank Account Ledger",
            "entity_name": label,
            "entity_id": account_id,
            "safe_name": re.sub(r"[^\w\-]+", "_", bank_name)[:40],
            "meta": [
                ("Account", label),
                ("Account Holder", (account["AccountHolderName"] or "").strip() or "—"),
                ("Period", f"{date_from.strftime('%d/%m/%Y')} to {date_to.strftime('%d/%m/%Y')}"),
            ],
            "headers": [
                "Date",
                "Description",
                "Reference",
                "Source",
                "Ledger Kind",
                "Debit",
                "Credit",
                "Running Balance",
            ],
            "lines": lines,
            "grouped_lines": grouped_lines,
            "pivot": pivot,
            "closing": running,
            "date_from": date_from,
            "date_to": date_to,
        }

    def _bank_pivot_matrix(self, txn_rows: list[Any]) -> dict[str, Any]:
        """Pivot source: Description x Date cells (sheet renders Date rows, Description headers)."""
        cells: dict[tuple[str, date], dict[str, Decimal]] = defaultdict(
            lambda: {"debit": Decimal("0.00"), "credit": Decimal("0.00")}
        )
        dates: set[date] = set()
        descs: set[str] = set()

        for row in txn_rows:
            txn_date = row["TransactionDate"]
            if txn_date is None:
                continue
            desc = (row["Description"] or row["Remarks"] or "Bank transaction").strip()
            dates.add(txn_date)
            descs.add(desc)
            key = (desc, txn_date)
            cells[key]["debit"] = self._money(cells[key]["debit"] + self._money(row["DebitValue"]))
            cells[key]["credit"] = self._money(
                cells[key]["credit"] + self._money(row["CreditValue"])
            )

        return {
            "dates": sorted(dates),
            "descriptions": sorted(descs, key=str.lower),
            "cells": dict(cells),
        }

    def _bank_desc_group_lines(
        self,
        txn_rows: list[Any],
        *,
        opening: Decimal,
        date_from: date,
    ) -> list[dict[str, Any]]:
        """Sheet-2 view: sort by date then description; group totals per date+description."""
        lines: list[dict[str, Any]] = []
        running = opening
        lines.append(
            {
                "date": date_from.strftime("%d/%m/%Y"),
                "description": "Opening Balance",
                "reference": "OPENING",
                "source": "Bank Master",
                "ledger_kind": "",
                "debit": Decimal("0.00"),
                "credit": Decimal("0.00"),
                "balance": running,
                "kind": "opening",
            }
        )

        def _row_desc(row: Any) -> str:
            return (row["Description"] or row["Remarks"] or "Bank transaction").strip()

        def _group_total_row(
            day: date, desc: str, debit_sum: Decimal, credit_sum: Decimal
        ) -> dict[str, Any]:
            day_label = day.strftime("%d/%m/%Y")
            return {
                "date": day_label,
                "description": f"{day_label} - {desc} Total",
                "reference": "",
                "source": "",
                "ledger_kind": "",
                "debit": debit_sum,
                "credit": credit_sum,
                "balance": None,
                "kind": "desc_total",
            }

        sorted_rows = sorted(
            [r for r in txn_rows if r["TransactionDate"] is not None],
            key=lambda r: (
                r["TransactionDate"],
                _row_desc(r).lower(),
                int(r["JtcsBankTransactionID"] or 0),
            ),
        )

        cur_key: tuple[date, str] | None = None
        group_debit = Decimal("0.00")
        group_credit = Decimal("0.00")

        for row in sorted_rows:
            txn_date = row["TransactionDate"]
            desc = _row_desc(row)
            key = (txn_date, desc)
            debit = self._money(row["DebitValue"])
            credit = self._money(row["CreditValue"])

            if cur_key is not None and key != cur_key:
                lines.append(
                    _group_total_row(cur_key[0], cur_key[1], group_debit, group_credit)
                )
                group_debit = Decimal("0.00")
                group_credit = Decimal("0.00")

            cur_key = key
            group_debit = self._money(group_debit + debit)
            group_credit = self._money(group_credit + credit)
            running = self._money(running + debit - credit)

            ref = f"BT-{row['JtcsBankTransactionID']}"
            if row["SourceRecordID"]:
                ref = f"{ref} / Rec#{row['SourceRecordID']}"
            lines.append(
                {
                    "date": txn_date.strftime("%d/%m/%Y"),
                    "description": desc,
                    "reference": ref,
                    "source": (row["SourceTable"] or row["SourceType"] or "").strip(),
                    "ledger_kind": (row["LedgerKind"] or "").strip(),
                    "debit": debit,
                    "credit": credit,
                    "balance": running,
                    "kind": "txn",
                }
            )

        if cur_key is not None:
            lines.append(
                _group_total_row(cur_key[0], cur_key[1], group_debit, group_credit)
            )
        return lines

    def _customer_ledger_data(
        self,
        customer_id: int,
        *,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        has_ob = bool(
            db.session.execute(
                text(
                    "SELECT CASE WHEN COL_LENGTH(N'dbo.CustomerMaster', N'OpeningBalance') "
                    "IS NULL THEN 0 ELSE 1 END"
                )
            ).scalar()
        )
        customer_sql = """
            SELECT CustomerID, CustomerName, MobileNumber, PANNumber
            FROM dbo.CustomerMaster
            WHERE CustomerID = :customer_id
        """
        if has_ob:
            customer_sql = """
                SELECT CustomerID, CustomerName, MobileNumber, PANNumber,
                       ISNULL(OpeningBalance, 0) AS OpeningBalance,
                       OpeningBalanceDate,
                       OpeningBalanceDrCr
                FROM dbo.CustomerMaster
                WHERE CustomerID = :customer_id
            """
        customer = db.session.execute(
            text(customer_sql),
            {"customer_id": customer_id},
        ).mappings().first()
        if customer is None:
            raise ValueError("Customer not found.")

        date_from, date_to = self._resolve_period(date_from, date_to)
        opening = Decimal("0.00")
        ob_date = None
        if has_ob:
            ob_date = customer["OpeningBalanceDate"]
            ob_amount = self._money(customer["OpeningBalance"])
            ob_type = (customer["OpeningBalanceDrCr"] or "Dr").strip()
            # Dr = receivable (+), Cr = advance / credit (-)
            signed_ob = ob_amount if ob_type.upper().startswith("D") else -ob_amount
            if ob_amount != 0 and (ob_date is None or ob_date <= date_from):
                opening = signed_ob

        prior_params = {"customer_id": customer_id, "date_from": date_from}
        prior_date_sql = "AND d.TransactionDate < :date_from"
        if ob_date is not None:
            prior_date_sql += " AND d.TransactionDate > :ob_date"
            prior_params["ob_date"] = ob_date

        prior = db.session.execute(
            text(
                f"""
                SELECT
                    ISNULL(SUM(ISNULL(d.SaleAmount, 0) + ISNULL(d.IncomeAmount, 0)), 0) AS billed,
                    ISNULL(SUM(ISNULL(b.Debit, 0)), 0) AS received
                FROM dbo.JTCSDailyTransaction d
                LEFT JOIN dbo.JtcsBankTransaction b
                    ON b.JtcsBankTransactionID = d.BankTransactionID
                WHERE d.CustomerID = :customer_id
                  AND d.Status = N'Posted'
                  {prior_date_sql}
                """
            ),
            prior_params,
        ).mappings().first()
        prior_billed = self._money(prior["billed"] if prior else 0)
        prior_received = self._money(prior["received"] if prior else 0)

        # Unpaid Followup Tally bills (ITR/GST/etc.) live on FollowupEntryMaster
        # until Payment Received creates JTCSDailyTransaction — include them so
        # Ledger Report matches Followup billing.
        prior_followup_billed = Decimal("0.00")
        followup_rows: list[Any] = []
        try:
            fu_prior_sql = """
                AND ISNULL(f.BillDate, f.WorkDate) < :date_from
            """
            fu_prior_params = {
                "customer_id": customer_id,
                "date_from": date_from,
            }
            if ob_date is not None:
                fu_prior_sql += " AND ISNULL(f.BillDate, f.WorkDate) > :ob_date"
                fu_prior_params["ob_date"] = ob_date
            prior_followup_billed = self._money(
                db.session.execute(
                    text(
                        f"""
                        SELECT ISNULL(SUM(ISNULL(f.BillAmount, 0)), 0)
                        FROM dbo.FollowupEntryMaster f
                        WHERE f.CustomerID = :customer_id
                          AND ISNULL(f.IsActive, 1) = 1
                          AND f.BillNo IS NOT NULL
                          AND LTRIM(RTRIM(f.BillNo)) <> N''
                          AND ISNULL(f.BillAmount, 0) > 0
                          {fu_prior_sql}
                          AND NOT EXISTS (
                              SELECT 1
                              FROM dbo.JTCSDailyTransaction d
                              WHERE d.CustomerID = f.CustomerID
                                AND d.Status = N'Posted'
                                AND UPPER(LTRIM(RTRIM(ISNULL(d.ReferenceNo, N''))))
                                    = UPPER(LTRIM(RTRIM(f.BillNo)))
                                AND d.WorkType = f.ModuleCode
                          )
                        """
                    ),
                    fu_prior_params,
                ).scalar()
            )
            followup_rows = list(
                db.session.execute(
                    text(
                        """
                        SELECT
                            CAST(NULL AS INT) AS TransactionID,
                            ISNULL(f.BillDate, f.WorkDate) AS TransactionDate,
                            f.ModuleCode AS WorkType,
                            CONCAT(f.ModuleCode, N' Followup') AS SubWorkType,
                            f.BillNo AS ReferenceNo,
                            CONCAT(
                                f.ModuleCode, N' Followup — ',
                                LTRIM(RTRIM(f.BillNo))
                            ) AS Description,
                            CAST(NULL AS NVARCHAR(500)) AS Remarks,
                            ISNULL(f.BillAmount, 0) AS SaleAmount,
                            CAST(0 AS DECIMAL(18, 2)) AS IncomeAmount,
                            CAST(0 AS DECIMAL(18, 2)) AS BankDebit,
                            CAST(0 AS DECIMAL(18, 2)) AS PaymentTotal
                        FROM dbo.FollowupEntryMaster f
                        WHERE f.CustomerID = :customer_id
                          AND ISNULL(f.IsActive, 1) = 1
                          AND f.BillNo IS NOT NULL
                          AND LTRIM(RTRIM(f.BillNo)) <> N''
                          AND ISNULL(f.BillAmount, 0) > 0
                          AND ISNULL(f.BillDate, f.WorkDate) >= :date_from
                          AND ISNULL(f.BillDate, f.WorkDate) <= :date_to
                          AND NOT EXISTS (
                              SELECT 1
                              FROM dbo.JTCSDailyTransaction d
                              WHERE d.CustomerID = f.CustomerID
                                AND d.Status = N'Posted'
                                AND UPPER(LTRIM(RTRIM(ISNULL(d.ReferenceNo, N''))))
                                    = UPPER(LTRIM(RTRIM(f.BillNo)))
                                AND d.WorkType = f.ModuleCode
                          )
                        """
                    ),
                    {
                        "customer_id": customer_id,
                        "date_from": date_from,
                        "date_to": date_to,
                    },
                ).mappings().all()
            )
        except Exception:
            db.session.rollback()
            prior_followup_billed = Decimal("0.00")
            followup_rows = []

        opening = self._money(
            opening + prior_billed + prior_followup_billed - prior_received
        )

        rows = list(
            db.session.execute(
                text(
                    """
                    SELECT
                        d.TransactionID, d.TransactionDate, d.WorkType, d.SubWorkType,
                        d.ReferenceNo, d.Description, d.Remarks,
                        ISNULL(d.SaleAmount, 0) AS SaleAmount,
                        ISNULL(d.IncomeAmount, 0) AS IncomeAmount,
                        ISNULL(b.Debit, 0) AS BankDebit,
                        (
                            SELECT ISNULL(SUM(p.Amount), 0)
                            FROM dbo.JTCSDailyTransactionPayment p
                            WHERE p.TransactionID = d.TransactionID
                        ) AS PaymentTotal
                    FROM dbo.JTCSDailyTransaction d
                    LEFT JOIN dbo.JtcsBankTransaction b
                        ON b.JtcsBankTransactionID = d.BankTransactionID
                    WHERE d.CustomerID = :customer_id
                      AND d.Status = N'Posted'
                      AND d.TransactionDate >= :date_from
                      AND d.TransactionDate <= :date_to
                    ORDER BY d.TransactionDate ASC, d.TransactionID ASC
                    """
                ),
                {"customer_id": customer_id, "date_from": date_from, "date_to": date_to},
            ).mappings().all()
        )
        if followup_rows:
            rows.extend(followup_rows)
            rows.sort(
                key=lambda r: (
                    r.get("TransactionDate") or date.min,
                    int(r.get("TransactionID") or 0),
                )
            )

        name = (customer["CustomerName"] or f"Customer {customer_id}").strip()
        lines: list[dict[str, Any]] = []
        running = opening
        lines.append(
            {
                "date": date_from.strftime("%d/%m/%Y"),
                "bill": "",
                "work": "",
                "description": "Opening Balance",
                "debit": Decimal("0.00"),
                "credit": Decimal("0.00"),
                "balance": running,
                "kind": "opening",
            }
        )
        for row in rows:
            billed = self._money(row["SaleAmount"]) + self._money(row["IncomeAmount"])
            receipt = self._money(row["PaymentTotal"])
            if receipt == 0:
                receipt = self._money(row["BankDebit"])
            running = self._money(running + billed - receipt)
            work = (row["WorkType"] or "").strip()
            sub = (row["SubWorkType"] or "").strip()
            if sub:
                work = f"{work} / {sub}" if work else sub
            txn_date = row["TransactionDate"]
            ref = (row["ReferenceNo"] or "").strip()
            if not ref and row.get("TransactionID"):
                ref = f"TXN-{row['TransactionID']}"
            lines.append(
                {
                    "date": txn_date.strftime("%d/%m/%Y") if txn_date else "",
                    "bill": ref,
                    "work": work,
                    "description": (row["Description"] or row["Remarks"] or "").strip(),
                    "debit": billed,
                    "credit": receipt,
                    "balance": running,
                    "kind": "txn",
                }
            )

        return {
            "kind": "customer",
            "title": "Customer Ledger",
            "entity_name": name,
            "entity_id": customer_id,
            "safe_name": re.sub(r"[^\w\-]+", "_", name)[:40],
            "meta": [
                ("Customer", name),
                ("Customer ID", str(customer_id)),
                ("Mobile", (customer["MobileNumber"] or "").strip() or "—"),
                ("PAN", (customer["PANNumber"] or "").strip() or "—"),
                ("Period", f"{date_from.strftime('%d/%m/%Y')} to {date_to.strftime('%d/%m/%Y')}"),
            ],
            "headers": [
                "Date",
                "Bill / Ref No.",
                "Work Type",
                "Description",
                "Debit (Bill)",
                "Credit (Receipt)",
                "Running Balance",
            ],
            "lines": lines,
            "closing": running,
            "date_from": date_from,
            "date_to": date_to,
        }

    def _write_xlsx_ledger_sheet(
        self, ws, data: dict[str, Any], lines: list[dict[str, Any]]
    ) -> None:
        thin = Border(
            left=Side(style="thin", color=COLOR_BORDER),
            right=Side(style="thin", color=COLOR_BORDER),
            top=Side(style="thin", color=COLOR_BORDER),
            bottom=Side(style="thin", color=COLOR_BORDER),
        )
        title_font = Font(name="Calibri", bold=True, size=18, color=COLOR_HEADER_FG)
        brand_font = Font(name="Calibri", bold=True, size=11, color="D5F5E3")
        meta_label_font = Font(name="Calibri", bold=True, size=10, color=COLOR_META_LABEL)
        meta_value_font = Font(name="Calibri", size=10, color="1C2833")
        header_font = Font(name="Calibri", bold=True, size=10, color=COLOR_HEADER_FG)
        cell_font = Font(name="Calibri", size=10, color="1C2833")
        opening_font = Font(name="Calibri", bold=True, size=10, color="7D6608")
        closing_font = Font(name="Calibri", bold=True, size=11, color="0E6655")
        debit_font = Font(name="Calibri", size=10, color=COLOR_DEBIT)
        credit_font = Font(name="Calibri", size=10, color=COLOR_CREDIT)
        balance_font = Font(name="Calibri", bold=True, size=10, color=COLOR_BALANCE)

        fill_title = PatternFill("solid", fgColor=COLOR_HEADER_BG)
        fill_brand = PatternFill("solid", fgColor=COLOR_TEAL)
        fill_meta = PatternFill("solid", fgColor=COLOR_META_BG)
        fill_header = PatternFill("solid", fgColor=COLOR_NAVY)
        fill_alt = PatternFill("solid", fgColor=COLOR_ALT_ROW)
        fill_opening = PatternFill("solid", fgColor=COLOR_OPENING)
        fill_closing = PatternFill("solid", fgColor=COLOR_CLOSING)
        fill_day_total = PatternFill("solid", fgColor="FDEBD0")
        fill_month_total = PatternFill("solid", fgColor="D6EAF8")
        fill_desc_total = PatternFill("solid", fgColor="F5CBA7")
        fill_white = PatternFill("solid", fgColor="FFFFFF")
        total_font = Font(name="Calibri", bold=True, size=10, color="6E2C00")
        month_total_font = Font(name="Calibri", bold=True, size=10, color="1A5276")
        desc_total_font = Font(name="Calibri", bold=True, size=10, color="6E2C00")

        col_count = len(data["headers"])

        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=col_count)
        ws["A1"] = "Joshi Tax Consultancy & Services"
        ws["A1"].font = brand_font
        ws["A1"].fill = fill_brand
        ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 22

        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=col_count)
        ws["A2"] = data["title"]
        ws["A2"].font = title_font
        ws["A2"].fill = fill_title
        ws["A2"].alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[2].height = 28

        row_idx = 4
        for label, value in data["meta"]:
            ws.cell(row=row_idx, column=1, value=label).font = meta_label_font
            ws.cell(row=row_idx, column=1).fill = fill_meta
            ws.cell(row=row_idx, column=1).border = thin
            ws.merge_cells(start_row=row_idx, start_column=2, end_row=row_idx, end_column=min(4, col_count))
            cell = ws.cell(row=row_idx, column=2, value=value)
            cell.font = meta_value_font
            cell.fill = fill_meta
            cell.border = thin
            for c in range(3, min(4, col_count) + 1):
                ws.cell(row=row_idx, column=c).fill = fill_meta
                ws.cell(row=row_idx, column=c).border = thin
            row_idx += 1

        row_idx += 1
        header_row = row_idx
        for col, header in enumerate(data["headers"], start=1):
            cell = ws.cell(row=header_row, column=col, value=header)
            cell.font = header_font
            cell.fill = fill_header
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = thin
        ws.row_dimensions[header_row].height = 24

        money_cols_bank = {6, 7, 8}
        money_cols_cust = {5, 6, 7}
        money_cols = money_cols_bank if data["kind"] == "bank" else money_cols_cust

        data_start = header_row + 1
        for i, line in enumerate(lines):
            r = data_start + i
            line_kind = line.get("kind") or "txn"
            bal = line.get("balance")
            if data["kind"] == "bank":
                values = [
                    line["date"],
                    line["description"],
                    line["reference"],
                    line["source"],
                    line["ledger_kind"],
                    float(line["debit"]),
                    float(line["credit"]),
                    "" if bal is None else float(bal),
                ]
            else:
                values = [
                    line["date"],
                    line["bill"],
                    line["work"],
                    line["description"],
                    float(line["debit"]),
                    float(line["credit"]),
                    "" if bal is None else float(bal),
                ]

            if line_kind == "opening":
                row_fill = fill_opening
                row_font = opening_font
            elif line_kind == "day_total":
                row_fill = fill_day_total
                row_font = total_font
            elif line_kind == "month_total":
                row_fill = fill_month_total
                row_font = month_total_font
            elif line_kind == "desc_total":
                row_fill = fill_desc_total
                row_font = desc_total_font
            else:
                row_fill = fill_alt if i % 2 else fill_white
                row_font = None

            for col, value in enumerate(values, start=1):
                cell = ws.cell(row=r, column=col, value=value)
                cell.border = thin
                cell.fill = row_fill
                if row_font is not None:
                    cell.font = row_font
                    if col in money_cols and value != "":
                        cell.number_format = "#,##0.00"
                        cell.alignment = Alignment(horizontal="right")
                    else:
                        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
                elif col in money_cols:
                    if data["kind"] == "bank":
                        if col == 6:
                            cell.font = debit_font
                        elif col == 7:
                            cell.font = credit_font
                        else:
                            cell.font = balance_font
                    else:
                        if col == 5:
                            cell.font = debit_font
                        elif col == 6:
                            cell.font = credit_font
                        else:
                            cell.font = balance_font
                    if value != "":
                        cell.number_format = "#,##0.00"
                    cell.alignment = Alignment(horizontal="right")
                else:
                    cell.font = cell_font
                    cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

        close_row = data_start + len(lines) + 1
        ws.cell(row=close_row, column=1, value="Closing Balance").font = closing_font
        ws.cell(row=close_row, column=1).fill = fill_closing
        ws.cell(row=close_row, column=1).border = thin
        for col in range(2, col_count):
            cell = ws.cell(row=close_row, column=col, value="")
            cell.fill = fill_closing
            cell.border = thin
        bal_cell = ws.cell(row=close_row, column=col_count, value=float(data["closing"]))
        bal_cell.font = closing_font
        bal_cell.fill = fill_closing
        bal_cell.border = thin
        bal_cell.number_format = "#,##0.00"
        bal_cell.alignment = Alignment(horizontal="right")

        footer_row = close_row + 2
        ws.merge_cells(start_row=footer_row, start_column=1, end_row=footer_row, end_column=col_count)
        ws.cell(
            row=footer_row,
            column=1,
            value=f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')} · JTCS ERP · Confidential",
        ).font = Font(name="Calibri", italic=True, size=9, color="7F8C8D")

        if data["kind"] == "bank":
            widths = [12, 36, 18, 16, 12, 12, 12, 14]
        else:
            widths = [12, 14, 22, 34, 12, 14, 14]
        for i, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = width

        ws.freeze_panes = f"A{header_row + 1}"
        ws.print_title_rows = f"1:{header_row}"
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0

    def _styled_xlsx(self, data: dict[str, Any]) -> tuple[bytes, str]:
        wb = Workbook()
        ws = wb.active
        ws.title = "Ledger" if data["kind"] == "bank" else "Customer Ledger"
        self._write_xlsx_ledger_sheet(ws, data, data["lines"])

        # Bank only: extra sheet — date + description sort with group totals
        if data["kind"] == "bank" and data.get("grouped_lines"):
            ws2 = wb.create_sheet("Date-Description")
            grouped_data = {
                **data,
                "title": "Bank Account Ledger (Date + Description)",
            }
            self._write_xlsx_ledger_sheet(ws2, grouped_data, data["grouped_lines"])

        # Bank only: pivot sheet — Description rows × Date columns (Debit/Credit)
        if data["kind"] == "bank" and data.get("pivot"):
            ws3 = wb.create_sheet("Pivot")
            self._write_xlsx_pivot_sheet(ws3, data, data["pivot"])

        buffer = io.BytesIO()
        wb.save(buffer)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = "Bank_Ledger" if data["kind"] == "bank" else "Customer_Ledger"
        filename = f"{prefix}_{data['safe_name']}_{data['entity_id']}_{stamp}.xlsx"
        return buffer.getvalue(), filename

    def _write_xlsx_pivot_sheet(
        self, ws, data: dict[str, Any], pivot: dict[str, Any]
    ) -> None:
        """Pivot matrix: row=Date, column=Description (header), values=Debit & Credit."""
        dates: list[date] = pivot.get("dates") or []
        descriptions: list[str] = pivot.get("descriptions") or []
        cells: dict[tuple[str, date], dict[str, Decimal]] = pivot.get("cells") or {}

        thin = Border(
            left=Side(style="thin", color=COLOR_BORDER),
            right=Side(style="thin", color=COLOR_BORDER),
            top=Side(style="thin", color=COLOR_BORDER),
            bottom=Side(style="thin", color=COLOR_BORDER),
        )
        brand_font = Font(name="Calibri", bold=True, size=11, color="D5F5E3")
        title_font = Font(name="Calibri", bold=True, size=16, color=COLOR_HEADER_FG)
        meta_label_font = Font(name="Calibri", bold=True, size=10, color=COLOR_META_LABEL)
        meta_value_font = Font(name="Calibri", size=10, color="1C2833")
        header_font = Font(name="Calibri", bold=True, size=9, color=COLOR_HEADER_FG)
        cell_font = Font(name="Calibri", size=9, color="1C2833")
        total_font = Font(name="Calibri", bold=True, size=9, color="1A5276")
        debit_font = Font(name="Calibri", size=9, color=COLOR_DEBIT)
        credit_font = Font(name="Calibri", size=9, color=COLOR_CREDIT)

        fill_brand = PatternFill("solid", fgColor=COLOR_TEAL)
        fill_title = PatternFill("solid", fgColor=COLOR_HEADER_BG)
        fill_meta = PatternFill("solid", fgColor=COLOR_META_BG)
        fill_header = PatternFill("solid", fgColor=COLOR_NAVY)
        fill_sub = PatternFill("solid", fgColor="2874A6")
        fill_alt = PatternFill("solid", fgColor=COLOR_ALT_ROW)
        fill_white = PatternFill("solid", fgColor="FFFFFF")
        fill_total = PatternFill("solid", fgColor="D6EAF8")
        fill_grand = PatternFill("solid", fgColor="D5F5E3")

        # Each description = 2 columns (Debit, Credit); + Date; + Grand Total Debit/Credit
        col_count = 1 + (len(descriptions) * 2) + 2
        if col_count < 4:
            col_count = 4

        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=col_count)
        ws["A1"] = "Joshi Tax Consultancy & Services"
        ws["A1"].font = brand_font
        ws["A1"].fill = fill_brand
        ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 22

        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=col_count)
        ws["A2"] = "Bank Account Ledger - Pivot (Date x Description)"
        ws["A2"].font = title_font
        ws["A2"].fill = fill_title
        ws["A2"].alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[2].height = 26

        row_idx = 4
        for label, value in data["meta"]:
            ws.cell(row=row_idx, column=1, value=label).font = meta_label_font
            ws.cell(row=row_idx, column=1).fill = fill_meta
            ws.cell(row=row_idx, column=1).border = thin
            ws.merge_cells(start_row=row_idx, start_column=2, end_row=row_idx, end_column=min(4, col_count))
            cell = ws.cell(row=row_idx, column=2, value=value)
            cell.font = meta_value_font
            cell.fill = fill_meta
            cell.border = thin
            for c in range(3, min(4, col_count) + 1):
                ws.cell(row=row_idx, column=c).fill = fill_meta
                ws.cell(row=row_idx, column=c).border = thin
            row_idx += 1

        row_idx += 1
        desc_header_row = row_idx
        sub_header_row = row_idx + 1

        # Corner: Date (row labels)
        corner = ws.cell(row=desc_header_row, column=1, value="Date")
        corner.font = header_font
        corner.fill = fill_header
        corner.alignment = Alignment(horizontal="center", vertical="center")
        corner.border = thin
        ws.merge_cells(
            start_row=desc_header_row,
            start_column=1,
            end_row=sub_header_row,
            end_column=1,
        )
        ws.cell(row=sub_header_row, column=1).fill = fill_header
        ws.cell(row=sub_header_row, column=1).border = thin

        # Description columns (Debit | Credit under each description)
        for i, desc in enumerate(descriptions):
            c0 = 2 + (i * 2)
            c1 = c0 + 1
            ws.merge_cells(
                start_row=desc_header_row,
                start_column=c0,
                end_row=desc_header_row,
                end_column=c1,
            )
            dcell = ws.cell(row=desc_header_row, column=c0, value=desc)
            dcell.font = header_font
            dcell.fill = fill_header
            dcell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            dcell.border = thin
            ws.cell(row=desc_header_row, column=c1).fill = fill_header
            ws.cell(row=desc_header_row, column=c1).border = thin

            for offset, label in enumerate(("Debit", "Credit")):
                cell = ws.cell(row=sub_header_row, column=c0 + offset, value=label)
                cell.font = header_font
                cell.fill = fill_sub
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = thin

        # Grand total columns
        gt0 = 2 + (len(descriptions) * 2)
        gt1 = gt0 + 1
        ws.merge_cells(
            start_row=desc_header_row,
            start_column=gt0,
            end_row=desc_header_row,
            end_column=gt1,
        )
        gcell = ws.cell(row=desc_header_row, column=gt0, value="Grand Total")
        gcell.font = header_font
        gcell.fill = fill_header
        gcell.alignment = Alignment(horizontal="center", vertical="center")
        gcell.border = thin
        ws.cell(row=desc_header_row, column=gt1).fill = fill_header
        ws.cell(row=desc_header_row, column=gt1).border = thin
        for offset, label in enumerate(("Debit", "Credit")):
            cell = ws.cell(row=sub_header_row, column=gt0 + offset, value=label)
            cell.font = header_font
            cell.fill = fill_sub
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin

        ws.row_dimensions[desc_header_row].height = 30
        ws.row_dimensions[sub_header_row].height = 18

        # Column totals (per description) for bottom Total row
        col_debit_tot = [Decimal("0.00") for _ in descriptions]
        col_credit_tot = [Decimal("0.00") for _ in descriptions]
        grand_debit = Decimal("0.00")
        grand_credit = Decimal("0.00")

        data_start = sub_header_row + 1
        for r_i, d in enumerate(dates):
            r = data_start + r_i
            row_fill = fill_alt if r_i % 2 else fill_white
            date_cell = ws.cell(row=r, column=1, value=d.strftime("%d/%m/%Y"))
            date_cell.font = cell_font
            date_cell.fill = row_fill
            date_cell.border = thin
            date_cell.alignment = Alignment(horizontal="center", vertical="center")

            row_debit = Decimal("0.00")
            row_credit = Decimal("0.00")
            for i, desc in enumerate(descriptions):
                amounts = cells.get((desc, d)) or {
                    "debit": Decimal("0.00"),
                    "credit": Decimal("0.00"),
                }
                debit = self._money(amounts["debit"])
                credit = self._money(amounts["credit"])
                row_debit = self._money(row_debit + debit)
                row_credit = self._money(row_credit + credit)
                col_debit_tot[i] = self._money(col_debit_tot[i] + debit)
                col_credit_tot[i] = self._money(col_credit_tot[i] + credit)

                c0 = 2 + (i * 2)
                for offset, amount, font in (
                    (0, debit, debit_font),
                    (1, credit, credit_font),
                ):
                    cell = ws.cell(
                        row=r,
                        column=c0 + offset,
                        value=float(amount) if amount != 0 else None,
                    )
                    cell.font = font
                    cell.fill = row_fill
                    cell.border = thin
                    cell.number_format = "#,##0.00"
                    cell.alignment = Alignment(horizontal="right")

            grand_debit = self._money(grand_debit + row_debit)
            grand_credit = self._money(grand_credit + row_credit)
            for offset, amount, font in (
                (0, row_debit, Font(name="Calibri", bold=True, size=9, color=COLOR_DEBIT)),
                (1, row_credit, Font(name="Calibri", bold=True, size=9, color=COLOR_CREDIT)),
            ):
                cell = ws.cell(
                    row=r,
                    column=gt0 + offset,
                    value=float(amount) if amount != 0 else None,
                )
                cell.font = font
                cell.fill = fill_total
                cell.border = thin
                cell.number_format = "#,##0.00"
                cell.alignment = Alignment(horizontal="right")

        # Bottom Total row
        total_row = data_start + len(dates)
        tcell = ws.cell(row=total_row, column=1, value="Total")
        tcell.font = total_font
        tcell.fill = fill_grand
        tcell.border = thin
        for i, _desc in enumerate(descriptions):
            c0 = 2 + (i * 2)
            for offset, amount in ((0, col_debit_tot[i]), (1, col_credit_tot[i])):
                cell = ws.cell(row=total_row, column=c0 + offset, value=float(amount))
                cell.font = total_font
                cell.fill = fill_grand
                cell.border = thin
                cell.number_format = "#,##0.00"
                cell.alignment = Alignment(horizontal="right")
        for offset, amount in ((0, grand_debit), (1, grand_credit)):
            cell = ws.cell(row=total_row, column=gt0 + offset, value=float(amount))
            cell.font = total_font
            cell.fill = fill_grand
            cell.border = thin
            cell.number_format = "#,##0.00"
            cell.alignment = Alignment(horizontal="right")

        footer_row = total_row + 2
        ws.merge_cells(
            start_row=footer_row, start_column=1, end_row=footer_row, end_column=min(6, col_count)
        )
        ws.cell(
            row=footer_row,
            column=1,
            value=f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')} · JTCS ERP · Pivot sheet",
        ).font = Font(name="Calibri", italic=True, size=9, color="7F8C8D")

        ws.column_dimensions["A"].width = 12
        for col in range(2, col_count + 1):
            ws.column_dimensions[get_column_letter(col)].width = 12
        ws.freeze_panes = f"B{data_start}"
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0

    def _draw_jtcs_watermark(self, canvas: pdf_canvas.Canvas, doc) -> None:
        """Single light diagonal JTCS watermark (bottom-left → top-right)."""
        canvas.saveState()
        page_w, page_h = doc.pagesize
        angle = math.degrees(math.atan2(page_h, page_w))
        canvas.translate(page_w / 2.0, page_h / 2.0)
        canvas.rotate(angle)
        # One soft background layer only (no double/dark shadow)
        canvas.setFillColor(colors.Color(0.12, 0.55, 0.50, alpha=0.07))
        canvas.setFont("Helvetica-Bold", 180)
        canvas.drawCentredString(0, -45, "JTCS")
        canvas.restoreState()

        # Footer strip
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#148F77"))
        canvas.rect(0, 0, page_w, 14, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(18, 4, "Joshi Tax Consultancy & Services · Confidential")
        canvas.drawRightString(page_w - 18, 4, f"Page {doc.page}")
        canvas.restoreState()

    def _styled_pdf(self, data: dict[str, Any]) -> tuple[bytes, str]:
        buffer = io.BytesIO()
        pagesize = landscape(A4)
        doc = BaseDocTemplate(
            buffer,
            pagesize=pagesize,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=16 * mm,
        )
        frame = Frame(
            doc.leftMargin,
            doc.bottomMargin,
            doc.width,
            doc.height,
            id="normal",
        )
        doc.addPageTemplates(
            [
                PageTemplate(
                    id="ledger",
                    frames=[frame],
                    onPage=self._draw_jtcs_watermark,
                )
            ]
        )

        styles = getSampleStyleSheet()
        brand = ParagraphStyle(
            "Brand",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=colors.HexColor("#148F77"),
            spaceAfter=2,
        )
        title = ParagraphStyle(
            "Title",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            textColor=colors.HexColor("#1A5276"),
            spaceAfter=8,
        )
        meta_style = ParagraphStyle(
            "Meta",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.HexColor("#1C2833"),
            leading=12,
        )
        cell_style = ParagraphStyle(
            "Cell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#1C2833"),
        )

        story: list[Any] = [
            Paragraph("Joshi Tax Consultancy &amp; Services", brand),
            Paragraph(data["title"], title),
        ]
        meta_bits = " &nbsp;&nbsp;|&nbsp;&nbsp; ".join(
            f"<b>{label}:</b> {value}" for label, value in data["meta"]
        )
        story.append(Paragraph(meta_bits, meta_style))
        story.append(Spacer(1, 8))

        bold_cell = ParagraphStyle(
            "BoldCell",
            parent=cell_style,
            fontName="Helvetica-Bold",
        )
        story.append(
            self._build_pdf_ledger_table(data, data["lines"], cell_style, bold_cell)
        )

        # Bank only: second section — date + description sort with group totals
        if data["kind"] == "bank" and data.get("grouped_lines"):
            story.append(PageBreak())
            story.append(Paragraph("Joshi Tax Consultancy &amp; Services", brand))
            story.append(
                Paragraph("Bank Account Ledger (Date + Description)", title)
            )
            story.append(Paragraph(meta_bits, meta_style))
            story.append(Spacer(1, 8))
            story.append(
                self._build_pdf_ledger_table(
                    data, data["grouped_lines"], cell_style, bold_cell
                )
            )

        story.append(Spacer(1, 10))
        story.append(
            Paragraph(
                f"Generated on {datetime.now().strftime('%d/%m/%Y %H:%M')} · JTCS ERP",
                ParagraphStyle(
                    "Foot",
                    parent=styles["Normal"],
                    fontSize=8,
                    textColor=colors.HexColor("#7F8C8D"),
                    alignment=TA_CENTER,
                ),
            )
        )

        doc.build(story)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = "Bank_Ledger" if data["kind"] == "bank" else "Customer_Ledger"
        filename = f"{prefix}_{data['safe_name']}_{data['entity_id']}_{stamp}.pdf"
        return buffer.getvalue(), filename

    def _build_pdf_ledger_table(
        self,
        data: dict[str, Any],
        lines: list[dict[str, Any]],
        cell_style: ParagraphStyle,
        bold_cell: ParagraphStyle,
    ) -> Table:
        table_data: list[list[Any]] = [
            [Paragraph(f"<b>{h}</b>", cell_style) for h in data["headers"]]
        ]
        line_kinds: list[str] = ["header"]
        total_kinds = {"day_total", "month_total", "desc_total", "opening"}
        for line in lines:
            line_kind = line.get("kind") or "txn"
            line_kinds.append(line_kind)
            bal = line.get("balance")
            bal_txt = "" if bal is None else f"<b>{self._fmt_money(bal)}</b>"
            style_use = bold_cell if line_kind in total_kinds else cell_style
            if data["kind"] == "bank":
                row = [
                    Paragraph(line["date"], style_use),
                    Paragraph(line["description"] or "—", style_use),
                    Paragraph(line["reference"] or "", style_use),
                    Paragraph(line["source"] or "", style_use),
                    Paragraph(line["ledger_kind"] or "", style_use),
                    Paragraph(self._fmt_money(line["debit"]), style_use),
                    Paragraph(self._fmt_money(line["credit"]), style_use),
                    Paragraph(bal_txt, style_use),
                ]
            else:
                row = [
                    Paragraph(line["date"], style_use),
                    Paragraph(line["bill"] or "", style_use),
                    Paragraph(line["work"] or "", style_use),
                    Paragraph(line["description"] or "—", style_use),
                    Paragraph(self._fmt_money(line["debit"]), style_use),
                    Paragraph(self._fmt_money(line["credit"]), style_use),
                    Paragraph(bal_txt, style_use),
                ]
            table_data.append(row)

        line_kinds.append("closing")
        close_pad = len(data["headers"]) - 2
        close_row = [Paragraph("<b>Closing Balance</b>", cell_style)] + [
            "" for _ in range(close_pad)
        ] + [Paragraph(f"<b>{self._fmt_money(data['closing'])}</b>", cell_style)]
        table_data.append(close_row)

        if data["kind"] == "bank":
            col_widths = [70, 160, 90, 80, 60, 65, 65, 75]
        else:
            col_widths = [70, 75, 110, 170, 70, 80, 75]

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A5276")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#D5F5E3")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#5D6D7E")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ALIGN", (-3, 1), (-1, -1), "RIGHT"),
        ]
        for i, kind in enumerate(line_kinds):
            if kind == "header":
                continue
            if kind == "opening":
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FCF3CF")))
            elif kind == "day_total":
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FDEBD0")))
            elif kind == "month_total":
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#D6EAF8")))
            elif kind == "desc_total":
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F5CBA7")))
            elif kind == "closing":
                continue
            elif i % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#E8F6F3")))
        table.setStyle(TableStyle(style_cmds))
        return table

    def bank_ledger_preview_data(
        self,
        account_id: int,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        """Ledger rows for on-screen HTML preview (Bank Accounts tab)."""
        return self._bank_ledger_data(account_id, date_from=date_from, date_to=date_to)

    def customer_ledger_preview_data(
        self,
        customer_id: int,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        """Ledger rows for on-screen HTML preview (Customers tab)."""
        return self._customer_ledger_data(
            customer_id, date_from=date_from, date_to=date_to
        )

    def build_bank_ledger(
        self,
        account_id: int,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        fmt: str = "xlsx",
    ) -> tuple[bytes, str, str]:
        data = self._bank_ledger_data(account_id, date_from=date_from, date_to=date_to)
        fmt = (fmt or "xlsx").lower().strip()
        if fmt == "pdf":
            content, filename = self._styled_pdf(data)
            return content, filename, "application/pdf"
        content, filename = self._styled_xlsx(data)
        return (
            content,
            filename,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def build_customer_ledger(
        self,
        customer_id: int,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        fmt: str = "xlsx",
    ) -> tuple[bytes, str, str]:
        data = self._customer_ledger_data(customer_id, date_from=date_from, date_to=date_to)
        fmt = (fmt or "xlsx").lower().strip()
        if fmt == "pdf":
            content, filename = self._styled_pdf(data)
            return content, filename, "application/pdf"
        content, filename = self._styled_xlsx(data)
        return (
            content,
            filename,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # Back-compat wrappers
    def build_bank_ledger_xlsx(self, account_id: int, **kwargs) -> tuple[bytes, str]:
        data, name, _ = self.build_bank_ledger(account_id, fmt="xlsx", **kwargs)
        return data, name

    def build_customer_ledger_xlsx(self, customer_id: int, **kwargs) -> tuple[bytes, str]:
        data, name, _ = self.build_customer_ledger(customer_id, fmt="xlsx", **kwargs)
        return data, name
