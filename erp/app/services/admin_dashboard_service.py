from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.extensions import db
from app.services.dashboard_service import METRIC_LABELS, DashboardMetrics, DashboardService
from app.utils.opening_balance import apply_account_running, is_credit_normal_nature
from app.utils.shcil_bank_accounts import stamp_purchase_account_id
from app.utils.smtp_health import mask_email


@dataclass
class AdminBankClosing:
    account_id: int
    bank_name: str
    masked_account: str
    account_type: str
    label: str
    opening_balance: Decimal
    movement_net: Decimal
    closing_balance: Decimal
    is_cash: bool


class AdminDashboardService:
    """Administrator-only dashboard: summary cards + per-bank closing drill-down."""

    def __init__(self, dashboard_service: DashboardService | None = None):
        self.dashboard = dashboard_service or DashboardService()

    @staticmethod
    def _money(value) -> Decimal:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))

    @staticmethod
    def _last4(masked: str | None, account_number: str | None) -> str:
        return DashboardService._account_suffix(account_number, masked)

    def _entered_by_lookup(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for user in db.session.execute(
            text("SELECT FullName, EmailID FROM Users")
        ).mappings().all():
            email = (user["EmailID"] or "").strip()
            if not email:
                continue
            masked = mask_email(email)
            mapping[email.lower()] = masked
            name = (user["FullName"] or "").strip()
            if name:
                mapping[name.lower()] = masked
        return mapping

    def _mask_entered_by(self, raw: str | None, lookup: dict[str, str]) -> str:
        value = (raw or "").strip()
        if not value:
            return ""
        resolved = lookup.get(value.lower())
        if resolved:
            return resolved
        if "@" in value:
            return mask_email(value)
        return value

    def list_bank_closings(self, *, as_of: date) -> list[AdminBankClosing]:
        stamp_account_id = stamp_purchase_account_id(db.session) or 0
        group_select = """
                    CAST(NULL AS NVARCHAR(20)) AS UnderType,
                    CAST(N'Asset' AS NVARCHAR(20)) AS GroupNature
        """
        group_join = ""
        if DashboardService._has_bank_chart_group():
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
        rows = db.session.execute(
            text(
                f"""
                SELECT
                    a.JtcsBankAccountID AS account_id,
                    a.BankName,
                    a.MaskedAccountNumber,
                    a.AccountNumber,
                    a.AccountType,
                    CASE
                        WHEN a.OpeningBalanceDate IS NULL OR a.OpeningBalanceDate <= :as_of
                        THEN ISNULL(a.OpeningBalance, 0)
                        ELSE 0
                    END AS opening_balance,
                    ISNULL((
                        SELECT SUM(ISNULL(t.Debit, 0))
                        FROM JtcsBankTransaction t
                        WHERE t.JtcsBankAccountID = a.JtcsBankAccountID
                          AND t.TransactionDate <= :as_of
                          AND (
                                a.OpeningBalanceDate IS NULL
                                OR t.TransactionDate >= a.OpeningBalanceDate
                              )
                    ), 0) AS debit_sum,
                    ISNULL((
                        SELECT SUM(ISNULL(t.Credit, 0))
                        FROM JtcsBankTransaction t
                        WHERE t.JtcsBankAccountID = a.JtcsBankAccountID
                          AND t.TransactionDate <= :as_of
                          AND (
                                a.OpeningBalanceDate IS NULL
                                OR t.TransactionDate >= a.OpeningBalanceDate
                              )
                    ), 0) AS credit_sum,
                    CASE
                        WHEN a.JtcsBankAccountID = :stamp_account_id AND :stamp_account_id <> 0
                        THEN ISNULL((
                            SELECT SUM(ISNULL(o.Amount, 0))
                            FROM OthersBankCashTransaction o
                            WHERE o.DebitBankAccountID = a.JtcsBankAccountID
                              AND ISNULL(o.IsActive, 1) = 1
                              AND o.WorkDate <= :as_of
                              AND (
                                    o.InBankTransactionID IS NULL
                                    OR NOT EXISTS (
                                        SELECT 1
                                        FROM JtcsBankTransaction t2
                                        WHERE t2.JtcsBankTransactionID = o.InBankTransactionID
                                          AND t2.JtcsBankAccountID = a.JtcsBankAccountID
                                    )
                              )
                        ), 0)
                        ELSE 0
                    END AS orphan_shcil_deposits,
                    {group_select}
                FROM JtcsBankAccountMaster a
                {group_join}
                WHERE ISNULL(a.ActiveStatus, 1) = 1
                ORDER BY
                    CASE WHEN LOWER(LTRIM(RTRIM(ISNULL(a.BankName, N'')))) = N'cash' THEN 0 ELSE 1 END,
                    a.DisplayOrder,
                    a.BankName,
                    a.JtcsBankAccountID
                """
            ),
            {"as_of": as_of, "stamp_account_id": stamp_account_id},
        ).mappings().all()

        result: list[AdminBankClosing] = []
        for row in rows:
            bank_name = (row["BankName"] or "Account").strip() or "Account"
            last4 = self._last4(row["MaskedAccountNumber"], row["AccountNumber"])
            account_type = (row["AccountType"] or "").strip()
            label_parts = [bank_name]
            if last4:
                label_parts.append(f"({last4})")
            if account_type:
                label_parts.append(f"[{account_type}]")
            opening = self._money(row["opening_balance"])
            debit = self._money(row["debit_sum"])
            credit = self._money(row["credit_sum"])
            credit_normal = is_credit_normal_nature(row.get("GroupNature"), row.get("UnderType"))
            signed_movement = apply_account_running(
                Decimal("0.00"), debit, credit, credit_normal=credit_normal
            )
            movement = self._money(signed_movement + self._money(row["orphan_shcil_deposits"]))
            closing = self._money(
                apply_account_running(
                    opening, debit, credit, credit_normal=credit_normal
                )
                + self._money(row["orphan_shcil_deposits"])
            )
            if credit_normal:
                closing = -closing
                movement = -movement
            result.append(
                AdminBankClosing(
                    account_id=int(row["account_id"]),
                    bank_name=bank_name,
                    masked_account=(row["MaskedAccountNumber"] or row["AccountNumber"] or "").strip(),
                    account_type=account_type,
                    label=" ".join(label_parts),
                    opening_balance=opening,
                    movement_net=movement,
                    closing_balance=closing,
                    is_cash=bank_name.lower() == "cash",
                )
            )
        return result

    def _project_income_total(self, date_from: date, date_to: date) -> Decimal:
        """
        Project-wide income for Admin Dashboard.

        Modules often post service receipts into SaleAmount (IncomeAmount stays 0).
        Reports already treat income as IncomeAmount + SaleAmount — use the same here.
        """
        self.dashboard.ensure_schema()
        value = db.session.execute(
            text(
                """
                SELECT ISNULL(SUM(ISNULL(IncomeAmount, 0) + ISNULL(SaleAmount, 0)), 0)
                FROM JTCSDailyTransaction
                WHERE TransactionDate >= :date_from
                  AND TransactionDate <= :date_to
                  AND Status = N'Posted'
                """
            ),
            {"date_from": date_from, "date_to": date_to},
        ).scalar() or Decimal("0")
        return self._money(value) + self._money(
            self.dashboard._manual_sum("total_income", date_from=date_from, date_to=date_to)
        )

    def get_admin_metrics(self, *, date_from: date, date_to: date) -> DashboardMetrics:
        """Admin cards: project-wide totals (IncomeAmount + SaleAmount for Total Income)."""
        # Same formula as reports: IncomeAmount + SaleAmount.
        base = self.dashboard.get_metrics(date_from, date_to)
        return DashboardMetrics(
            total_income=base.total_income,
            total_expenses=base.total_expenses,
            total_sales=base.total_sales,
            cash_closing_balance=base.cash_closing_balance,
            bank_closing_balance=base.bank_closing_balance,
            cash_received=base.cash_received,
            bank_received=base.bank_received,
            date_from=base.date_from,
            date_to=base.date_to,
        )

    def _income_entry_rows(self, date_from: date, date_to: date) -> list[dict]:
        """Entry rows that feed Total Income (IncomeAmount + SaleAmount)."""
        rows = db.session.execute(
            text(
                """
                SELECT
                    TransactionID,
                    TransactionDate,
                    WorkType,
                    SubWorkType,
                    StampID,
                    CustomerName,
                    ReferenceNo,
                    Description,
                    ISNULL(IncomeAmount, 0) AS IncomeValue,
                    ISNULL(SaleAmount, 0) AS SaleValue,
                    ISNULL(IncomeAmount, 0) + ISNULL(SaleAmount, 0) AS AmountValue
                FROM JTCSDailyTransaction
                WHERE TransactionDate >= :date_from
                  AND TransactionDate <= :date_to
                  AND Status = N'Posted'
                  AND (ISNULL(IncomeAmount, 0) + ISNULL(SaleAmount, 0)) <> 0
                ORDER BY TransactionDate DESC, TransactionID DESC
                """
            ),
            {"date_from": date_from, "date_to": date_to},
        ).mappings().all()

        result: list[dict] = []
        for row in rows:
            work = row["WorkType"] or ""
            if row["SubWorkType"]:
                work = f"{work} / {row['SubWorkType']}" if work else row["SubWorkType"]
            reference = row["ReferenceNo"] or f"DT-{row['TransactionID']}"
            income_part = self._money(row["IncomeValue"])
            sale_part = self._money(row["SaleValue"])
            parts = []
            if income_part:
                parts.append(f"Income {income_part}")
            if sale_part:
                parts.append(f"Sale {sale_part}")
            desc = row["Description"] or "Income / Sale"
            if parts:
                desc = f"{desc} ({', '.join(parts)})"
            item = {
                "row_key": f"daily-income-{row['TransactionID']}",
                "entry_id": None,
                "source": "system",
                "can_edit": False,
                "can_delete": False,
                "entry_date": row["TransactionDate"].isoformat() if row["TransactionDate"] else "",
                "description": desc,
                "reference": reference,
                "work": work or "—",
                "customer": row["CustomerName"] or "—",
                "amount": str(self._money(row["AmountValue"])),
            }
            item.update(
                self.dashboard._source_link_for_daily(
                    transaction_id=row["TransactionID"],
                    work_type=row["WorkType"],
                    sub_work_type=row["SubWorkType"],
                    stamp_id=row["StampID"],
                    reference=row["ReferenceNo"],
                )
            )
            result.append(item)
        return result

    def get_metric_details(
        self,
        metric_key: str,
        *,
        date_from: date,
        date_to: date,
    ) -> dict:
        """Entry-level breakdown for Admin Dashboard summary cards."""
        key = (metric_key or "").strip().lower()
        if key not in METRIC_LABELS:
            raise ValueError("Invalid metric key.")

        metrics = self.get_admin_metrics(date_from=date_from, date_to=date_to)
        total_map = {
            "total_income": metrics.total_income,
            "total_expenses": metrics.total_expenses,
            "total_sales": metrics.total_sales,
            "cash_closing_balance": metrics.cash_closing_balance,
            "bank_closing_balance": metrics.bank_closing_balance,
            "cash_received": metrics.cash_received,
            "bank_received": metrics.bank_received,
        }

        if key == "total_income":
            self.dashboard.ensure_schema()
            date_from, date_to = self.dashboard._normalize_period(date_from, date_to)
            system_rows = self._income_entry_rows(date_from, date_to)
            manual_rows = self.dashboard._manual_rows(
                key, date_from=date_from, date_to=date_to
            )
            rows = list(manual_rows) + list(system_rows)
            return {
                "metric_key": key,
                "metric_label": METRIC_LABELS[key],
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "total": str(total_map[key]),
                "opening_balance": None,
                "rows": rows,
                "row_count": len(rows),
                "formula": "SUM(IncomeAmount + SaleAmount) from all Posted daily transactions in period + manual entries",
            }

        details = self.dashboard.get_metric_details(
            key, date_from=date_from, date_to=date_to
        )
        details["total"] = str(total_map[key])
        formulas = {
            "total_expenses": "SUM(ExpenseAmount) from all Posted daily transactions in period + manual entries",
            "total_sales": "SUM(SaleAmount) from all Posted daily transactions in period + manual entries",
            "cash_closing_balance": "Cash account opening + Cash ledger Debit/Credit through period end + manual entries",
            "bank_closing_balance": "Non-cash bank opening + bank ledger Debit/Credit through period end + manual entries",
            "cash_received": "SUM(Debit) on Cash bank ledger in period + manual entries",
            "bank_received": "SUM(Debit) on non-Cash bank ledger in period + manual entries",
        }
        details["formula"] = formulas.get(key, "")
        return details

    def get_page_data(self, *, date_from: date, date_to: date) -> dict:
        metrics = self.get_admin_metrics(date_from=date_from, date_to=date_to)
        banks = self.list_bank_closings(as_of=date_to)
        banks_total = self._money(sum((b.closing_balance for b in banks), Decimal("0")))
        return {
            "date_from": date_from,
            "date_to": date_to,
            "metrics": metrics,
            "banks": banks,
            "banks_total": banks_total,
            "cards": [
                {
                    "key": "total_income",
                    "label": "Total Income",
                    "value": metrics.total_income,
                },
                {
                    "key": "total_expenses",
                    "label": "Total Expenses",
                    "value": metrics.total_expenses,
                },
                {
                    "key": "total_sales",
                    "label": "Total Sales",
                    "value": metrics.total_sales,
                },
                {
                    "key": "cash_closing_balance",
                    "label": "Cash Closing Balance",
                    "value": metrics.cash_closing_balance,
                },
                {
                    "key": "bank_closing_balance",
                    "label": "Bank Closing Balance",
                    "value": metrics.bank_closing_balance,
                },
                {
                    "key": "cash_received",
                    "label": "Cash Received",
                    "value": metrics.cash_received,
                },
                {
                    "key": "bank_received",
                    "label": "Bank Received",
                    "value": metrics.bank_received,
                },
            ],
        }

    def get_bank_source_details(self, account_id: int, *, as_of: date) -> dict:
        account = db.session.execute(
            text(
                """
                SELECT
                    JtcsBankAccountID,
                    BankName,
                    MaskedAccountNumber,
                    AccountNumber,
                    AccountType,
                    OpeningBalance,
                    OpeningBalanceDate
                FROM JtcsBankAccountMaster
                WHERE JtcsBankAccountID = :account_id
                """
            ),
            {"account_id": account_id},
        ).mappings().first()
        if account is None:
            raise ValueError("Bank account not found.")

        bank_name = (account["BankName"] or "Account").strip() or "Account"
        last4 = self._last4(account["MaskedAccountNumber"], account["AccountNumber"])
        label_parts = [bank_name]
        if last4:
            label_parts.append(f"({last4})")
        account_type = (account["AccountType"] or "").strip()
        if account_type:
            label_parts.append(f"[{account_type}]")
        label = " ".join(label_parts)

        opening = Decimal("0.00")
        ob_date = account["OpeningBalanceDate"]
        if ob_date is None or ob_date <= as_of:
            opening = self._money(account["OpeningBalance"])

        lookup = self._entered_by_lookup()
        txn_sql = """
                SELECT
                    JtcsBankTransactionID,
                    TransactionDate,
                    Description,
                    Remarks,
                    SourceTable,
                    SourceType,
                    SourceRecordID,
                    SourceID,
                    LedgerKind,
                    ImportedBy,
                    ISNULL(Debit, 0) AS DebitValue,
                    ISNULL(Credit, 0) AS CreditValue
                FROM JtcsBankTransaction
                WHERE JtcsBankAccountID = :account_id
                  AND TransactionDate <= :as_of
            """
        txn_params = {"account_id": account_id, "as_of": as_of}
        if ob_date is not None:
            txn_sql += " AND TransactionDate >= :ob_date"
            txn_params["ob_date"] = ob_date
        txn_sql += " ORDER BY TransactionDate ASC, JtcsBankTransactionID ASC"
        txn_rows = db.session.execute(text(txn_sql), txn_params).mappings().all()

        stamp_account_id = stamp_purchase_account_id(db.session)
        is_shcil_stamp = stamp_account_id is not None and int(account_id) == int(stamp_account_id)
        orphan_obc_rows = []
        if is_shcil_stamp:
            orphan_obc_rows = db.session.execute(
                text(
                    """
                    SELECT
                        o.EntryID,
                        o.VoucherNo,
                        o.WorkDate,
                        o.Amount,
                        o.Purpose,
                        o.Remarks,
                        o.CreatedBy,
                        o.InBankTransactionID
                    FROM OthersBankCashTransaction o
                    WHERE o.DebitBankAccountID = :account_id
                      AND ISNULL(o.IsActive, 1) = 1
                      AND o.WorkDate <= :as_of
                      AND (
                            o.InBankTransactionID IS NULL
                            OR NOT EXISTS (
                                SELECT 1
                                FROM JtcsBankTransaction t2
                                WHERE t2.JtcsBankTransactionID = o.InBankTransactionID
                                  AND t2.JtcsBankAccountID = :account_id
                            )
                      )
                    ORDER BY o.WorkDate ASC, o.EntryID ASC
                    """
                ),
                {"account_id": account_id, "as_of": as_of},
            ).mappings().all()

        # Merge bank legs + orphan SHCILStamp deposits (OBC jama missing from ledger)
        events: list[tuple] = []
        for row in txn_rows:
            events.append(
                (
                    row["TransactionDate"],
                    int(row["JtcsBankTransactionID"] or 0),
                    "bank",
                    row,
                )
            )
        for row in orphan_obc_rows:
            events.append(
                (
                    row["WorkDate"],
                    int(row["EntryID"] or 0),
                    "orphan_obc",
                    row,
                )
            )
        events.sort(key=lambda item: (item[0] or date.min, item[1], item[2]))

        rows: list[dict] = [
            {
                "row_key": "opening-balance",
                "entry_date": (ob_date.isoformat() if ob_date else as_of.isoformat()),
                "description": "Opening Balance (Bank Master)",
                "source_module": "JtcsBankAccountMaster",
                "source_type": "OPENING",
                "reference": "OPENING",
                "ledger_kind": "",
                "debit": "0.00",
                "credit": "0.00",
                "net": str(opening),
                "entered_by": "",
                "is_opening": True,
            }
        ]

        running = opening
        for _dt, _seq, kind, row in events:
            if kind == "bank":
                debit = self._money(row["DebitValue"])
                credit = self._money(row["CreditValue"])
                net = self._money(debit - credit)
                running = self._money(running + net)
                source_table = (row["SourceTable"] or "").strip() or "—"
                source_type = (row["SourceType"] or "").strip() or "—"
                source_ref_parts = []
                if row["SourceRecordID"]:
                    source_ref_parts.append(f"Rec#{row['SourceRecordID']}")
                if row["SourceID"]:
                    source_ref_parts.append(f"Src#{row['SourceID']}")
                rows.append(
                    {
                        "row_key": f"bank-{row['JtcsBankTransactionID']}",
                        "entry_date": row["TransactionDate"].isoformat() if row["TransactionDate"] else "",
                        "description": (row["Description"] or row["Remarks"] or "Bank transaction").strip(),
                        "source_module": source_table,
                        "source_type": source_type,
                        "reference": " · ".join(source_ref_parts) or f"BT-{row['JtcsBankTransactionID']}",
                        "ledger_kind": (row["LedgerKind"] or "").strip(),
                        "debit": str(debit),
                        "credit": str(credit),
                        "net": str(net),
                        "running_balance": str(running),
                        "entered_by": self._mask_entered_by(row["ImportedBy"], lookup),
                        "is_opening": False,
                    }
                )
            else:
                debit = self._money(row["Amount"])
                credit = Decimal("0.00")
                net = debit
                running = self._money(running + net)
                purpose = (row["Purpose"] or "Bank Transfer").strip()
                voucher = (row["VoucherNo"] or "").strip()
                rows.append(
                    {
                        "row_key": f"obc-orphan-{row['EntryID']}",
                        "entry_date": row["WorkDate"].isoformat() if row["WorkDate"] else "",
                        "description": f"{purpose} (Debit / In) — OBC deposit",
                        "source_module": "OthersBankCashTransaction",
                        "source_type": "OTHERS_BANK_CASH",
                        "reference": voucher or f"OBC#{row['EntryID']}",
                        "ledger_kind": "CONTRA_IN",
                        "debit": str(debit),
                        "credit": str(credit),
                        "net": str(net),
                        "running_balance": str(running),
                        "entered_by": self._mask_entered_by(row["CreatedBy"], lookup),
                        "is_opening": False,
                    }
                )

        # Attach running on opening for consistent grid
        rows[0]["running_balance"] = str(opening)

        closing = self._money(running)
        return {
            "account_id": account_id,
            "label": label,
            "bank_name": bank_name,
            "as_of": as_of.isoformat(),
            "opening_balance": str(opening),
            "closing_balance": str(closing),
            "row_count": len(rows),
            "rows": rows,
        }
