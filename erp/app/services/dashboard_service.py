from __future__ import annotations

from calendar import month_abbr
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import re

from sqlalchemy import select, text

from app.extensions import db
from app.models.transactions import JTCSDailyTransaction
from app.utils.opening_balance import (
    BANK_MOVEMENT_SINCE_OPENING_SQL,
    apply_account_running,
    is_credit_normal_nature,
)


METRIC_LABELS = {
    "total_income": "Total Income",
    "total_expenses": "Total Expenses",
    "total_sales": "Total Sales",
    "cash_closing_balance": "Cash Closing Balance",
    "bank_closing_balance": "Bank Closing Balance",
    "cash_received": "Cash Received",
    "bank_received": "Bank Received",
}

TODAY_ACTIVITY_LABELS = {
    "cash": "Cash",
    "bank": "Bank",
    "income": "Income",
    "expense": "Expense",
    "sales": "Sales",
    "total": "Total Amount",
}


@dataclass
class DashboardMetrics:
    total_income: Decimal
    total_expenses: Decimal
    total_sales: Decimal
    cash_closing_balance: Decimal
    bank_closing_balance: Decimal
    cash_received: Decimal
    bank_received: Decimal
    date_from: date
    date_to: date


@dataclass
class TodayActivityBankLine:
    bank_name: str
    last4: str
    amount: Decimal
    account_id: int | None = None

    @property
    def label(self) -> str:
        name = (self.bank_name or "Bank").strip() or "Bank"
        if self.last4:
            return f"{name} ({self.last4})"
        return name


@dataclass
class BankAccountClosingLine:
    """Per-bank closing balance for dashboard Bank Closing Balance hover."""

    account_id: int
    account_number: str
    bank_name: str
    closing_balance: Decimal
    credit_normal: bool = False


@dataclass
class TodayActivitySummary:
    """Always based on the permanent system date (independent of Period)."""

    system_date: date
    transaction_count: int
    total_amount: Decimal
    income_amount: Decimal
    expense_amount: Decimal
    sale_amount: Decimal
    cash_amount: Decimal
    bank_lines: list[TodayActivityBankLine]
    bank_total: Decimal


