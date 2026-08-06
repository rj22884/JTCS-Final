"""Reusable Financial Report Engine — group tree + ledger balances + drill-down."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.extensions import db
from app.utils.opening_balance import default_dr_cr_for_under_type

ZERO = Decimal("0.00")

# Child → Parent (Tally-like). Parents may be synthetic nature roots.
PARENT_MAP: dict[str, str | None] = {
    "Current Assets": None,
    "Fixed Assets": None,
    "Investments": None,
    "Bank Accounts": "Current Assets",
    "Cash-in-Hand": "Current Assets",
    "Sundry Debtors": "Current Assets",
    "Stock-in-Hand": "Current Assets",
    "Deposits (Asset)": "Current Assets",
    "Loans & Advances (Asset)": "Current Assets",
    "Stock Holding Corporation of India": "Current Assets",
    "Individual Client": "Current Assets",
    "Suspense A/c": "Current Assets",
    "Bank OCC A/c": "Current Assets",
    "Computers Printers & Electric Items": "Fixed Assets",
    "Immovable Property": "Fixed Assets",
    "Misc. Expenses (ASSET)": None,
    "Capital Account": None,
    "Reserves & Surplus": None,
    "Retained Earnings": "Reserves & Surplus",
    "Current Liabilities": None,
    "Loans (Liability)": None,
    "Sundry Creditors": "Current Liabilities",
    "Duties & Taxes": "Current Liabilities",
    "Provisions": "Current Liabilities",
    "Branch / Divisions": "Current Liabilities",
    "Secured Loans": "Loans (Liability)",
    "Unsecured Loans": "Loans (Liability)",
    "Bank OD A/c": "Loans (Liability)",
    "Sales Accounts": None,
    "Direct Incomes": None,
    "Income (Direct)": "Direct Incomes",
    "Commission Income": "Direct Incomes",
    "Rent Income": "Indirect Incomes",
    "Indirect Incomes": None,
    "Income (Indirect)": "Indirect Incomes",
    "Purchase Accounts": None,
    "Direct Expenses": None,
    "Expenses (Direct)": "Direct Expenses",
    "Salary and Wages": "Direct Expenses",
    "Electricity Expenses": "Indirect Expenses",
    "Indirect Expenses": None,
    "Expenses (Indirect)": "Indirect Expenses",
}

NATURE_BY_NAME: dict[str, str] = {
    "Current Assets": "Asset",
    "Fixed Assets": "Asset",
    "Investments": "Asset",
    "Bank Accounts": "Asset",
    "Cash-in-Hand": "Asset",
    "Sundry Debtors": "Asset",
    "Stock-in-Hand": "Asset",
    "Deposits (Asset)": "Asset",
    "Loans & Advances (Asset)": "Asset",
    "Stock Holding Corporation of India": "Asset",
    "Individual Client": "Asset",
    "Suspense A/c": "Asset",
    "Bank OCC A/c": "Asset",
    "Computers Printers & Electric Items": "Asset",
    "Immovable Property": "Asset",
    "Misc. Expenses (ASSET)": "Asset",
    "Capital Account": "Liability",
    "Reserves & Surplus": "Liability",
    "Retained Earnings": "Liability",
    "Current Liabilities": "Liability",
    "Loans (Liability)": "Liability",
    "Sundry Creditors": "Liability",
    "Duties & Taxes": "Liability",
    "Provisions": "Liability",
    "Branch / Divisions": "Liability",
    "Secured Loans": "Liability",
    "Unsecured Loans": "Liability",
    "Bank OD A/c": "Liability",
    "Sales Accounts": "Income",
    "Direct Incomes": "Income",
    "Income (Direct)": "Income",
    "Commission Income": "Income",
    "Rent Income": "Income",
    "Indirect Incomes": "Income",
    "Income (Indirect)": "Income",
    "Purchase Accounts": "Expense",
    "Direct Expenses": "Expense",
    "Expenses (Direct)": "Expense",
    "Salary and Wages": "Expense",
    "Electricity Expenses": "Expense",
    "Indirect Expenses": "Expense",
    "Expenses (Indirect)": "Expense",
}


class FinancialReportEngine:
    """
    Server-side aggregation engine.

    Closing = Opening (± Dr/Cr) + period Debits − period Credits
    (signed by account nature for statement presentation).
    """

    def __init__(self):
        self._schema_ready = False

    @staticmethod
    def money(value) -> Decimal:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))

    @staticmethod
    def fy_start(as_of: date | None = None) -> date:
        as_of = as_of or date.today()
        year = as_of.year if as_of.month >= 4 else as_of.year - 1
        return date(year, 4, 1)

    @staticmethod
    def fy_end(as_of: date | None = None) -> date:
        start = FinancialReportEngine.fy_start(as_of)
        return date(start.year + 1, 3, 31)

    @staticmethod
    def parse_date(raw: str | None, fallback: date) -> date:
        value = (raw or "").strip()
        if not value:
            return fallback
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return fallback

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        from app.repositories.chart_account_repository import ChartAccountRepository
        from app.repositories.chart_group_repository import ChartGroupRepository

        ChartGroupRepository().ensure_schema()
        ChartAccountRepository().ensure_schema()
        try:
            from app.repositories.bank_master_repository import BankMasterRepository

            BankMasterRepository().ensure_schema()
        except Exception:
            db.session.rollback()
        db.session.execute(
            text(
                """
                IF COL_LENGTH(N'dbo.ChartOfGroupMaster', N'ParentGroupID') IS NULL
                    ALTER TABLE dbo.ChartOfGroupMaster ADD ParentGroupID INT NULL;
                """
            )
        )
        db.session.execute(
            text(
                """
                IF COL_LENGTH(N'dbo.ChartOfGroupMaster', N'GroupNature') IS NULL
                    ALTER TABLE dbo.ChartOfGroupMaster ADD GroupNature NVARCHAR(20) NULL;
                """
            )
        )
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.ChartOfGroupMaster', N'U') IS NOT NULL
                   AND COL_LENGTH(N'dbo.ChartOfGroupMaster', N'ParentGroupID') IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM sys.foreign_keys
                       WHERE name = N'FK_ChartOfGroupMaster_Parent'
                         AND parent_object_id = OBJECT_ID(N'dbo.ChartOfGroupMaster')
                   )
                    ALTER TABLE dbo.ChartOfGroupMaster
                        ADD CONSTRAINT FK_ChartOfGroupMaster_Parent
                        FOREIGN KEY (ParentGroupID) REFERENCES dbo.ChartOfGroupMaster (GroupID);
                """
            )
        )
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.FixedAssetMaster', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.FixedAssetMaster (
                        AssetID                 INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        AssetName               NVARCHAR(200) NOT NULL,
                        AccountID               INT NULL,
                        GroupID                 INT NULL,
                        PurchaseDate            DATE NOT NULL,
                        PurchaseValue           DECIMAL(18, 2) NOT NULL,
                        DepreciationRate        DECIMAL(9, 4) NOT NULL CONSTRAINT DF_FixedAsset_Rate DEFAULT (0),
                        OpeningAccumulatedDep   DECIMAL(18, 2) NOT NULL CONSTRAINT DF_FixedAsset_OpenAcc DEFAULT (0),
                        CurrentYearDepreciation DECIMAL(18, 2) NOT NULL CONSTRAINT DF_FixedAsset_CYDep DEFAULT (0),
                        AccumulatedDepreciation DECIMAL(18, 2) NOT NULL CONSTRAINT DF_FixedAsset_Acc DEFAULT (0),
                        WDV                     DECIMAL(18, 2) NOT NULL CONSTRAINT DF_FixedAsset_WDV DEFAULT (0),
                        Method                  NVARCHAR(20) NOT NULL CONSTRAINT DF_FixedAsset_Method DEFAULT (N'WDV'),
                        IsActive                BIT NOT NULL CONSTRAINT DF_FixedAsset_Active DEFAULT (1),
                        CreatedDate             DATETIME2 NOT NULL CONSTRAINT DF_FixedAsset_Created DEFAULT (SYSUTCDATETIME()),
                        UpdatedDate             DATETIME2 NULL
                    );
                END
                """
            )
        )
        db.session.commit()
        self._backfill_group_hierarchy()
        self._schema_ready = True

    def _backfill_group_hierarchy(self) -> None:
        rows = db.session.execute(
            text(
                """
                SELECT GroupID, GroupName, UnderType, ParentGroupID, GroupNature
                FROM dbo.ChartOfGroupMaster
                """
            )
        ).mappings().all()
        by_name = {(r["GroupName"] or "").strip(): dict(r) for r in rows}
        for name, row in by_name.items():
            nature = NATURE_BY_NAME.get(name)
            if not nature:
                nature = "Asset" if (row.get("UnderType") or "") == "Assets" else "Liability"
            parent_name = PARENT_MAP.get(name)
            parent_id = None
            if parent_name and parent_name in by_name:
                parent_id = by_name[parent_name]["GroupID"]
            need_nature = not (row.get("GroupNature") or "").strip()
            need_parent = row.get("ParentGroupID") is None and parent_id is not None
            if need_nature or need_parent:
                db.session.execute(
                    text(
                        """
                        UPDATE dbo.ChartOfGroupMaster
                        SET GroupNature = COALESCE(NULLIF(GroupNature, N''), :nature),
                            ParentGroupID = CASE
                                WHEN ParentGroupID IS NULL THEN :parent_id
                                ELSE ParentGroupID
                            END,
                            UpdatedDate = SYSUTCDATETIME()
                        WHERE GroupID = :gid
                        """
                    ),
                    {
                        "nature": nature,
                        "parent_id": parent_id,
                        "gid": row["GroupID"],
                    },
                )
        db.session.commit()

    def load_groups(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        self.ensure_schema()
        sql = """
            SELECT GroupID, GroupName, UnderType, ParentGroupID,
                   ISNULL(NULLIF(GroupNature, N''),
                          CASE WHEN UnderType = N'Assets' THEN N'Asset' ELSE N'Liability' END
                   ) AS GroupNature,
                   IsActive
            FROM dbo.ChartOfGroupMaster
        """
        if active_only:
            sql += " WHERE IsActive = 1"
        sql += " ORDER BY GroupName"
        return [dict(r) for r in db.session.execute(text(sql)).mappings().all()]

    def build_group_tree(self, groups: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        groups = groups if groups is not None else self.load_groups()
        by_id = {int(g["GroupID"]): {**g, "children": [], "ledgers": []} for g in groups}
        roots: list[dict[str, Any]] = []
        for gid, node in by_id.items():
            pid = node.get("ParentGroupID")
            if pid and int(pid) in by_id and int(pid) != gid:
                by_id[int(pid)]["children"].append(node)
            else:
                roots.append(node)
        return roots

    def _signed_opening(self, amount, dr_cr: str | None, nature: str) -> Decimal:
        amt = abs(self.money(amount))
        token = (dr_cr or default_dr_cr_for_under_type(
            "Assets" if nature in {"Asset", "Expense"} else "Liabilities"
        )).strip().lower()
        is_dr = token in {"dr", "d", "debit"}
        # Asset/Expense increase with Dr; Liability/Income increase with Cr
        if nature in {"Asset", "Expense"}:
            return amt if is_dr else -amt
        return -amt if is_dr else amt

    def load_ledger_rows(self) -> list[dict[str, Any]]:
        """Unified ledger list: CoA rows + bank accounts mapped by ChartGroupID."""
        self.ensure_schema()
        ledgers: list[dict[str, Any]] = []

        coa = db.session.execute(
            text(
                """
                SELECT
                    a.AccountID,
                    a.AccountName,
                    a.GroupID,
                    a.CustomerID,
                    a.WorkID,
                    a.OpeningBalance,
                    a.OpeningBalanceDate,
                    a.OpeningBalanceDrCr,
                    a.IsActive,
                    g.GroupName,
                    g.UnderType,
                    ISNULL(NULLIF(g.GroupNature, N''),
                           CASE WHEN g.UnderType = N'Assets' THEN N'Asset' ELSE N'Liability' END
                    ) AS GroupNature
                FROM dbo.ChartOfAccountMaster a
                INNER JOIN dbo.ChartOfGroupMaster g ON g.GroupID = a.GroupID
                WHERE a.IsActive = 1
                """
            )
        ).mappings().all()
        for r in coa:
            nature = (r.get("GroupNature") or "Asset").strip()
            ledgers.append(
                {
                    "ledger_key": f"coa-{r['AccountID']}",
                    "source": "coa",
                    "account_id": int(r["AccountID"]),
                    "bank_account_id": None,
                    "customer_id": int(r["CustomerID"]) if r.get("CustomerID") else None,
                    "work_id": int(r["WorkID"]) if r.get("WorkID") else None,
                    "ledger_name": (r.get("AccountName") or "").strip(),
                    "group_id": int(r["GroupID"]),
                    "group_name": r.get("GroupName") or "",
                    "nature": nature,
                    "opening_raw": r.get("OpeningBalance"),
                    "opening_date": r.get("OpeningBalanceDate"),
                    "opening_dr_cr": r.get("OpeningBalanceDrCr"),
                }
            )

        banks = db.session.execute(
            text(
                """
                SELECT
                    b.JtcsBankAccountID,
                    b.BankName,
                    b.AccountNumber,
                    b.OpeningBalance,
                    b.OpeningBalanceDate,
                    b.OpeningBalanceDrCr,
                    b.ChartGroupID,
                    b.ActiveStatus,
                    g.GroupName,
                    g.UnderType,
                    ISNULL(NULLIF(g.GroupNature, N''), N'Asset') AS GroupNature
                FROM dbo.JtcsBankAccountMaster b
                LEFT JOIN dbo.ChartOfGroupMaster g ON g.GroupID = b.ChartGroupID
                WHERE ISNULL(b.ActiveStatus, 1) = 1
                  AND b.ChartGroupID IS NOT NULL
                """
            )
        ).mappings().all()
        for r in banks:
            name = (r.get("BankName") or "").strip()
            if (r.get("AccountNumber") or "").strip():
                name = f"{name} ({r['AccountNumber']})"
            nature = (r.get("GroupNature") or "Asset").strip()
            # Prefer UnderType when group nature is missing/odd so banks stay
            # on the correct BS side for their ChartGroupID placement.
            under = (r.get("UnderType") or "").strip()
            if under == "Assets":
                nature = "Asset"
            elif under == "Liabilities":
                nature = "Liability"
            ledgers.append(
                {
                    "ledger_key": f"bank-{r['JtcsBankAccountID']}",
                    "source": "bank",
                    "account_id": None,
                    "bank_account_id": int(r["JtcsBankAccountID"]),
                    "customer_id": None,
                    "work_id": None,
                    "ledger_name": name or f"Bank #{r['JtcsBankAccountID']}",
                    "group_id": int(r["ChartGroupID"]),
                    "group_name": r.get("GroupName") or "",
                    "nature": nature,
                    "opening_raw": r.get("OpeningBalance"),
                    "opening_date": r.get("OpeningBalanceDate"),
                    "opening_dr_cr": r.get("OpeningBalanceDrCr") or "Dr",
                }
            )
        return ledgers

    def _bank_opening_as_of(self, bank_account_id: int, date_from: date) -> Decimal:
        """Master OB + prior Debit−Credit on/after OpeningBalanceDate only."""
        row = db.session.execute(
            text(
                """
                SELECT OpeningBalance, OpeningBalanceDate
                FROM dbo.JtcsBankAccountMaster
                WHERE JtcsBankAccountID = :bid
                """
            ),
            {"bid": bank_account_id},
        ).mappings().first()
        if not row:
            return ZERO
        opening = ZERO
        ob_date = row.get("OpeningBalanceDate")
        if isinstance(ob_date, datetime):
            ob_date = ob_date.date()
        if ob_date is None or ob_date <= date_from:
            opening = self.money(row.get("OpeningBalance"))
        prior_sql = """
                SELECT ISNULL(SUM(ISNULL(Debit, 0) - ISNULL(Credit, 0)), 0)
                FROM dbo.JtcsBankTransaction
                WHERE JtcsBankAccountID = :bid
                  AND TransactionDate < :d1
            """
        prior_params = {"bid": bank_account_id, "d1": date_from}
        if ob_date is not None:
            prior_sql += " AND TransactionDate >= :ob_date"
            prior_params["ob_date"] = ob_date
        prior = db.session.execute(text(prior_sql), prior_params).scalar()
        return self.money(opening + self.money(prior))

    def _customer_has_opening_cols(self) -> bool:
        try:
            return bool(
                db.session.execute(
                    text(
                        "SELECT CASE WHEN COL_LENGTH(N'dbo.CustomerMaster', N'OpeningBalance') "
                        "IS NULL THEN 0 ELSE 1 END"
                    )
                ).scalar()
            )
        except Exception:
            db.session.rollback()
            return False

    def _customer_opening_as_of(self, customer_id: int, date_from: date) -> Decimal:
        """
        Same opening as Ledger Export / Customer Ledger:
        CustomerMaster OB (Dr receivable / Cr advance) + prior (billed − received).
        """
        opening = ZERO
        ob_date = None
        if self._customer_has_opening_cols():
            row = db.session.execute(
                text(
                    """
                    SELECT ISNULL(OpeningBalance, 0) AS OpeningBalance,
                           OpeningBalanceDate,
                           OpeningBalanceDrCr
                    FROM dbo.CustomerMaster
                    WHERE CustomerID = :cid
                    """
                ),
                {"cid": customer_id},
            ).mappings().first()
            if row:
                ob_date = row.get("OpeningBalanceDate")
                if isinstance(ob_date, datetime):
                    ob_date = ob_date.date()
                ob_amount = self.money(row.get("OpeningBalance"))
                ob_type = (row.get("OpeningBalanceDrCr") or "Dr").strip()
                signed_ob = (
                    ob_amount if ob_type.upper().startswith("D") else -ob_amount
                )
                if ob_amount != ZERO and (ob_date is None or ob_date <= date_from):
                    opening = signed_ob

        prior_params: dict[str, Any] = {
            "customer_id": customer_id,
            "date_from": date_from,
        }
        prior_date_sql = "AND d.TransactionDate < :date_from"
        if ob_date is not None:
            prior_date_sql += " AND d.TransactionDate > :ob_date"
            prior_params["ob_date"] = ob_date

        # Match Ledger Export prior: billed − bank debit on linked bank txn
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
        billed = self.money(prior["billed"] if prior else 0)
        received = self.money(prior["received"] if prior else 0)
        # Unpaid Followup Tally bills (not yet in JTCSDailyTransaction)
        followup_billed = ZERO
        try:
            fu_sql = "AND ISNULL(f.BillDate, f.WorkDate) < :date_from"
            fu_params: dict[str, Any] = {
                "customer_id": customer_id,
                "date_from": date_from,
            }
            if ob_date is not None:
                fu_sql += " AND ISNULL(f.BillDate, f.WorkDate) > :ob_date"
                fu_params["ob_date"] = ob_date
            followup_billed = self.money(
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
                          {fu_sql}
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
                    fu_params,
                ).scalar()
            )
        except Exception:
            db.session.rollback()
            followup_billed = ZERO
        return self.money(opening + billed + followup_billed - received)

    def _period_movements(
        self,
        *,
        date_from: date,
        date_to: date,
    ) -> dict[str, dict[str, Decimal]]:
        """Return ledger_key → {debit, credit} for the period."""
        moves: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: {"debit": ZERO, "credit": ZERO}
        )

        # Bank transactions → bank ledgers
        bank_rows = db.session.execute(
            text(
                """
                SELECT JtcsBankAccountID,
                       SUM(ISNULL(Debit, 0)) AS DebitAmt,
                       SUM(ISNULL(Credit, 0)) AS CreditAmt
                FROM dbo.JtcsBankTransaction
                WHERE TransactionDate >= :d1 AND TransactionDate <= :d2
                GROUP BY JtcsBankAccountID
                """
            ),
            {"d1": date_from, "d2": date_to},
        ).mappings().all()
        for r in bank_rows:
            key = f"bank-{int(r['JtcsBankAccountID'])}"
            moves[key]["debit"] += self.money(r["DebitAmt"])
            moves[key]["credit"] += self.money(r["CreditAmt"])

        # Customer ledgers — same as Customer Ledger / Ledger Export:
        # Debit = billed (Sale+Income), Credit = receipt (PaymentTotal else BankDebit)
        cust_to_coa = {
            int(row["CustomerID"]): int(row["AccountID"])
            for row in db.session.execute(
                text(
                    """
                    SELECT AccountID, CustomerID FROM dbo.ChartOfAccountMaster
                    WHERE CustomerID IS NOT NULL AND IsActive = 1
                    """
                )
            ).mappings().all()
            if row.get("CustomerID")
        }
        cust_rows = db.session.execute(
            text(
                """
                SELECT
                    d.CustomerID,
                    ISNULL(d.SaleAmount, 0) + ISNULL(d.IncomeAmount, 0) AS Billed,
                    ISNULL(b.Debit, 0) AS BankDebit,
                    (
                        SELECT ISNULL(SUM(p.Amount), 0)
                        FROM dbo.JTCSDailyTransactionPayment p
                        WHERE p.TransactionID = d.TransactionID
                    ) AS PaymentTotal
                FROM dbo.JTCSDailyTransaction d
                LEFT JOIN dbo.JtcsBankTransaction b
                    ON b.JtcsBankTransactionID = d.BankTransactionID
                WHERE d.CustomerID IS NOT NULL
                  AND d.Status = N'Posted'
                  AND d.TransactionDate >= :d1
                  AND d.TransactionDate <= :d2
                """
            ),
            {"d1": date_from, "d2": date_to},
        ).mappings().all()
        for r in cust_rows:
            cid = int(r["CustomerID"])
            aid = cust_to_coa.get(cid)
            if not aid:
                continue
            key = f"coa-{aid}"
            billed = self.money(r["Billed"])
            receipt = self.money(r["PaymentTotal"])
            if receipt == ZERO:
                receipt = self.money(r["BankDebit"])
            moves[key]["debit"] += billed
            moves[key]["credit"] += receipt

        # Unpaid Followup Tally bills → customer CoA debit (receivable)
        try:
            fu_rows = db.session.execute(
                text(
                    """
                    SELECT f.CustomerID, ISNULL(f.BillAmount, 0) AS BillAmount
                    FROM dbo.FollowupEntryMaster f
                    WHERE f.CustomerID IS NOT NULL
                      AND ISNULL(f.IsActive, 1) = 1
                      AND f.BillNo IS NOT NULL
                      AND LTRIM(RTRIM(f.BillNo)) <> N''
                      AND ISNULL(f.BillAmount, 0) > 0
                      AND ISNULL(f.BillDate, f.WorkDate) >= :d1
                      AND ISNULL(f.BillDate, f.WorkDate) <= :d2
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
                {"d1": date_from, "d2": date_to},
            ).mappings().all()
            for r in fu_rows:
                cid = int(r["CustomerID"])
                aid = cust_to_coa.get(cid)
                if not aid:
                    continue
                moves[f"coa-{aid}"]["debit"] += self.money(r["BillAmount"])
        except Exception:
            db.session.rollback()

        # Work-linked others + daily → coa by WorkID
        work_to_coa = {
            int(r["WorkID"]): int(r["AccountID"])
            for r in db.session.execute(
                text(
                    """
                    SELECT AccountID, WorkID FROM dbo.ChartOfAccountMaster
                    WHERE WorkID IS NOT NULL AND IsActive = 1
                    """
                )
            ).mappings().all()
            if r.get("WorkID")
        }

        try:
            work_oie = db.session.execute(
                text(
                    """
                    SELECT d.WorkID,
                           SUM(CASE WHEN w.LedgerKind = N'Expense' THEN ISNULL(d.Amount, 0) ELSE 0 END) AS DebitSide,
                           SUM(CASE WHEN w.LedgerKind IN (N'Income', N'Misc.') THEN ISNULL(d.Amount, 0) ELSE 0 END) AS CreditSide
                    FROM dbo.OthersIncomeExpenseDetail d
                    INNER JOIN dbo.OthersIncomeExpenseMaster m ON m.EntryID = d.EntryID
                    INNER JOIN dbo.WorkMaster w ON w.WorkID = d.WorkID
                    WHERE m.WorkDate >= :d1 AND m.WorkDate <= :d2
                      AND ISNULL(m.IsActive, 1) = 1
                      AND d.WorkID IS NOT NULL
                    GROUP BY d.WorkID
                    """
                ),
                {"d1": date_from, "d2": date_to},
            ).mappings().all()
            for r in work_oie:
                wid = int(r["WorkID"])
                aid = work_to_coa.get(wid)
                if not aid:
                    continue
                key = f"coa-{aid}"
                moves[key]["debit"] += self.money(r["DebitSide"])
                moves[key]["credit"] += self.money(r["CreditSide"])
        except Exception:
            db.session.rollback()

        return moves

    def compute_ledger_balances(
        self,
        *,
        date_from: date,
        date_to: date,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """Opening + period movements + closing for every ledger."""
        self.ensure_schema()
        ledgers = self.load_ledger_rows()
        moves = self._period_movements(date_from=date_from, date_to=date_to)
        needle = (search or "").strip().lower()
        result = []
        for led in ledgers:
            if needle and needle not in (led["ledger_name"] or "").lower():
                continue
            nature = led["nature"]
            if led.get("source") == "bank" and led.get("bank_account_id"):
                # Align Balance Sheet bank totals with Ledger Export
                # (master OB + prior Dr−Cr, then period Dr−Cr).
                opening = self._bank_opening_as_of(int(led["bank_account_id"]), date_from)
            elif led.get("customer_id"):
                # Align with Customer Ledger / Ledger Export closing.
                opening = self._customer_opening_as_of(int(led["customer_id"]), date_from)
            else:
                opening = self._signed_opening(
                    led.get("opening_raw"), led.get("opening_dr_cr"), nature
                )
                ob_date = led.get("opening_date")
                if ob_date and isinstance(ob_date, datetime):
                    ob_date = ob_date.date()
                if ob_date and ob_date > date_to:
                    opening = ZERO
            mv = moves.get(led["ledger_key"], {"debit": ZERO, "credit": ZERO})
            debit = self.money(mv["debit"])
            credit = self.money(mv["credit"])
            # Closing signed balance. Bank + customer books use Debit−Credit
            # (same as Ledger Export), even when group nature differs.
            if (
                led.get("source") == "bank"
                or led.get("customer_id")
                or nature in {"Asset", "Expense"}
            ):
                closing = opening + debit - credit
            else:
                closing = opening + credit - debit
            result.append(
                {
                    **led,
                    "opening": opening,
                    "debit": debit,
                    "credit": credit,
                    "closing": closing,
                    "closing_dr_cr": (
                        "Dr"
                        if (
                            (nature in {"Asset", "Expense"} and closing >= 0)
                            or (nature in {"Liability", "Income"} and closing < 0)
                        )
                        else "Cr"
                    ),
                    "display_closing": abs(closing),
                }
            )
        return result

    def rollup_groups(
        self,
        ledgers: list[dict[str, Any]],
        *,
        natures: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Attach ledgers to group tree and sum closing balances recursively."""
        groups = self.load_groups()
        if natures:
            allowed = {g["GroupID"] for g in groups if (g.get("GroupNature") or "") in natures}
            # keep ancestors of allowed
            by_id = {int(g["GroupID"]): g for g in groups}
            keep = set(allowed)
            for gid in list(allowed):
                cur = by_id.get(int(gid))
                while cur and cur.get("ParentGroupID"):
                    pid = int(cur["ParentGroupID"])
                    keep.add(pid)
                    cur = by_id.get(pid)
            groups = [g for g in groups if int(g["GroupID"]) in keep]

        tree = self.build_group_tree(groups)
        by_group: dict[int, list[dict]] = defaultdict(list)
        for led in ledgers:
            if natures and led.get("nature") not in natures:
                continue
            by_group[int(led["group_id"])].append(led)

        def walk(node: dict) -> Decimal:
            node["ledgers"] = by_group.get(int(node["GroupID"]), [])
            total = sum((self.money(l["closing"]) for l in node["ledgers"]), ZERO)
            for child in node["children"]:
                total += walk(child)
            node["closing"] = total
            node["display_closing"] = abs(total)
            node["has_children"] = bool(node["children"] or node["ledgers"])
            return total

        for root in tree:
            walk(root)
        # Drop empty branches
        def prune(nodes: list[dict]) -> list[dict]:
            out = []
            for n in nodes:
                n["children"] = prune(n["children"])
                if n["children"] or n["ledgers"] or self.money(n.get("closing")) != ZERO:
                    out.append(n)
            return out

        return prune(tree)

    def get_ledger_statement(
        self,
        ledger_key: str,
        *,
        date_from: date,
        date_to: date,
        limit: int = 2000,
    ) -> dict[str, Any]:
        """
        Drill-down statement matching Ledger Export preview:
        Opening Balance + vouchers + running balance + closing.
        """
        self.ensure_schema()
        lim = max(1, min(int(limit or 2000), 5000))

        if ledger_key.startswith("bank-"):
            bank_id = int(ledger_key.split("-", 1)[1])
            from app.services.ledger_export_service import LedgerExportService

            data = LedgerExportService().bank_ledger_preview_data(
                bank_id, date_from=date_from, date_to=date_to
            )
            opening = self._bank_opening_as_of(bank_id, date_from)
            closing = self.money(data.get("closing"))
            lines = []
            for line in (data.get("lines") or [])[:lim]:
                kind = line.get("kind") or "txn"
                ref = line.get("reference") or ""
                source = line.get("source") or ""
                # Parse BT-id for voucher detail click
                voucher_id = None
                source_table = "JtcsBankTransaction" if kind == "txn" else ""
                source_record_id = None
                if kind == "txn" and str(ref).startswith("BT-"):
                    try:
                        voucher_id = int(str(ref).split("/")[0].replace("BT-", "").strip())
                        source_record_id = voucher_id
                    except ValueError:
                        voucher_id = None
                lines.append(
                    {
                        "kind": kind,
                        "voucher_date": line.get("date") or "",
                        "voucher_type": line.get("ledger_kind") or kind,
                        "narration": line.get("description") or "",
                        "reference": ref,
                        "source": source,
                        "debit": self.money(line.get("debit")),
                        "credit": self.money(line.get("credit")),
                        "running_balance": (
                            None
                            if line.get("balance") is None
                            else self.money(line.get("balance"))
                        ),
                        "voucher_id": voucher_id,
                        "SourceTable": source_table,
                        "SourceRecordID": source_record_id,
                        "clickable": kind == "txn",
                    }
                )
            lines.append(
                {
                    "kind": "closing",
                    "voucher_date": date_to.strftime("%d/%m/%Y"),
                    "voucher_type": "",
                    "narration": "Closing Balance",
                    "reference": "CLOSING",
                    "source": "",
                    "debit": ZERO,
                    "credit": ZERO,
                    "running_balance": closing,
                    "voucher_id": None,
                    "SourceTable": "",
                    "SourceRecordID": None,
                    "clickable": False,
                }
            )
            return {
                "format": "ledger",
                "ledger_kind": "bank",
                "title": data.get("title") or "Bank Account Ledger",
                "entity_name": data.get("entity_name") or "",
                "meta": [
                    {"label": k, "value": v}
                    for k, v in (data.get("meta") or [])
                ],
                "opening": opening,
                "closing": closing,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "headers": list(data.get("headers") or [
                    "Date",
                    "Description",
                    "Reference",
                    "Source",
                    "Ledger Kind",
                    "Debit",
                    "Credit",
                    "Running Balance",
                ]),
                "lines": lines,
            }

        # CoA / customer / work — build opening + period lines (ledger style)
        rows = self.list_vouchers_for_ledger(
            ledger_key, date_from=date_from, date_to=date_to, limit=lim
        )
        opening = ZERO
        name = ledger_key
        if ledger_key.startswith("coa-"):
            aid = int(ledger_key.split("-", 1)[1])
            info = db.session.execute(
                text(
                    """
                    SELECT AccountName, OpeningBalance, OpeningBalanceDate, OpeningBalanceDrCr,
                           CustomerID, WorkID, g.GroupNature, g.UnderType
                    FROM dbo.ChartOfAccountMaster a
                    LEFT JOIN dbo.ChartOfGroupMaster g ON g.GroupID = a.GroupID
                    WHERE a.AccountID = :aid
                    """
                ),
                {"aid": aid},
            ).mappings().first()
            if info:
                name = (info.get("AccountName") or name).strip()
                nature = (info.get("GroupNature") or (
                    "Asset" if (info.get("UnderType") or "") == "Assets" else "Liability"
                ))
                opening = self._signed_opening(
                    info.get("OpeningBalance"), info.get("OpeningBalanceDrCr"), nature
                )
                if info.get("CustomerID"):
                    try:
                        from app.services.ledger_export_service import LedgerExportService

                        data = LedgerExportService().customer_ledger_preview_data(
                            int(info["CustomerID"]),
                            date_from=date_from,
                            date_to=date_to,
                        )
                        closing = self.money(data.get("closing"))
                        opening_bal = self.money(
                            next(
                                (
                                    ln.get("balance")
                                    for ln in (data.get("lines") or [])
                                    if ln.get("kind") == "opening"
                                ),
                                ZERO,
                            )
                        )
                        lines = []
                        for line in (data.get("lines") or [])[:lim]:
                            kind = line.get("kind") or "txn"
                            lines.append(
                                {
                                    "kind": kind,
                                    "voucher_date": line.get("date") or "",
                                    "voucher_type": line.get("work") or "",
                                    "narration": line.get("description") or "",
                                    "reference": line.get("bill") or "",
                                    "source": line.get("work") or "",
                                    "debit": self.money(line.get("debit")),
                                    "credit": self.money(line.get("credit")),
                                    "running_balance": (
                                        None
                                        if line.get("balance") is None
                                        else self.money(line.get("balance"))
                                    ),
                                    "voucher_id": None,
                                    "SourceTable": "",
                                    "SourceRecordID": None,
                                    "clickable": False,
                                    # Customer ledger columns differ from bank
                                    "bill": line.get("bill") or "",
                                    "work": line.get("work") or "",
                                }
                            )
                        lines.append(
                            {
                                "kind": "closing",
                                "voucher_date": date_to.strftime("%d/%m/%Y"),
                                "voucher_type": "",
                                "narration": "Closing Balance",
                                "reference": "CLOSING",
                                "source": "",
                                "debit": ZERO,
                                "credit": ZERO,
                                "running_balance": closing,
                                "voucher_id": None,
                                "SourceTable": "",
                                "SourceRecordID": None,
                                "clickable": False,
                                "bill": "",
                                "work": "",
                            }
                        )
                        return {
                            "format": "ledger",
                            "ledger_kind": "customer",
                            "title": data.get("title") or "Customer Ledger",
                            "entity_name": data.get("entity_name") or name,
                            "meta": [
                                {"label": k, "value": v}
                                for k, v in (data.get("meta") or [])
                            ],
                            "opening": opening_bal,
                            "closing": closing,
                            "date_from": date_from.isoformat(),
                            "date_to": date_to.isoformat(),
                            "headers": list(data.get("headers") or [
                                "Date",
                                "Bill / Ref No.",
                                "Work Type",
                                "Description",
                                "Debit (Bill)",
                                "Credit (Receipt)",
                                "Running Balance",
                            ]),
                            "lines": lines,
                        }
                    except Exception:
                        db.session.rollback()

        running = opening
        lines = [
            {
                "kind": "opening",
                "voucher_date": date_from.strftime("%d/%m/%Y"),
                "voucher_type": "",
                "narration": "Opening Balance",
                "reference": "OPENING",
                "source": "Chart of Account",
                "debit": ZERO,
                "credit": ZERO,
                "running_balance": running,
                "voucher_id": None,
                "SourceTable": "",
                "SourceRecordID": None,
                "clickable": False,
            }
        ]
        for r in rows:
            debit = self.money(r.get("debit"))
            credit = self.money(r.get("credit"))
            running = self.money(running + debit - credit)
            vdate = r.get("voucher_date")
            if hasattr(vdate, "strftime"):
                vdate = vdate.strftime("%d/%m/%Y")
            lines.append(
                {
                    "kind": "txn",
                    "voucher_date": vdate or "",
                    "voucher_type": r.get("voucher_type") or "",
                    "narration": r.get("narration") or "",
                    "reference": str(r.get("voucher_id") or ""),
                    "source": r.get("SourceTable") or "",
                    "debit": debit,
                    "credit": credit,
                    "running_balance": running,
                    "voucher_id": r.get("voucher_id"),
                    "SourceTable": r.get("SourceTable") or "",
                    "SourceRecordID": r.get("SourceRecordID") or r.get("voucher_id"),
                    "clickable": True,
                }
            )
        lines.append(
            {
                "kind": "closing",
                "voucher_date": date_to.strftime("%d/%m/%Y"),
                "voucher_type": "",
                "narration": "Closing Balance",
                "reference": "CLOSING",
                "source": "",
                "debit": ZERO,
                "credit": ZERO,
                "running_balance": running,
                "voucher_id": None,
                "SourceTable": "",
                "SourceRecordID": None,
                "clickable": False,
            }
        )
        return {
            "format": "ledger",
            "ledger_kind": "generic",
            "title": "Ledger Statement",
            "entity_name": name,
            "meta": [
                {"label": "Account", "value": name},
                {
                    "label": "Period",
                    "value": f"{date_from.strftime('%d/%m/%Y')} to {date_to.strftime('%d/%m/%Y')}",
                },
            ],
            "opening": opening,
            "closing": running,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
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
        }

    def list_vouchers_for_ledger(
        self,
        ledger_key: str,
        *,
        date_from: date,
        date_to: date,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Raw voucher rows (used when full ledger export is unavailable)."""
        self.ensure_schema()
        lim = max(1, min(int(limit or 500), 2000))
        if ledger_key.startswith("bank-"):
            bank_id = int(ledger_key.split("-", 1)[1])
            rows = db.session.execute(
                text(
                    """
                    SELECT TOP (:lim)
                        t.JtcsBankTransactionID AS voucher_id,
                        t.TransactionDate AS voucher_date,
                        ISNULL(t.LedgerKind, N'BANK') AS voucher_type,
                        ISNULL(t.Description, N'') AS narration,
                        ISNULL(t.Debit, 0) AS debit,
                        ISNULL(t.Credit, 0) AS credit,
                        t.SourceType,
                        t.SourceID,
                        t.SourceTable,
                        t.SourceRecordID
                    FROM dbo.JtcsBankTransaction t
                    WHERE t.JtcsBankAccountID = :bid
                      AND t.TransactionDate >= :d1 AND t.TransactionDate <= :d2
                    ORDER BY t.TransactionDate, t.JtcsBankTransactionID
                    """
                ),
                {"lim": lim, "bid": bank_id, "d1": date_from, "d2": date_to},
            ).mappings().all()
            return [dict(r) for r in rows]

        if ledger_key.startswith("coa-"):
            account_id = int(ledger_key.split("-", 1)[1])
            info = db.session.execute(
                text(
                    """
                    SELECT CustomerID, WorkID, AccountName
                    FROM dbo.ChartOfAccountMaster WHERE AccountID = :aid
                    """
                ),
                {"aid": account_id},
            ).mappings().first()
            if not info:
                return []
            rows: list[dict] = []
            if info.get("CustomerID"):
                rows.extend(
                    dict(r)
                    for r in db.session.execute(
                        text(
                            """
                            SELECT TOP (:lim)
                                t.TransactionID AS voucher_id,
                                t.TransactionDate AS voucher_date,
                                ISNULL(t.WorkType, N'Daily') AS voucher_type,
                                ISNULL(t.Description, t.ReferenceNo) AS narration,
                                ISNULL(t.ExpenseAmount, 0) + ISNULL(t.PurchaseAmount, 0) AS debit,
                                ISNULL(t.IncomeAmount, 0) + ISNULL(t.SaleAmount, 0) AS credit,
                                CAST(NULL AS NVARCHAR(50)) AS SourceType,
                                CAST(NULL AS INT) AS SourceID,
                                N'JTCSDailyTransaction' AS SourceTable,
                                t.TransactionID AS SourceRecordID
                            FROM dbo.JTCSDailyTransaction t
                            WHERE t.CustomerID = :cid
                              AND t.TransactionDate >= :d1 AND t.TransactionDate <= :d2
                              AND ISNULL(t.Status, N'') <> N'Void'
                            ORDER BY t.TransactionDate, t.TransactionID
                            """
                        ),
                        {
                            "lim": lim,
                            "cid": int(info["CustomerID"]),
                            "d1": date_from,
                            "d2": date_to,
                        },
                    ).mappings().all()
                )
            if info.get("WorkID"):
                rows.extend(
                    dict(r)
                    for r in db.session.execute(
                        text(
                            """
                            SELECT TOP (:lim)
                                m.EntryID AS voucher_id,
                                m.WorkDate AS voucher_date,
                                ISNULL(w.LedgerKind, N'Others') AS voucher_type,
                                ISNULL(m.Remarks, m.BillNo) AS narration,
                                CASE WHEN w.LedgerKind = N'Expense' THEN ISNULL(d.Amount, 0) ELSE 0 END AS debit,
                                CASE WHEN w.LedgerKind IN (N'Income', N'Misc.') THEN ISNULL(d.Amount, 0) ELSE 0 END AS credit,
                                CAST(NULL AS NVARCHAR(50)) AS SourceType,
                                CAST(NULL AS INT) AS SourceID,
                                N'OthersIncomeExpenseMaster' AS SourceTable,
                                m.EntryID AS SourceRecordID
                            FROM dbo.OthersIncomeExpenseDetail d
                            INNER JOIN dbo.OthersIncomeExpenseMaster m ON m.EntryID = d.EntryID
                            INNER JOIN dbo.WorkMaster w ON w.WorkID = d.WorkID
                            WHERE d.WorkID = :wid
                              AND m.WorkDate >= :d1 AND m.WorkDate <= :d2
                              AND ISNULL(m.IsActive, 1) = 1
                            ORDER BY m.WorkDate, m.EntryID
                            """
                        ),
                        {
                            "lim": lim,
                            "wid": int(info["WorkID"]),
                            "d1": date_from,
                            "d2": date_to,
                        },
                    ).mappings().all()
                )
            rows.sort(key=lambda x: (x.get("voucher_date") or date.min, x.get("voucher_id") or 0))
            return rows[:lim]
        return []

    def get_voucher_detail(self, source_table: str, source_id: int) -> dict[str, Any]:
        self.ensure_schema()
        table = (source_table or "").strip()
        if table == "JtcsBankTransaction" or table == "":
            row = db.session.execute(
                text(
                    """
                    SELECT * FROM dbo.JtcsBankTransaction
                    WHERE JtcsBankTransactionID = :id
                    """
                ),
                {"id": source_id},
            ).mappings().first()
            return {"source": "bank", "record": dict(row) if row else {}}
        if table == "JTCSDailyTransaction":
            row = db.session.execute(
                text("SELECT * FROM dbo.JTCSDailyTransaction WHERE TransactionID = :id"),
                {"id": source_id},
            ).mappings().first()
            return {"source": "daily", "record": dict(row) if row else {}}
        if table == "OthersIncomeExpenseMaster":
            row = db.session.execute(
                text("SELECT * FROM dbo.OthersIncomeExpenseMaster WHERE EntryID = :id"),
                {"id": source_id},
            ).mappings().first()
            details = db.session.execute(
                text(
                    """
                    SELECT * FROM dbo.OthersIncomeExpenseDetail WHERE EntryID = :id
                    """
                ),
                {"id": source_id},
            ).mappings().all()
            return {
                "source": "others",
                "record": dict(row) if row else {},
                "details": [dict(d) for d in details],
            }
        return {"source": table, "record": {}}