class DashboardService:
    """Dashboard figures from transaction tables + popup manual entries."""

    def __init__(self) -> None:
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.DashboardManualEntry', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.DashboardManualEntry (
                        EntryID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        MetricKey NVARCHAR(50) NOT NULL,
                        EntryDate DATE NOT NULL,
                        Description NVARCHAR(500) NULL,
                        Amount DECIMAL(18, 2) NOT NULL,
                        CreatedBy NVARCHAR(150) NULL,
                        CreatedDate DATETIME2 NOT NULL
                            CONSTRAINT DF_DashboardManualEntry_CreatedDate DEFAULT (SYSUTCDATETIME()),
                        ModifiedDate DATETIME2 NULL,
                        IsActive BIT NOT NULL
                            CONSTRAINT DF_DashboardManualEntry_IsActive DEFAULT (1)
                    );
                    CREATE INDEX IX_DashboardManualEntry_Metric_Date
                        ON dbo.DashboardManualEntry (MetricKey, EntryDate, IsActive);
                END
                """
            )
        )
        db.session.commit()
        self._schema_ready = True

    @staticmethod
    def fiscal_year_bounds(today: date | None = None) -> tuple[date, date]:
        today = today or date.today()
        if today.month >= 4:
            return date(today.year, 4, 1), date(today.year + 1, 3, 31)
        return date(today.year - 1, 4, 1), date(today.year, 3, 31)

    @staticmethod
    def month_bounds(today: date | None = None) -> tuple[date, date]:
        today = today or date.today()
        return today.replace(day=1), today

    @staticmethod
    def _decimal(value) -> Decimal:
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Invalid amount.") from None

    @staticmethod
    def _parse_date(value) -> date | None:
        if isinstance(value, date):
            return value
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None

    def _normalize_period(
        self, date_from: date | None, date_to: date | None
    ) -> tuple[date, date]:
        today = date.today()
        date_from = date_from or today
        date_to = date_to or today
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        return date_from, date_to

    def _validate_metric(self, metric_key: str) -> str:
        key = (metric_key or "").strip().lower()
        if key not in METRIC_LABELS:
            raise ValueError("Unknown dashboard metric.")
        return key

    def _manual_sum(
        self,
        metric_key: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        through_date: date | None = None,
    ) -> Decimal:
        self.ensure_schema()
        sql = """
            SELECT ISNULL(SUM(Amount), 0)
            FROM DashboardManualEntry
            WHERE MetricKey = :metric_key
              AND IsActive = 1
        """
        params: dict = {"metric_key": metric_key}
        if through_date is not None:
            sql += " AND EntryDate <= :through_date"
            params["through_date"] = through_date
        else:
            if date_from is not None:
                sql += " AND EntryDate >= :date_from"
                params["date_from"] = date_from
            if date_to is not None:
                sql += " AND EntryDate <= :date_to"
                params["date_to"] = date_to
        return Decimal(str(db.session.execute(text(sql), params).scalar() or 0))

    def get_metrics(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> DashboardMetrics:
        self.ensure_schema()
        date_from, date_to = self._normalize_period(date_from, date_to)

        daily = db.session.execute(
            text(
                """
                SELECT
                    ISNULL(SUM(IncomeAmount), 0) AS income_total,
                    ISNULL(SUM(ExpenseAmount), 0) AS expense_total,
                    ISNULL(SUM(SaleAmount), 0) AS sale_total
                FROM JTCSDailyTransaction
                WHERE TransactionDate >= :date_from
                  AND TransactionDate <= :date_to
                  AND Status = N'Posted'
                """
            ),
            {"date_from": date_from, "date_to": date_to},
        ).mappings().one()

        cash_received = db.session.execute(
            text(
                """
                SELECT ISNULL(SUM(ISNULL(t.Debit, 0)), 0)
                FROM JtcsBankTransaction t
                INNER JOIN JtcsBankAccountMaster a
                    ON a.JtcsBankAccountID = t.JtcsBankAccountID
                WHERE a.BankName = N'Cash'
                  AND ISNULL(a.ActiveStatus, 1) = 1
                  AND t.TransactionDate >= :date_from
                  AND t.TransactionDate <= :date_to
                """
            ),
            {"date_from": date_from, "date_to": date_to},
        ).scalar() or Decimal("0")

        bank_received = db.session.execute(
            text(
                """
                SELECT ISNULL(SUM(ISNULL(t.Debit, 0)), 0)
                FROM JtcsBankTransaction t
                INNER JOIN JtcsBankAccountMaster a
                    ON a.JtcsBankAccountID = t.JtcsBankAccountID
                WHERE a.BankName <> N'Cash'
                  AND ISNULL(a.ActiveStatus, 1) = 1
                  AND t.TransactionDate >= :date_from
                  AND t.TransactionDate <= :date_to
                """
            ),
            {"date_from": date_from, "date_to": date_to},
        ).scalar() or Decimal("0")

        cash_closing = self._ledger_closing_balance(cash_only=True, as_of=date_to)
        bank_closing = self._ledger_closing_balance(cash_only=False, as_of=date_to)

        # Reports / Admin Dashboard: Total Income = IncomeAmount + SaleAmount.
        # Service modules post receipts into SaleAmount; IncomeAmount is often 0.
        posted_income = Decimal(str(daily["income_total"])) + Decimal(str(daily["sale_total"]))

        return DashboardMetrics(
            total_income=posted_income
            + self._manual_sum("total_income", date_from=date_from, date_to=date_to),
            total_expenses=Decimal(str(daily["expense_total"]))
            + self._manual_sum("total_expenses", date_from=date_from, date_to=date_to),
            total_sales=Decimal(str(daily["sale_total"]))
            + self._manual_sum("total_sales", date_from=date_from, date_to=date_to),
            cash_closing_balance=Decimal(str(cash_closing))
            + self._manual_sum("cash_closing_balance", through_date=date_to),
            bank_closing_balance=Decimal(str(bank_closing))
            + self._manual_sum("bank_closing_balance", through_date=date_to),
            cash_received=Decimal(str(cash_received))
            + self._manual_sum("cash_received", date_from=date_from, date_to=date_to),
            bank_received=Decimal(str(bank_received))
            + self._manual_sum("bank_received", date_from=date_from, date_to=date_to),
            date_from=date_from,
            date_to=date_to,
        )

    @staticmethod
    def _active_account_sql(alias: str = "") -> str:
        col = f"{alias}.ActiveStatus" if alias else "ActiveStatus"
        return f"ISNULL({col}, 1) = 1"

    def _ledger_bank_filter(self, *, cash_only: bool, alias: str = "") -> str:
        name_col = f"{alias}.BankName" if alias else "BankName"
        name = f"{name_col} = N'Cash'" if cash_only else f"{name_col} <> N'Cash'"
        return f"{name} AND {self._active_account_sql(alias)}"

    def _master_opening_balance(self, *, cash_only: bool, as_of: date) -> Decimal:
        """Sum of account opening balances effective on/before as_of."""
        bank_filter = self._ledger_bank_filter(cash_only=cash_only)
        value = db.session.execute(
            text(
                f"""
                SELECT ISNULL(SUM(ISNULL(OpeningBalance, 0)), 0)
                FROM JtcsBankAccountMaster
                WHERE {bank_filter}
                  AND (OpeningBalanceDate IS NULL OR OpeningBalanceDate <= :as_of)
                """
            ),
            {"as_of": as_of},
        ).scalar() or Decimal("0")
        return Decimal(str(value))

    def _ledger_txn_net(self, *, cash_only: bool, before: date | None = None, date_from: date | None = None, date_to: date | None = None) -> Decimal:
        """
        Net Debit−Credit for Cash/Bank ledgers.

        Only movements on/after each account's OpeningBalanceDate are included so
        Bank Master Opening Balance is never double-counted with pre-opening rows.
        """
        bank_filter = self._ledger_bank_filter(cash_only=cash_only, alias="a")
        clauses = [bank_filter, BANK_MOVEMENT_SINCE_OPENING_SQL]
        params: dict = {}
        if before is not None:
            clauses.append("t.TransactionDate < :before")
            params["before"] = before
        if date_from is not None:
            clauses.append("t.TransactionDate >= :date_from")
            params["date_from"] = date_from
        if date_to is not None:
            clauses.append("t.TransactionDate <= :date_to")
            params["date_to"] = date_to
        where_sql = " AND ".join(clauses)
        value = db.session.execute(
            text(
                f"""
                SELECT ISNULL(SUM(ISNULL(t.Debit, 0)), 0) - ISNULL(SUM(ISNULL(t.Credit, 0)), 0)
                FROM JtcsBankTransaction t
                INNER JOIN JtcsBankAccountMaster a
                    ON a.JtcsBankAccountID = t.JtcsBankAccountID
                WHERE {where_sql}
                """
            ),
            params,
        ).scalar() or Decimal("0")
        return Decimal(str(value))

    def _ledger_opening_balance(self, *, cash_only: bool, date_from: date) -> Decimal:
        """
        Period opening =
          Bank Master Opening Balance (effective on/before period start)
          + movements on/after each account OpeningBalanceDate and before period start.
        When period start equals OpeningBalanceDate, this equals Bank Master OB.
        """
        return (
            self._master_opening_balance(cash_only=cash_only, as_of=date_from)
            + self._ledger_txn_net(cash_only=cash_only, before=date_from)
        )

    def _ledger_closing_balance(self, *, cash_only: bool, as_of: date) -> Decimal:
        """Closing = master OB (on/before as_of) + post-opening movements through as_of.

        Bank (non-cash) uses Chart of Account Group nature, same as Bank Account Ledger:
        Asset/Expense = Opening + Debit − Credit; Liability/Capital/Income = Opening + Credit − Debit.
        """
        if not cash_only:
            return sum(
                (line.closing_balance for line in self.list_bank_account_closings(as_of=as_of)),
                Decimal("0"),
            )
        return (
            self._master_opening_balance(cash_only=True, as_of=as_of)
            + self._ledger_txn_net(cash_only=True, date_to=as_of)
        )

    @staticmethod
    def _has_bank_chart_group() -> bool:
        return bool(
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

    def get_bank_closing_hover(self, *, as_of: date) -> dict:
        """Hover payload for Bank Closing Balance (respects dashboard period end)."""
        return {
            "accounts": self.list_bank_account_closings(as_of=as_of),
            "manual": self._manual_sum("bank_closing_balance", through_date=as_of),
            "as_of": as_of,
        }

    def list_bank_account_closings(self, *, as_of: date) -> list[BankAccountClosingLine]:
        """
        Active non-cash bank accounts with closing balance as of date_to (dashboard period end).

        Ledger magnitude uses Chart of Account Group (Asset +Dr−Cr, Liability +Cr−Dr).
        Liability / Capital / Income accounts are then signed negative so Bank Closing
        is net cash at bank (OD reduces the total and shows in red).
        """
        group_select = """
                    CAST(NULL AS NVARCHAR(20)) AS UnderType,
                    CAST(N'Asset' AS NVARCHAR(20)) AS GroupNature
        """
        group_join = ""
        if self._has_bank_chart_group():
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
                    a.AccountNumber,
                    a.MaskedAccountNumber,
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
                          AND {BANK_MOVEMENT_SINCE_OPENING_SQL}
                    ), 0) AS debit_sum,
                    ISNULL((
                        SELECT SUM(ISNULL(t.Credit, 0))
                        FROM JtcsBankTransaction t
                        WHERE t.JtcsBankAccountID = a.JtcsBankAccountID
                          AND t.TransactionDate <= :as_of
                          AND {BANK_MOVEMENT_SINCE_OPENING_SQL}
                    ), 0) AS credit_sum,
                    {group_select}
                FROM JtcsBankAccountMaster a
                {group_join}
                WHERE a.BankName <> N'Cash'
                  AND {self._active_account_sql("a")}
                ORDER BY
                    ISNULL(a.DisplayOrder, 2147483647),
                    a.BankName,
                    a.JtcsBankAccountID
                """
            ),
            {"as_of": as_of},
        ).mappings().all()

        result: list[BankAccountClosingLine] = []
        for row in rows:
            bank_name = (row["BankName"] or "Bank").strip() or "Bank"
            account_number = (
                (row["MaskedAccountNumber"] or row["AccountNumber"] or "").strip()
                or bank_name
            )
            opening = Decimal(str(row["opening_balance"] or 0))
            debit = Decimal(str(row["debit_sum"] or 0))
            credit = Decimal(str(row["credit_sum"] or 0))
            credit_normal = is_credit_normal_nature(row.get("GroupNature"), row.get("UnderType"))
            closing = apply_account_running(
                opening, debit, credit, credit_normal=credit_normal
            )
            # Dashboard Bank Closing = net cash at bank. Liability/OD (Cr-normal)
            # outstanding is shown negative so it reduces the card total and turns red.
            if credit_normal:
                closing = -closing
            result.append(
                BankAccountClosingLine(
                    account_id=int(row["account_id"]),
                    account_number=account_number,
                    bank_name=bank_name,
                    closing_balance=closing,
                    credit_normal=credit_normal,
                )
            )
        return result

    @staticmethod
    def _account_suffix(account_number: str | None, masked: str | None = None) -> str:
        """Short public suffix: BOB 5825…0396 → 396; SHCILStamp → Stamp (not tamp)."""
        raw = (account_number or "").strip() or (masked or "").strip()
        if not raw:
            return ""
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) >= 3:
            chunk = digits[-4:] if len(digits) >= 4 else digits
            stripped = chunk.lstrip("0")
            return stripped if stripped else chunk
        parts = re.findall(
            r"[A-Z]+(?=[A-Z][a-z])|[A-Z][a-z]+|[A-Z]+|[a-z]+|\d+",
            raw,
        )
        if len(parts) >= 2:
            return parts[-1]
        alnum = "".join(ch for ch in raw if ch.isalnum())
        return alnum[-4:] if len(alnum) >= 4 else alnum

    @staticmethod
    def _last4_account(masked: str | None, account_number: str | None) -> str:
        return DashboardService._account_suffix(account_number, masked)

    @staticmethod
    def _is_cash_account(bank_name: str | None, account_number: str | None) -> bool:
        return (bank_name or "").strip().lower() == "cash" or (
            account_number or ""
        ).strip().lower() == "cash"

    @staticmethod
    def _mask_account_display(
        account_number: str | None, bank_name: str | None = None
    ) -> str:
        """Cash → 'Cash'; numeric accounts → XXXX396; letter codes → XXXXStamp."""
        if DashboardService._is_cash_account(bank_name, account_number):
            return "Cash"
        suffix = DashboardService._account_suffix(account_number)
        if not suffix:
            return "—"
        return "XXXX" + suffix

    def _accounts_for_daily_txns(
        self, txn_ids: list[int]
    ) -> dict[int, list[tuple[str, str]]]:
        """Map TransactionID → [(bank_name, account_number), ...] in payment order."""
        if not txn_ids:
            return {}
        from sqlalchemy import bindparam

        stmt = text(
            """
            SELECT
                p.TransactionID AS transaction_id,
                a.BankName AS bank_name,
                a.AccountNumber AS account_number
            FROM JTCSDailyTransactionPayment p
            INNER JOIN JtcsBankAccountMaster a
                ON a.JtcsBankAccountID = p.BankAccountID
            WHERE p.TransactionID IN :ids
            ORDER BY p.TransactionID, p.PaymentSequence, p.PaymentLineID
            """
        ).bindparams(bindparam("ids", expanding=True))
        rows = db.session.execute(stmt, {"ids": txn_ids}).mappings().all()
        by_txn: dict[int, list[tuple[str, str]]] = {}
        for row in rows:
            tid = int(row["transaction_id"])
            by_txn.setdefault(tid, []).append(
                (
                    (row["bank_name"] or "").strip(),
                    (row["account_number"] or "").strip(),
                )
            )

        missing = [tid for tid in txn_ids if tid not in by_txn]
        if missing:
            fallback = text(
                """
                SELECT
                    d.TransactionID AS transaction_id,
                    bt.BankName AS bank_name,
                    COALESCE(NULLIF(a.AccountNumber, N''), bt.MaskedAccountNumber, N'') AS account_number
                FROM JTCSDailyTransaction d
                INNER JOIN JtcsBankTransaction bt
                    ON bt.JtcsBankTransactionID = d.BankTransactionID
                LEFT JOIN JtcsBankAccountMaster a
                    ON a.JtcsBankAccountID = bt.JtcsBankAccountID
                WHERE d.TransactionID IN :ids
                  AND d.BankTransactionID IS NOT NULL
                """
            ).bindparams(bindparam("ids", expanding=True))
            for row in db.session.execute(fallback, {"ids": missing}).mappings().all():
                tid = int(row["transaction_id"])
                by_txn.setdefault(tid, []).append(
                    (
                        (row["bank_name"] or "").strip(),
                        (row["account_number"] or "").strip(),
                    )
                )
        return by_txn

    def _format_bank_accounts_label(
        self, accounts: list[tuple[str, str]] | None
    ) -> str:
        if not accounts:
            return "—"
        labels: list[str] = []
        seen: set[str] = set()
        for bank_name, account_number in accounts:
            label = self._mask_account_display(account_number, bank_name)
            key = label.casefold()
            if key in seen:
                continue
            seen.add(key)
            labels.append(label)
        return " · ".join(labels) if labels else "—"

    def get_today_activity_summary(self, system_date: date | None = None) -> TodayActivitySummary:
        system_date = system_date or date.today()
        row = db.session.execute(
            text(
                """
                SELECT
                    COUNT(*) AS txn_count,
                    ISNULL(SUM(TotalAmount), 0) AS total_amount,
                    ISNULL(SUM(IncomeAmount), 0) AS income_amount,
                    ISNULL(SUM(ExpenseAmount), 0) AS expense_amount,
                    ISNULL(SUM(SaleAmount), 0) AS sale_amount
                FROM JTCSDailyTransaction
                WHERE TransactionDate = :system_date
                  AND Status = N'Posted'
                """
            ),
            {"system_date": system_date},
        ).mappings().one()

        # Use bank/payment date when present (ITR followup can post payment on a
        # different day than the daily work/bill date).
        payment_rows = db.session.execute(
            text(
                """
                SELECT
                    a.JtcsBankAccountID AS account_id,
                    a.BankName AS bank_name,
                    a.MaskedAccountNumber AS masked_account,
                    a.AccountNumber AS account_number,
                    ISNULL(SUM(
                        CASE
                            WHEN ISNULL(d.ExpenseAmount, 0) > 0 THEN -ISNULL(p.Amount, 0)
                            ELSE ISNULL(p.Amount, 0)
                        END
                    ), 0) AS amount
                FROM JTCSDailyTransactionPayment p
                INNER JOIN JTCSDailyTransaction d
                    ON d.TransactionID = p.TransactionID
                INNER JOIN JtcsBankAccountMaster a
                    ON a.JtcsBankAccountID = p.BankAccountID
                LEFT JOIN JtcsBankTransaction bt
                    ON bt.JtcsBankTransactionID = p.BankTransactionID
                WHERE d.Status = N'Posted'
                  AND ISNULL(p.Amount, 0) <> 0
                  AND COALESCE(bt.TransactionDate, d.TransactionDate) = :system_date
                GROUP BY
                    a.JtcsBankAccountID,
                    a.BankName,
                    a.MaskedAccountNumber,
                    a.AccountNumber
                ORDER BY a.BankName, a.JtcsBankAccountID
                """
            ),
            {"system_date": system_date},
        ).mappings().all()

        # OBC Bank Transfer / contra legs post to JtcsBankTransaction only (no
        # payment-split rows). Merge those orphan legs so Cash/Bank tiles match
        # Cash Closing Balance. Skip legs already counted via payment rows.
        orphan_rows = db.session.execute(
            text(
                """
                SELECT
                    bt.JtcsBankAccountID AS account_id,
                    COALESCE(a.BankName, bt.BankName) AS bank_name,
                    COALESCE(a.MaskedAccountNumber, bt.MaskedAccountNumber) AS masked_account,
                    a.AccountNumber AS account_number,
                    ISNULL(SUM(ISNULL(bt.Debit, 0) - ISNULL(bt.Credit, 0)), 0) AS amount
                FROM JtcsBankTransaction bt
                LEFT JOIN JtcsBankAccountMaster a
                    ON a.JtcsBankAccountID = bt.JtcsBankAccountID
                WHERE bt.TransactionDate = :system_date
                  AND (ISNULL(bt.Debit, 0) <> 0 OR ISNULL(bt.Credit, 0) <> 0)
                  AND NOT EXISTS (
                        SELECT 1
                        FROM JTCSDailyTransactionPayment p
                        WHERE p.BankTransactionID = bt.JtcsBankTransactionID
                  )
                GROUP BY
                    bt.JtcsBankAccountID,
                    COALESCE(a.BankName, bt.BankName),
                    COALESCE(a.MaskedAccountNumber, bt.MaskedAccountNumber),
                    a.AccountNumber
                ORDER BY COALESCE(a.BankName, bt.BankName), bt.JtcsBankAccountID
                """
            ),
            {"system_date": system_date},
        ).mappings().all()

        # Aggregate payment + orphan bank legs by account.
        by_account: dict[int | None, dict] = {}
        for item in list(payment_rows) + list(orphan_rows):
            amount = Decimal(str(item["amount"] or 0)).quantize(Decimal("0.01"))
            if amount == 0:
                continue
            account_id = item.get("account_id")
            key = int(account_id) if account_id is not None else None
            if key in by_account:
                by_account[key]["amount"] = (
                    Decimal(str(by_account[key]["amount"])) + amount
                ).quantize(Decimal("0.01"))
            else:
                by_account[key] = {
                    "account_id": key,
                    "bank_name": (item["bank_name"] or "").strip() or "Bank",
                    "masked_account": item.get("masked_account"),
                    "account_number": item.get("account_number"),
                    "amount": amount,
                }

        cash_amount = Decimal("0.00")
        bank_lines: list[TodayActivityBankLine] = []
        for item in by_account.values():
            amount = Decimal(str(item["amount"] or 0)).quantize(Decimal("0.01"))
            if amount == 0:
                continue
            bank_name = (item["bank_name"] or "").strip() or "Bank"
            if bank_name.lower() == "cash":
                cash_amount += amount
                continue
            bank_lines.append(
                TodayActivityBankLine(
                    bank_name=bank_name,
                    last4=self._last4_account(item.get("masked_account"), item.get("account_number")),
                    amount=amount,
                    account_id=item.get("account_id"),
                )
            )

        bank_total = sum((line.amount for line in bank_lines), Decimal("0.00"))

        return TodayActivitySummary(
            system_date=system_date,
            transaction_count=int(row["txn_count"] or 0),
            total_amount=Decimal(str(row["total_amount"])),
            income_amount=Decimal(str(row["income_amount"])),
            expense_amount=Decimal(str(row["expense_amount"])),
            sale_amount=Decimal(str(row["sale_amount"])),
            cash_amount=cash_amount.quantize(Decimal("0.01")),
            bank_lines=bank_lines,
            bank_total=Decimal(str(bank_total)).quantize(Decimal("0.01")),
        )

    def _validate_today_activity_metric(self, metric_key: str) -> str:
        key = (metric_key or "").strip().lower()
        if key not in TODAY_ACTIVITY_LABELS:
            raise ValueError("Unknown today activity metric.")
        return key

    def _no_source_link(self) -> dict:
        return {
            "transaction_id": None,
            "work_type": None,
            "sub_work_type": None,
            "source_module": None,
            "source_module_id": None,
            "source_url": None,
            "can_open": False,
        }

    def _source_link_for_daily(
        self,
        *,
        transaction_id: int | None,
        work_type: str | None,
        sub_work_type: str | None,
        stamp_id: int | None,
        reference: str | None,
    ) -> dict:
        """Resolve deep-link URL back to the module entry form for a daily txn."""
        from flask import url_for

        base = {
            "transaction_id": int(transaction_id) if transaction_id else None,
            "work_type": (work_type or "").strip() or None,
            "sub_work_type": (sub_work_type or "").strip() or None,
            "source_module": None,
            "source_module_id": None,
            "source_url": None,
            "can_open": False,
        }
        wt = (work_type or "").strip()
        sw = (sub_work_type or "").strip()
        ref = (reference or "").strip()
        wt_u = wt.upper()
        sw_l = sw.lower()

        try:
            if wt_u == "SHCIL" and sw_l == "stamp activity" and stamp_id:
                sid = int(stamp_id)
                base.update(
                    {
                        "source_module": "stamp",
                        "source_module_id": sid,
                        "source_url": url_for("stamp.stamp_activity", load_stamp=sid),
                        "can_open": True,
                    }
                )
                return base

            if wt_u == "SHCIL" and "e-court" in sw_l and transaction_id:
                sale = db.session.execute(
                    text(
                        """
                        SELECT TOP 1 SaleID
                        FROM ECourtSale
                        WHERE DailyTransactionID = :tid
                        ORDER BY SaleID DESC
                        """
                    ),
                    {"tid": int(transaction_id)},
                ).first()
                if sale:
                    base.update(
                        {
                            "source_module": "ecourt",
                            "source_module_id": int(sale[0]),
                            "source_url": url_for("ecourt.ecourt_activity"),
                            "can_open": True,
                        }
                    )
                return base

            if wt_u == "OTHERS" and sw.lower().startswith("income / expense") and ref:
                row = db.session.execute(
                    text(
                        """
                        SELECT TOP 1 EntryID
                        FROM OthersIncomeExpenseMaster
                        WHERE BillNo = :bill_no AND IsActive = 1
                        ORDER BY EntryID DESC
                        """
                    ),
                    {"bill_no": ref},
                ).first()
                if row:
                    eid = int(row[0])
                    base.update(
                        {
                            "source_module": "income_expense",
                            "source_module_id": eid,
                            "source_url": url_for(
                                "others_income_expense.index", load_entry=eid
                            ),
                            "can_open": True,
                        }
                    )
                return base

            if wt_u == "OTHERS" and sw.lower().startswith("other bank/cash") and ref:
                row = db.session.execute(
                    text(
                        """
                        SELECT TOP 1 EntryID
                        FROM OthersBankCashTransaction
                        WHERE VoucherNo = :voucher_no AND IsActive = 1
                        ORDER BY EntryID DESC
                        """
                    ),
                    {"voucher_no": ref},
                ).first()
                if row:
                    eid = int(row[0])
                    base.update(
                        {
                            "source_module": "bank_cash",
                            "source_module_id": eid,
                            "source_url": url_for(
                                "others_bank_cash.index", load_entry=eid
                            ),
                            "can_open": True,
                        }
                    )
                return base

            if wt_u == "OTHERS" and sw.lower().startswith("printing and scanning") and ref:
                row = db.session.execute(
                    text(
                        """
                        SELECT TOP 1 p.PrintingScanID, w.LedgerKind
                        FROM PrintingScanMaster p
                        INNER JOIN WorkMaster w ON w.WorkID = p.WorkID
                        WHERE p.BillNo = :bill_no AND p.IsActive = 1
                        ORDER BY p.PrintingScanID DESC
                        """
                    ),
                    {"bill_no": ref},
                ).mappings().first()
                if row:
                    pid = int(row["PrintingScanID"])
                    ledger = (row["LedgerKind"] or "").strip()
                    if ledger.lower() == "expense":
                        endpoint = "printing_scan_expense.printing_scanning"
                    else:
                        endpoint = "printing_scanning.printing_scanning"
                    base.update(
                        {
                            "source_module": "printing_scanning",
                            "source_module_id": pid,
                            "source_url": url_for(endpoint, load_entry=pid),
                            "can_open": True,
                        }
                    )
                return base

            if wt_u in {"ITR", "DSC", "TDS", "GST"} and "followup" in sw_l:
                params: dict = {"module_code": wt_u}
                sql = """
                    SELECT TOP 1 EntryID
                    FROM FollowupEntryMaster
                    WHERE ModuleCode = :module_code AND IsActive = 1
                """
                if ref:
                    sql += " AND BillNo = :bill_no"
                    params["bill_no"] = ref
                else:
                    return base
                sql += " ORDER BY EntryID DESC"
                row = db.session.execute(text(sql), params).first()
                if row:
                    eid = int(row[0])
                    endpoint_map = {
                        "ITR": "itr_followup.index",
                        "DSC": "dsc_followup.index",
                        "TDS": "tds_followup.index",
                        "GST": "gst_followup.index",
                    }
                    endpoint = endpoint_map.get(wt_u)
                    if endpoint:
                        base.update(
                            {
                                "source_module": "followup",
                                "source_module_id": eid,
                                "source_url": url_for(endpoint, load_entry=eid),
                                "can_open": True,
                            }
                        )
                return base
        except Exception:
            return base

        return base

    def _source_link_for_bank_cash_entry(self, entry_id: int) -> dict:
        from flask import url_for

        eid = int(entry_id)
        return {
            "transaction_id": None,
            "work_type": "Others",
            "sub_work_type": "Other Bank/Cash Transactions",
            "source_module": "bank_cash",
            "source_module_id": eid,
            "source_url": url_for("others_bank_cash.index", load_entry=eid),
            "can_open": True,
        }

    def _resolve_bank_cash_entry_id(
        self,
        *,
        source_record_id: int | None,
        bank_transaction_id: int | None,
    ) -> int | None:
        """Map Other Bank/Cash ledger legs back to OthersBankCashTransaction.EntryID."""
        if source_record_id:
            sid = int(source_record_id)
            # Newer writes store DailyTransactionID in SourceRecordID.
            daily = db.session.execute(
                text(
                    """
                    SELECT TOP 1 ReferenceNo
                    FROM JTCSDailyTransaction
                    WHERE TransactionID = :tid
                    """
                ),
                {"tid": sid},
            ).first()
            if daily and (daily[0] or "").strip():
                entry = db.session.execute(
                    text(
                        """
                        SELECT TOP 1 EntryID
                        FROM OthersBankCashTransaction
                        WHERE VoucherNo = :voucher_no AND IsActive = 1
                        ORDER BY EntryID DESC
                        """
                    ),
                    {"voucher_no": str(daily[0]).strip()},
                ).first()
                if entry:
                    return int(entry[0])

            # Older / alternate: SourceRecordID may already be EntryID.
            entry = db.session.execute(
                text(
                    """
                    SELECT TOP 1 EntryID
                    FROM OthersBankCashTransaction
                    WHERE EntryID = :eid AND IsActive = 1
                    """
                ),
                {"eid": sid},
            ).first()
            if entry:
                return int(entry[0])

        if bank_transaction_id:
            btid = int(bank_transaction_id)
            entry = db.session.execute(
                text(
                    """
                    SELECT TOP 1 EntryID
                    FROM OthersBankCashTransaction
                    WHERE IsActive = 1
                      AND (
                            OutBankTransactionID = :btid
                         OR InBankTransactionID = :btid
                      )
                    ORDER BY EntryID DESC
                    """
                ),
                {"btid": btid},
            ).first()
            if entry:
                return int(entry[0])
        return None

    def _source_link_for_bank_leg(
        self,
        *,
        source_table: str | None,
        source_record_id: int | None,
        bank_transaction_id: int | None = None,
    ) -> dict:
        table = (source_table or "").strip().lower()
        if not source_record_id and not bank_transaction_id:
            return self._no_source_link()

        # Other Bank/Cash contra legs (Cash Deposit Credit/Out, Debit/In, etc.)
        if table in {"othersbankcashtransaction", "others_bank_cash_transaction"} or (
            not table and bank_transaction_id
        ):
            entry_id = self._resolve_bank_cash_entry_id(
                source_record_id=source_record_id,
                bank_transaction_id=bank_transaction_id,
            )
            if entry_id:
                return self._source_link_for_bank_cash_entry(entry_id)
            if table in {"othersbankcashtransaction", "others_bank_cash_transaction"}:
                return self._no_source_link()

        if not source_record_id:
            return self._no_source_link()
        if table and table != "jtcsdailytransaction":
            # Still try OBC resolve when SourceType/table naming varies.
            entry_id = self._resolve_bank_cash_entry_id(
                source_record_id=source_record_id,
                bank_transaction_id=bank_transaction_id,
            )
            if entry_id:
                return self._source_link_for_bank_cash_entry(entry_id)
            return self._no_source_link()

        daily = db.session.execute(
            text(
                """
                SELECT TOP 1
                    TransactionID, WorkType, SubWorkType, StampID, ReferenceNo
                FROM JTCSDailyTransaction
                WHERE TransactionID = :tid
                """
            ),
            {"tid": int(source_record_id)},
        ).mappings().first()
        if not daily:
            return self._no_source_link()
        link = self._source_link_for_daily(
            transaction_id=daily["TransactionID"],
            work_type=daily["WorkType"],
            sub_work_type=daily["SubWorkType"],
            stamp_id=daily["StampID"],
            reference=daily["ReferenceNo"],
        )
        if link.get("can_open"):
            return link
        # Daily may be OBC even if SourceTable was stored as JTCSDailyTransaction.
        entry_id = self._resolve_bank_cash_entry_id(
            source_record_id=int(daily["TransactionID"]),
            bank_transaction_id=bank_transaction_id,
        )
        if entry_id:
            return self._source_link_for_bank_cash_entry(entry_id)
        return link

    def _today_payment_detail_rows(
        self,
        system_date: date,
        *,
        cash_only: bool | None = None,
        account_id: int | None = None,
    ) -> list[dict]:
        """Detail rows for Cash / Bank tiles (payment splits + orphan bank legs)."""
        params: dict = {"system_date": system_date}
        filters = [
            "d.Status = N'Posted'",
            "ISNULL(p.Amount, 0) <> 0",
            # Prefer bank ledger date (payment date) over daily work/bill date.
            "COALESCE(bt.TransactionDate, d.TransactionDate) = :system_date",
        ]
        if cash_only is True:
            filters.append("LOWER(LTRIM(RTRIM(ISNULL(a.BankName, N'')))) = N'cash'")
        elif cash_only is False:
            filters.append("LOWER(LTRIM(RTRIM(ISNULL(a.BankName, N'')))) <> N'cash'")
        if account_id is not None:
            filters.append("a.JtcsBankAccountID = :account_id")
            params["account_id"] = account_id

        where_sql = " AND ".join(filters)
        payment_rows = db.session.execute(
            text(
                f"""
                SELECT TOP 500
                    p.PaymentLineID,
                    d.TransactionID,
                    COALESCE(bt.TransactionDate, d.TransactionDate) AS ActivityDate,
                    d.WorkType,
                    d.SubWorkType,
                    d.StampID,
                    d.CustomerName,
                    d.ReferenceNo,
                    d.Description,
                    d.ExpenseAmount,
                    a.BankName,
                    a.MaskedAccountNumber,
                    p.Amount AS AmountValue
                FROM JTCSDailyTransactionPayment p
                INNER JOIN JTCSDailyTransaction d
                    ON d.TransactionID = p.TransactionID
                INNER JOIN JtcsBankAccountMaster a
                    ON a.JtcsBankAccountID = p.BankAccountID
                LEFT JOIN JtcsBankTransaction bt
                    ON bt.JtcsBankTransactionID = p.BankTransactionID
                WHERE {where_sql}
                ORDER BY ActivityDate DESC, d.TransactionID DESC, p.PaymentLineID DESC
                """
            ),
            params,
        ).mappings().all()

        result: list[dict] = []
        for row in payment_rows:
            work = row["WorkType"] or ""
            if row["SubWorkType"]:
                work = f"{work} / {row['SubWorkType']}" if work else row["SubWorkType"]
            bank_name = (row["BankName"] or "").strip() or "Bank"
            reference = row["ReferenceNo"] or f"DT-{row['TransactionID']}"
            amount = Decimal(str(row["AmountValue"] or 0))
            is_expense = Decimal(str(row["ExpenseAmount"] or 0)) > 0
            if is_expense:
                amount = -abs(amount)
            activity_date = row["ActivityDate"]
            item = {
                "row_key": f"pay-{row['PaymentLineID']}",
                "entry_id": None,
                "source": "system",
                "can_edit": False,
                "can_delete": False,
                "entry_date": activity_date.isoformat() if activity_date else "",
                "description": row["Description"] or bank_name,
                "reference": reference,
                "work": work or bank_name,
                "customer": row["CustomerName"] or row["MaskedAccountNumber"] or "—",
                "amount": str(amount),
                "is_expense": is_expense,
            }
            item.update(
                self._source_link_for_daily(
                    transaction_id=row["TransactionID"],
                    work_type=row["WorkType"],
                    sub_work_type=row["SubWorkType"],
                    stamp_id=row["StampID"],
                    reference=row["ReferenceNo"],
                )
            )
            result.append(item)

        # Always merge orphan bank legs (e.g. OBC Bank Transfer) that are not
        # linked via JTCSDailyTransactionPayment — otherwise Cash Closing shows
        # them but Today's Activity Cash tile does not.
        bank_params: dict = {"system_date": system_date}
        bank_filters = [
            "bt.TransactionDate = :system_date",
            "(ISNULL(bt.Debit, 0) <> 0 OR ISNULL(bt.Credit, 0) <> 0)",
            """NOT EXISTS (
                    SELECT 1
                    FROM JTCSDailyTransactionPayment p
                    WHERE p.BankTransactionID = bt.JtcsBankTransactionID
               )""",
        ]
        if cash_only is True:
            bank_filters.append("LOWER(LTRIM(RTRIM(ISNULL(bt.BankName, N'')))) = N'cash'")
        elif cash_only is False:
            bank_filters.append("LOWER(LTRIM(RTRIM(ISNULL(bt.BankName, N'')))) <> N'cash'")
        if account_id is not None:
            bank_filters.append("bt.JtcsBankAccountID = :account_id")
            bank_params["account_id"] = account_id

        bank_where = " AND ".join(bank_filters)
        bank_rows = db.session.execute(
            text(
                f"""
                SELECT TOP 500
                    bt.JtcsBankTransactionID,
                    bt.TransactionDate,
                    bt.BankName,
                    bt.MaskedAccountNumber,
                    bt.Description,
                    bt.Remarks,
                    bt.SourceTable,
                    bt.SourceRecordID,
                    ISNULL(bt.Debit, 0) AS DebitValue,
                    ISNULL(bt.Credit, 0) AS CreditValue,
                    ISNULL(bt.Debit, 0) - ISNULL(bt.Credit, 0) AS AmountValue,
                    d.WorkType,
                    d.SubWorkType,
                    d.ReferenceNo AS DailyReference,
                    d.CustomerName AS DailyCustomer
                FROM JtcsBankTransaction bt
                LEFT JOIN JTCSDailyTransaction d
                    ON d.TransactionID = bt.SourceRecordID
                   AND LOWER(LTRIM(RTRIM(ISNULL(bt.SourceTable, N'')))) IN (
                        N'othersbankcashtransaction',
                        N'others_bank_cash_transaction',
                        N'jtcsdailytransaction'
                   )
                WHERE {bank_where}
                ORDER BY bt.TransactionDate DESC, bt.JtcsBankTransactionID DESC
                """
            ),
            bank_params,
        ).mappings().all()

        for row in bank_rows:
            bank_name = (row["BankName"] or "").strip() or "Bank"
            amount = Decimal(str(row["AmountValue"] or 0))
            work = row["WorkType"] or ""
            if row["SubWorkType"]:
                work = f"{work} / {row['SubWorkType']}" if work else row["SubWorkType"]
            reference = (
                (row["DailyReference"] or "").strip()
                or f"BT-{row['JtcsBankTransactionID']}"
            )
            item = {
                "row_key": f"bank-{row['JtcsBankTransactionID']}",
                "entry_id": None,
                "source": "system",
                "can_edit": False,
                "can_delete": False,
                "entry_date": row["TransactionDate"].isoformat() if row["TransactionDate"] else "",
                "description": row["Description"] or row["Remarks"] or bank_name,
                "reference": reference,
                "work": work or bank_name,
                "customer": row["DailyCustomer"] or row["MaskedAccountNumber"] or "—",
                "amount": str(amount),
                "is_expense": amount < 0,
            }
            item.update(
                self._source_link_for_bank_leg(
                    source_table=row["SourceTable"],
                    source_record_id=row["SourceRecordID"],
                    bank_transaction_id=row["JtcsBankTransactionID"],
                )
            )
            result.append(item)

        # Newest activity first (payments already ordered; orphans appended — re-sort).
        result.sort(
            key=lambda r: (
                r.get("entry_date") or "",
                r.get("row_key") or "",
            ),
            reverse=True,
        )
        return result

    def get_today_activity_details(
        self,
        metric_key: str,
        *,
        account_id: int | None = None,
        system_date: date | None = None,
    ) -> dict:
        """Drill-down rows for Today's Activity Summary tiles (system date only)."""
        metric_key = self._validate_today_activity_metric(metric_key)
        system_date = system_date or date.today()
        summary = self.get_today_activity_summary(system_date)
        label = TODAY_ACTIVITY_LABELS[metric_key]

        if metric_key == "cash":
            rows = self._today_payment_detail_rows(system_date, cash_only=True)
            total = summary.cash_amount
        elif metric_key == "bank":
            rows = self._today_payment_detail_rows(
                system_date, cash_only=False, account_id=account_id
            )
            if account_id is not None:
                match = next(
                    (line for line in summary.bank_lines if line.account_id == account_id),
                    None,
                )
                total = match.amount if match else Decimal("0.00")
                if match:
                    label = match.label
            else:
                total = summary.bank_total
        elif metric_key == "income":
            rows = self._daily_metric_rows("IncomeAmount", system_date, system_date)
            total = summary.income_amount
        elif metric_key == "expense":
            rows = self._daily_metric_rows("ExpenseAmount", system_date, system_date)
            total = summary.expense_amount
        elif metric_key == "sales":
            rows = self._daily_metric_rows("SaleAmount", system_date, system_date)
            total = summary.sale_amount
        else:  # total
            rows = self._daily_metric_rows("TotalAmount", system_date, system_date)
            total = summary.total_amount

        return {
            "metric_key": metric_key,
            "metric_label": label,
            "date_from": system_date.isoformat(),
            "date_to": system_date.isoformat(),
            "total": str(total.quantize(Decimal("0.01"))),
            "opening_balance": None,
            "rows": rows,
            "row_count": len(rows),
            "read_only": True,
            "scope": "today_activity",
        }

    def recent_daily_transactions(self, limit: int = 10) -> list[dict]:
        stmt = (
            select(JTCSDailyTransaction)
            .order_by(
                JTCSDailyTransaction.TransactionDate.desc(),
                JTCSDailyTransaction.TransactionID.desc(),
            )
            .limit(limit)
        )
        rows = list(db.session.scalars(stmt).all())
        accounts_by_txn = self._accounts_for_daily_txns(
            [int(row.TransactionID) for row in rows]
        )
        result: list[dict] = []
        for row in rows:
            work = row.WorkType or ""
            if row.SubWorkType:
                work = f"{work} / {row.SubWorkType}" if work else row.SubWorkType
            is_expense = Decimal(str(row.ExpenseAmount or 0)) > 0
            amount = Decimal(str(row.TotalAmount or 0))
            if is_expense:
                amount = -abs(amount)
            created = getattr(row, "CreatedDate", None)
            if created is not None:
                entry_datetime = created.isoformat(sep=" ", timespec="seconds")
            elif row.TransactionDate:
                entry_datetime = f"{row.TransactionDate.isoformat()} 00:00:00"
            else:
                entry_datetime = ""
            bank_account = self._format_bank_accounts_label(
                accounts_by_txn.get(int(row.TransactionID))
            )
            item = {
                "transaction_id": row.TransactionID,
                "entry_date": row.TransactionDate.isoformat() if row.TransactionDate else "",
                "entry_datetime": entry_datetime,
                "work": work,
                "customer": row.CustomerName or "—",
                "bank_account": bank_account,
                "reference": row.ReferenceNo or "",
                "description": row.Description or "",
                "amount": str(amount),
                "is_expense": is_expense,
                "row_key": f"recent-{row.TransactionID}",
            }
            item.update(
                self._source_link_for_daily(
                    transaction_id=row.TransactionID,
                    work_type=row.WorkType,
                    sub_work_type=row.SubWorkType,
                    stamp_id=row.StampID,
                    reference=row.ReferenceNo,
                )
            )
            result.append(item)
        return result

    def _manual_rows(
        self,
        metric_key: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        through_date: date | None = None,
    ) -> list[dict]:
        self.ensure_schema()
        sql = """
            SELECT EntryID, MetricKey, EntryDate, Description, Amount, CreatedBy, CreatedDate
            FROM DashboardManualEntry
            WHERE MetricKey = :metric_key
              AND IsActive = 1
        """
        params: dict = {"metric_key": metric_key}
        if through_date is not None:
            sql += " AND EntryDate <= :through_date"
            params["through_date"] = through_date
        else:
            if date_from is not None:
                sql += " AND EntryDate >= :date_from"
                params["date_from"] = date_from
            if date_to is not None:
                sql += " AND EntryDate <= :date_to"
                params["date_to"] = date_to
        sql += " ORDER BY EntryDate DESC, EntryID DESC"
        rows = db.session.execute(text(sql), params).mappings().all()
        result = []
        for row in rows:
            result.append(
                {
                    "row_key": f"manual-{row['EntryID']}",
                    "entry_id": int(row["EntryID"]),
                    "source": "manual",
                    "can_edit": True,
                    "can_delete": True,
                    "entry_date": row["EntryDate"].isoformat() if row["EntryDate"] else "",
                    "description": row["Description"] or "Manual entry",
                    "reference": f"MANUAL-{row['EntryID']}",
                    "work": "Dashboard Manual",
                    "customer": row["CreatedBy"] or "—",
                    "amount": str(row["Amount"]),
                    "transaction_id": None,
                    "work_type": None,
                    "sub_work_type": None,
                    "source_module": "dashboard_manual",
                    "source_module_id": int(row["EntryID"]),
                    "source_url": None,
                    "can_open": True,
                }
            )
        return result

    def _daily_metric_rows(
        self, amount_column: str, date_from: date, date_to: date
    ) -> list[dict]:
        allowed = {
            "IncomeAmount": "Income",
            "ExpenseAmount": "Expense",
            "SaleAmount": "Sale",
            "TotalAmount": "Total",
        }
        if amount_column not in allowed:
            raise ValueError("Invalid amount column.")
        label = allowed[amount_column]
        rows = db.session.execute(
            text(
                f"""
                SELECT TOP 500
                    TransactionID,
                    TransactionDate,
                    WorkType,
                    SubWorkType,
                    StampID,
                    CustomerName,
                    ReferenceNo,
                    Description,
                    {amount_column} AS AmountValue
                FROM JTCSDailyTransaction
                WHERE TransactionDate >= :date_from
                  AND TransactionDate <= :date_to
                  AND Status = N'Posted'
                  AND ISNULL({amount_column}, 0) <> 0
                ORDER BY TransactionDate DESC, TransactionID DESC
                """
            ),
            {"date_from": date_from, "date_to": date_to},
        ).mappings().all()
        result = []
        for row in rows:
            work = row["WorkType"] or ""
            if row["SubWorkType"]:
                work = f"{work} / {row['SubWorkType']}" if work else row["SubWorkType"]
            reference = row["ReferenceNo"] or f"DT-{row['TransactionID']}"
            item = {
                "row_key": f"daily-{row['TransactionID']}",
                "entry_id": None,
                "source": "system",
                "can_edit": False,
                "can_delete": False,
                "entry_date": row["TransactionDate"].isoformat() if row["TransactionDate"] else "",
                "description": row["Description"] or label,
                "reference": reference,
                "work": work or "—",
                "customer": row["CustomerName"] or "—",
                "amount": str(row["AmountValue"]),
            }
            item.update(
                self._source_link_for_daily(
                    transaction_id=row["TransactionID"],
                    work_type=row["WorkType"],
                    sub_work_type=row["SubWorkType"],
                    stamp_id=row["StampID"],
                    reference=row["ReferenceNo"],
                )
            )
            result.append(item)
        return result

    def _posted_income_rows(self, date_from: date, date_to: date) -> list[dict]:
        """Total Income drill-down: IncomeAmount + SaleAmount (same as reports)."""
        rows = db.session.execute(
            text(
                """
                SELECT TOP 500
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
        result = []
        for row in rows:
            work = row["WorkType"] or ""
            if row["SubWorkType"]:
                work = f"{work} / {row['SubWorkType']}" if work else row["SubWorkType"]
            reference = row["ReferenceNo"] or f"DT-{row['TransactionID']}"
            item = {
                "row_key": f"daily-income-{row['TransactionID']}",
                "entry_id": None,
                "source": "system",
                "can_edit": False,
                "can_delete": False,
                "entry_date": row["TransactionDate"].isoformat() if row["TransactionDate"] else "",
                "description": row["Description"] or "Income",
                "reference": reference,
                "work": work or "—",
                "customer": row["CustomerName"] or "—",
                "amount": str(row["AmountValue"]),
            }
            item.update(
                self._source_link_for_daily(
                    transaction_id=row["TransactionID"],
                    work_type=row["WorkType"],
                    sub_work_type=row["SubWorkType"],
                    stamp_id=row["StampID"],
                    reference=row["ReferenceNo"],
                )
            )
            result.append(item)
        return result

    def _bank_metric_rows(
        self,
        *,
        cash_only: bool,
        mode: str,
        date_from: date,
        date_to: date,
    ) -> list[dict]:
        bank_filter = self._ledger_bank_filter(cash_only=cash_only, alias="a")
        if mode == "received":
            amount_sql = "ISNULL(t.Debit, 0)"
            where_extra = "AND ISNULL(t.Debit, 0) <> 0"
            date_clause = "t.TransactionDate >= :date_from AND t.TransactionDate <= :date_to"
            params = {"date_from": date_from, "date_to": date_to}
        else:
            # Closing drill-down: period movements only (opening balance added separately).
            # Amount = Debit - Credit so Total = Opening + Debit - Credit.
            amount_sql = "ISNULL(t.Debit, 0) - ISNULL(t.Credit, 0)"
            where_extra = ""
            date_clause = "t.TransactionDate >= :date_from AND t.TransactionDate <= :date_to"
            params = {"date_from": date_from, "date_to": date_to}

        order_sql = (
            "ORDER BY t.TransactionDate ASC, t.JtcsBankTransactionID ASC"
            if mode == "closing"
            else "ORDER BY t.TransactionDate DESC, t.JtcsBankTransactionID DESC"
        )

        rows = db.session.execute(
            text(
                f"""
                SELECT
                    t.JtcsBankTransactionID,
                    t.TransactionDate,
                    t.BankName,
                    t.MaskedAccountNumber,
                    t.Description,
                    t.Remarks,
                    t.SourceTable,
                    t.SourceRecordID,
                    ISNULL(t.Debit, 0) AS DebitValue,
                    ISNULL(t.Credit, 0) AS CreditValue,
                    {amount_sql} AS AmountValue
                FROM JtcsBankTransaction t
                INNER JOIN JtcsBankAccountMaster a
                    ON a.JtcsBankAccountID = t.JtcsBankAccountID
                WHERE {bank_filter}
                  AND {date_clause}
                  AND {BANK_MOVEMENT_SINCE_OPENING_SQL}
                  {where_extra}
                {order_sql}
                """
            ),
            params,
        ).mappings().all()
        result = []
        for row in rows:
            item = {
                "row_key": f"bank-{row['JtcsBankTransactionID']}",
                "entry_id": None,
                "source": "system",
                "can_edit": False,
                "can_delete": False,
                "entry_date": row["TransactionDate"].isoformat() if row["TransactionDate"] else "",
                "description": row["Description"] or row["Remarks"] or "Bank transaction",
                "reference": f"BT-{row['JtcsBankTransactionID']}",
                "work": row["BankName"] or "—",
                "customer": row["MaskedAccountNumber"] or "—",
                "amount": str(row["AmountValue"]),
                "debit": str(row["DebitValue"]),
                "credit": str(row["CreditValue"]),
            }
            item.update(
                self._source_link_for_bank_leg(
                    source_table=row["SourceTable"],
                    source_record_id=row["SourceRecordID"],
                    bank_transaction_id=row["JtcsBankTransactionID"],
                )
            )
            result.append(item)
        return result

    def _opening_balance_row(self, *, cash_only: bool, date_from: date) -> dict:
        opening = self._ledger_opening_balance(cash_only=cash_only, date_from=date_from)
        label = "Cash" if cash_only else "Bank"
        row = {
            "row_key": "opening-balance",
            "entry_id": None,
            "source": "opening",
            "can_edit": False,
            "can_delete": False,
            "entry_date": date_from.isoformat(),
            "description": f"Opening Balance (Bank Master as on {date_from.isoformat()})",
            "reference": "OPENING",
            "work": label,
            "customer": "—",
            "amount": str(opening.quantize(Decimal("0.01"))),
            "debit": "0",
            "credit": "0",
        }
        row.update(self._no_source_link())
        return row

    def get_metric_details(
        self,
        metric_key: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        self.ensure_schema()
        metric_key = self._validate_metric(metric_key)
        date_from, date_to = self._normalize_period(date_from, date_to)
        metrics = self.get_metrics(date_from, date_to)
        total_map = {
            "total_income": metrics.total_income,
            "total_expenses": metrics.total_expenses,
            "total_sales": metrics.total_sales,
            "cash_closing_balance": metrics.cash_closing_balance,
            "bank_closing_balance": metrics.bank_closing_balance,
            "cash_received": metrics.cash_received,
            "bank_received": metrics.bank_received,
        }

        opening_row = None
        if metric_key == "total_income":
            system_rows = self._posted_income_rows(date_from, date_to)
            manual_rows = self._manual_rows(metric_key, date_from=date_from, date_to=date_to)
        elif metric_key == "total_expenses":
            system_rows = self._daily_metric_rows("ExpenseAmount", date_from, date_to)
            manual_rows = self._manual_rows(metric_key, date_from=date_from, date_to=date_to)
        elif metric_key == "total_sales":
            system_rows = self._daily_metric_rows("SaleAmount", date_from, date_to)
            manual_rows = self._manual_rows(metric_key, date_from=date_from, date_to=date_to)
        elif metric_key == "cash_received":
            system_rows = self._bank_metric_rows(
                cash_only=True, mode="received", date_from=date_from, date_to=date_to
            )
            manual_rows = self._manual_rows(metric_key, date_from=date_from, date_to=date_to)
        elif metric_key == "bank_received":
            system_rows = self._bank_metric_rows(
                cash_only=False, mode="received", date_from=date_from, date_to=date_to
            )
            manual_rows = self._manual_rows(metric_key, date_from=date_from, date_to=date_to)
        elif metric_key == "cash_closing_balance":
            opening_row = self._opening_balance_row(cash_only=True, date_from=date_from)
            system_rows = self._bank_metric_rows(
                cash_only=True, mode="closing", date_from=date_from, date_to=date_to
            )
            manual_rows = self._manual_rows(metric_key, date_from=date_from, date_to=date_to)
        else:  # bank_closing_balance
            opening_row = self._opening_balance_row(cash_only=False, date_from=date_from)
            system_rows = self._bank_metric_rows(
                cash_only=False, mode="closing", date_from=date_from, date_to=date_to
            )
            manual_rows = self._manual_rows(metric_key, date_from=date_from, date_to=date_to)

        rows = []
        if opening_row is not None:
            rows.append(opening_row)
        movement_rows = list(manual_rows) + list(system_rows)
        if metric_key in {"cash_closing_balance", "bank_closing_balance"}:
            movement_rows.sort(
                key=lambda r: (
                    r.get("entry_date") or "",
                    r.get("reference") or "",
                    r.get("row_key") or "",
                )
            )
        rows.extend(movement_rows)
        return {
            "metric_key": metric_key,
            "metric_label": METRIC_LABELS[metric_key],
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "total": str(total_map[metric_key]),
            "opening_balance": opening_row["amount"] if opening_row else None,
            "rows": rows,
            "row_count": len(rows),
        }

    def add_manual_entry(
        self,
        *,
        metric_key: str,
        entry_date: date | None,
        amount,
        description: str | None,
        created_by: str,
    ) -> dict:
        self.ensure_schema()
        metric_key = self._validate_metric(metric_key)
        entry_date = entry_date or date.today()
        amount_value = self._decimal(amount)
        if amount_value == 0:
            raise ValueError("Amount cannot be zero.")
        desc = (description or "").strip() or None

        row = db.session.execute(
            text(
                """
                INSERT INTO DashboardManualEntry
                    (MetricKey, EntryDate, Description, Amount, CreatedBy, CreatedDate, IsActive)
                OUTPUT INSERTED.EntryID
                VALUES
                    (:metric_key, :entry_date, :description, :amount, :created_by, :created_date, 1)
                """
            ),
            {
                "metric_key": metric_key,
                "entry_date": entry_date,
                "description": desc,
                "amount": amount_value,
                "created_by": created_by,
                "created_date": datetime.utcnow(),
            },
        ).first()
        db.session.commit()
        entry_id = int(row[0]) if row else 0
        return {
            "entry_id": entry_id,
            "message": "Manual entry added.",
        }

    def update_manual_entry(
        self,
        entry_id: int,
        *,
        entry_date: date | None,
        amount,
        description: str | None,
    ) -> dict:
        self.ensure_schema()
        existing = db.session.execute(
            text(
                """
                SELECT EntryID, MetricKey
                FROM DashboardManualEntry
                WHERE EntryID = :entry_id AND IsActive = 1
                """
            ),
            {"entry_id": entry_id},
        ).mappings().first()
        if not existing:
            raise ValueError("Manual entry not found.")

        entry_date = entry_date or date.today()
        amount_value = self._decimal(amount)
        if amount_value == 0:
            raise ValueError("Amount cannot be zero.")
        desc = (description or "").strip() or None

        db.session.execute(
            text(
                """
                UPDATE DashboardManualEntry
                SET EntryDate = :entry_date,
                    Description = :description,
                    Amount = :amount,
                    ModifiedDate = :modified_date
                WHERE EntryID = :entry_id
                  AND IsActive = 1
                """
            ),
            {
                "entry_id": entry_id,
                "entry_date": entry_date,
                "description": desc,
                "amount": amount_value,
                "modified_date": datetime.utcnow(),
            },
        )
        db.session.commit()
        return {
            "entry_id": entry_id,
            "metric_key": existing["MetricKey"],
            "message": "Manual entry updated.",
        }

    def delete_manual_entry(self, entry_id: int) -> dict:
        self.ensure_schema()
        existing = db.session.execute(
            text(
                """
                SELECT EntryID, MetricKey
                FROM DashboardManualEntry
                WHERE EntryID = :entry_id AND IsActive = 1
                """
            ),
            {"entry_id": entry_id},
        ).mappings().first()
        if not existing:
            raise ValueError("Manual entry not found.")

        db.session.execute(
            text(
                """
                UPDATE DashboardManualEntry
                SET IsActive = 0,
                    ModifiedDate = :modified_date
                WHERE EntryID = :entry_id
                """
            ),
            {"entry_id": entry_id, "modified_date": datetime.utcnow()},
        )
        db.session.commit()
        return {
            "entry_id": entry_id,
            "metric_key": existing["MetricKey"],
            "message": "Manual entry deleted.",
        }

    def delete_ecourt_source_sale(self, sale_id: int) -> dict:
        """Unsell/roll back the e-Court sale linked from a dashboard closing row."""
        from app.services.ecourt_service import ECourtService

        sale = db.session.execute(
            text(
                """
                SELECT TOP 1 SaleID, ReceiptNo
                FROM ECourtSale
                WHERE SaleID = :sale_id
                """
            ),
            {"sale_id": int(sale_id)},
        ).first()
        if not sale:
            raise ValueError("e-Court sale not found.")

        receipt_no = (sale[1] or "").strip()
        if not receipt_no:
            raise ValueError("e-Court sale has no receipt number.")

        try:
            result = ECourtService().unsell_receipts([receipt_no])
            db.session.commit()
            return result
        except Exception:
            db.session.rollback()
            raise

    @staticmethod
    def _money(value) -> float:
        return float(Decimal(str(value or 0)).quantize(Decimal("0.01")))

    def get_analytics(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        """Aggregated posted daily-transaction series for dashboard charts."""
        date_from, date_to = self._normalize_period(date_from, date_to)
        span_days = (date_to - date_from).days + 1
        monthly = span_days > 45

        daily_rows = db.session.execute(
            text(
                """
                SELECT
                    CAST(TransactionDate AS DATE) AS txn_date,
                    ISNULL(SUM(ISNULL(IncomeAmount, 0) + ISNULL(SaleAmount, 0)), 0) AS collection_amount,
                    ISNULL(SUM(ISNULL(IncomeAmount, 0) + ISNULL(SaleAmount, 0)), 0) AS income_amount,
                    ISNULL(SUM(ISNULL(ExpenseAmount, 0)), 0) AS expense_amount
                FROM JTCSDailyTransaction
                WHERE TransactionDate >= :date_from
                  AND TransactionDate <= :date_to
                  AND Status = N'Posted'
                GROUP BY CAST(TransactionDate AS DATE)
                ORDER BY CAST(TransactionDate AS DATE)
                """
            ),
            {"date_from": date_from, "date_to": date_to},
        ).mappings().all()

        by_date: dict[date, dict[str, Decimal]] = {}
        for row in daily_rows:
            txn_date = row["txn_date"]
            if hasattr(txn_date, "date"):
                txn_date = txn_date.date()
            by_date[txn_date] = {
                "collection": Decimal(str(row["collection_amount"] or 0)),
                "income": Decimal(str(row["income_amount"] or 0)),
                "expense": Decimal(str(row["expense_amount"] or 0)),
            }

        collection_labels: list[str] = []
        collection_values: list[float] = []
        has_collection = any(v["collection"] != 0 for v in by_date.values())
        if has_collection:
            cursor = date_from
            while cursor <= date_to:
                collection_labels.append(cursor.strftime("%d-%b"))
                collection_values.append(
                    self._money(by_date.get(cursor, {}).get("collection", 0))
                )
                cursor += timedelta(days=1)

        income_labels: list[str] = []
        income_values: list[float] = []
        expense_values: list[float] = []
        net_values: list[float] = []
        has_pl = any(v["income"] != 0 or v["expense"] != 0 for v in by_date.values())
        if has_pl:
            if monthly:
                buckets: dict[date, dict[str, Decimal]] = {}
                cursor = date_from
                while cursor <= date_to:
                    key = date(cursor.year, cursor.month, 1)
                    bucket = buckets.setdefault(
                        key, {"income": Decimal("0"), "expense": Decimal("0")}
                    )
                    day = by_date.get(cursor)
                    if day:
                        bucket["income"] += day["income"]
                        bucket["expense"] += day["expense"]
                    cursor += timedelta(days=1)
                for key in sorted(buckets):
                    income_labels.append(f"{month_abbr[key.month]} {key.year}")
                    inc = buckets[key]["income"]
                    exp = buckets[key]["expense"]
                    income_values.append(self._money(inc))
                    expense_values.append(self._money(exp))
                    net_values.append(self._money(inc - exp))
            else:
                cursor = date_from
                while cursor <= date_to:
                    income_labels.append(cursor.strftime("%d-%b"))
                    day = by_date.get(cursor, {})
                    inc = day.get("income", Decimal("0"))
                    exp = day.get("expense", Decimal("0"))
                    income_values.append(self._money(inc))
                    expense_values.append(self._money(exp))
                    net_values.append(self._money(inc - exp))
                    cursor += timedelta(days=1)

        activity_rows = db.session.execute(
            text(
                """
                SELECT
                    CASE
                        WHEN NULLIF(LTRIM(RTRIM(WorkType)), N'') IS NULL THEN N'Other'
                        ELSE LTRIM(RTRIM(WorkType))
                    END AS activity,
                    ISNULL(SUM(ISNULL(IncomeAmount, 0) + ISNULL(SaleAmount, 0)), 0) AS amount
                FROM JTCSDailyTransaction
                WHERE TransactionDate >= :date_from
                  AND TransactionDate <= :date_to
                  AND Status = N'Posted'
                GROUP BY
                    CASE
                        WHEN NULLIF(LTRIM(RTRIM(WorkType)), N'') IS NULL THEN N'Other'
                        ELSE LTRIM(RTRIM(WorkType))
                    END
                HAVING ISNULL(SUM(ISNULL(IncomeAmount, 0) + ISNULL(SaleAmount, 0)), 0) <> 0
                ORDER BY amount DESC
                """
            ),
            {"date_from": date_from, "date_to": date_to},
        ).mappings().all()

        activity_labels = [str(row["activity"] or "Other") for row in activity_rows]
        activity_values = [self._money(row["amount"]) for row in activity_rows]
        if len(activity_labels) > 10:
            other_total = sum(activity_values[9:])
            activity_labels = activity_labels[:9] + ["Other"]
            activity_values = activity_values[:9] + [round(other_total, 2)]

        payment_rows = db.session.execute(
            text(
                """
                SELECT payment_mode, ISNULL(SUM(amount), 0) AS amount
                FROM (
                    SELECT
                        ISNULL(NULLIF(LTRIM(RTRIM(pm.PaymentModeName)), N''), N'Unspecified') AS payment_mode,
                        ISNULL(p.Amount, 0) AS amount
                    FROM JTCSDailyTransaction d
                    INNER JOIN JTCSDailyTransactionPayment p
                        ON p.TransactionID = d.TransactionID
                    LEFT JOIN PaymentModeMaster pm
                        ON pm.PaymentModeID = COALESCE(p.PaymentModeID, d.PaymentModeID)
                    WHERE d.TransactionDate >= :date_from
                      AND d.TransactionDate <= :date_to
                      AND d.Status = N'Posted'
                      AND ISNULL(d.ExpenseAmount, 0) = 0
                      AND ISNULL(p.Amount, 0) <> 0
                    UNION ALL
                    SELECT
                        ISNULL(NULLIF(LTRIM(RTRIM(pm.PaymentModeName)), N''), N'Unspecified') AS payment_mode,
                        ISNULL(d.IncomeAmount, 0) + ISNULL(d.SaleAmount, 0) AS amount
                    FROM JTCSDailyTransaction d
                    LEFT JOIN PaymentModeMaster pm
                        ON pm.PaymentModeID = d.PaymentModeID
                    WHERE d.TransactionDate >= :date_from
                      AND d.TransactionDate <= :date_to
                      AND d.Status = N'Posted'
                      AND ISNULL(d.IncomeAmount, 0) + ISNULL(d.SaleAmount, 0) <> 0
                      AND NOT EXISTS (
                            SELECT 1
                            FROM JTCSDailyTransactionPayment p
                            WHERE p.TransactionID = d.TransactionID
                      )
                ) src
                GROUP BY payment_mode
                HAVING ISNULL(SUM(amount), 0) <> 0
                ORDER BY amount DESC
                """
            ),
            {"date_from": date_from, "date_to": date_to},
        ).mappings().all()

        payment_labels = [
            str(row["payment_mode"] or "Unspecified") for row in payment_rows
        ]
        payment_values = [self._money(row["amount"]) for row in payment_rows]

        collection_total = round(sum(collection_values), 2)
        income_total = round(sum(income_values), 2)
        expense_total = round(sum(expense_values), 2)

        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "group": "month" if monthly else "day",
            "daily_collection": {
                "labels": collection_labels,
                "values": collection_values,
                "total": collection_total,
                "empty": not has_collection,
            },
            "by_activity": {
                "labels": activity_labels,
                "values": activity_values,
                "chart": "doughnut" if 0 < len(activity_labels) <= 7 else "bar",
                "total": round(sum(activity_values), 2),
                "empty": not activity_labels,
            },
            "income_expense": {
                "labels": income_labels,
                "income": income_values,
                "expense": expense_values,
                "net": net_values,
                "income_total": income_total,
                "expense_total": expense_total,
                "net_total": round(income_total - expense_total, 2),
                "empty": not has_pl,
            },
            "payment_mode": {
                "labels": payment_labels,
                "values": payment_values,
                "total": round(sum(payment_values), 2),
                "empty": not payment_labels,
            },
        }
