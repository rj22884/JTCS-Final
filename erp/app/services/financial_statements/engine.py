"""Reusable Financial Report Engine — group tree + ledger balances + drill-down."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.extensions import db
from app.services.payment_accounting_service import (
    sql_customer_receipt_expr,
    sql_unpaid_followup_exclusion,
)
from app.utils.opening_balance import (
    BANK_MOVEMENT_SINCE_OPENING_SQL,
    apply_account_running,
    default_dr_cr_for_under_type,
    is_credit_normal_nature,
)

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
    "Appreciation": "Income (Indirect)",
    "Purchase Accounts": None,
    "Direct Expenses": None,
    "Expenses (Direct)": "Direct Expenses",
    "Depreciation": "Expenses (Direct)",
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
    "Appreciation": "Income",
    "Purchase Accounts": "Expense",
    "Direct Expenses": "Expense",
    "Expenses (Direct)": "Expense",
    "Depreciation": "Expense",
    "Salary and Wages": "Expense",
    "Electricity Expenses": "Expense",
    "Indirect Expenses": "Expense",
    "Expenses (Indirect)": "Expense",
}

TALLY_ASSET_ROOT_ORDER = (
    "Fixed Assets",
    "Investments",
    "Current Assets",
    "Misc. Expenses (ASSET)",
)
TALLY_LIABILITY_ROOT_ORDER = (
    "Capital Account",
    "Reserves & Surplus",
    "Loans (Liability)",
    "Current Liabilities",
)

# Higher rank wins when a ledger is linked to multiple groups.
PLACEMENT_RANK = {
    "investments": 100,
    "fixed assets": 95,
    "immovable property": 94,
    "computers printers & electric items": 94,
    "capital account": 90,
    "loans (liability)": 88,
    "secured loans": 87,
    "unsecured loans": 87,
    "bank od a/c": 87,
    "current liabilities": 80,
    "sundry creditors": 79,
    "deposits (asset)": 72,
    "loans & advances (asset)": 72,
    "stock holding corporation of india": 71,
    "bank accounts": 70,
    "cash-in-hand": 70,
    "sundry debtors": 60,
    "current assets": 20,
    "suspense a/c": 15,
    "individual client": 10,
}

RECEIVABLE_GROUP_NAMES = {"individual client", "sundry debtors"}


class FinancialReportEngine:
    """
    Server-side aggregation engine.

    Closing = Opening (± Dr/Cr) + period Debits − period Credits
    (signed by account nature for statement presentation).
    """

    _schema_ready = False
    FA_GROUP_NAMES = {
        "fixed assets",
        "computers printers & electric items",
        "immovable property",
    }
    INV_GROUP_NAMES = {
        "investments",
        "investment",
    }

    def __init__(self):
        self._groups_cache: dict[bool, list[dict[str, Any]]] = {}
        self._fa_group_ids: set[int] | None = None
        self._inv_group_ids: set[int] | None = None
        self._dep_expense_group: dict[str, Any] | None | bool = False
        self._app_income_group: dict[str, Any] | None | bool = False

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
        if FinancialReportEngine._schema_ready:
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
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.FixedAssetMaster', N'U') IS NOT NULL
                   AND COL_LENGTH(N'dbo.FixedAssetMaster', N'ItemID') IS NULL
                    ALTER TABLE dbo.FixedAssetMaster ADD ItemID INT NULL;
                """
            )
        )
        db.session.commit()
        self._backfill_group_hierarchy()
        FinancialReportEngine._schema_ready = True

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
        cached = self._groups_cache.get(active_only)
        if cached is not None:
            return cached
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
        rows = [dict(r) for r in db.session.execute(text(sql)).mappings().all()]
        self._groups_cache[active_only] = rows
        return rows

    def fixed_asset_group_ids(self) -> set[int]:
        if self._fa_group_ids is None:
            self._fa_group_ids = self.group_ids_under_names(self.FA_GROUP_NAMES)
        return self._fa_group_ids

    def investment_group_ids(self) -> set[int]:
        if self._inv_group_ids is None:
            self._inv_group_ids = self.group_ids_under_names(self.INV_GROUP_NAMES)
        return self._inv_group_ids

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
        for node in by_id.values():
            node["children"].sort(key=lambda n: (n.get("GroupName") or "").lower())
        roots.sort(key=lambda n: (n.get("GroupName") or "").lower())
        return roots

    def _nature_from_group(self, group: dict | None, by_id: dict[int, dict]) -> str:
        if not group:
            return "Asset"
        cur = group
        seen: set[int] = set()
        hops = 0
        while cur and hops < 40:
            gid = int(cur["GroupID"])
            if gid in seen:
                break
            seen.add(gid)
            name = (cur.get("GroupName") or "").strip()
            mapped = NATURE_BY_NAME.get(name)
            if mapped:
                return mapped
            n = (cur.get("GroupNature") or "").strip()
            if n in {"Asset", "Liability", "Income", "Expense"}:
                return n
            pid = cur.get("ParentGroupID")
            cur = by_id.get(int(pid)) if pid else None
            hops += 1
        under = ((group or {}).get("UnderType") or "").strip()
        return "Asset" if under == "Assets" else "Liability"

    def _ancestor_names(self, group: dict | None, by_id: dict[int, dict]) -> list[str]:
        names: list[str] = []
        cur = group
        seen: set[int] = set()
        hops = 0
        while cur and hops < 40:
            gid = int(cur["GroupID"])
            if gid in seen:
                break
            seen.add(gid)
            names.append((cur.get("GroupName") or "").strip().casefold())
            pid = cur.get("ParentGroupID")
            cur = by_id.get(int(pid)) if pid else None
            hops += 1
        return names

    def group_ids_under_names(self, names: set[str]) -> set[int]:
        """Chart of Account Group IDs whose self or ancestor name is in `names`."""
        wanted = {n.strip().casefold() for n in names if n}
        groups = self.load_groups(active_only=False)
        by_id = {int(g["GroupID"]): g for g in groups}
        out: set[int] = set()
        for g in groups:
            if any(n in wanted for n in self._ancestor_names(g, by_id)):
                out.add(int(g["GroupID"]))
        return out

    def is_trading_group(self, group_id: int | None, by_id: dict[int, dict] | None = None) -> bool:
        """Direct trading Income/Expense groups from Chart of Account Group Master."""
        if not group_id:
            return False
        by_id = by_id if by_id is not None else {
            int(g["GroupID"]): g for g in self.load_groups(active_only=False)
        }
        group = by_id.get(int(group_id))
        if not group:
            return False
        nature = self._nature_from_group(group, by_id)
        if nature not in {"Income", "Expense"}:
            return False
        names = self._ancestor_names(group, by_id)
        if any("indirect" in n for n in names):
            return False
        return any(
            "direct" in n
            or n.startswith("sales")
            or n.startswith("purchase")
            or n in {"commission income", "salary and wages"}
            for n in names
        )

    def _group_rank(self, group: dict, by_id: dict[int, dict]) -> int:
        best = 0
        cur = group
        seen: set[int] = set()
        hops = 0
        while cur and hops < 40:
            gid = int(cur["GroupID"])
            if gid in seen:
                break
            seen.add(gid)
            name = (cur.get("GroupName") or "").strip().casefold()
            best = max(best, int(PLACEMENT_RANK.get(name, 40)))
            pid = cur.get("ParentGroupID")
            cur = by_id.get(int(pid)) if pid else None
            hops += 1
        return best

    def _pick_placement_group(
        self, candidate_ids: list[int], by_id: dict[int, dict]
    ) -> int | None:
        best_id = None
        best_rank = -1
        for gid in candidate_ids:
            if gid is None:
                continue
            group = by_id.get(int(gid))
            if not group:
                continue
            rank = self._group_rank(group, by_id)
            if rank > best_rank:
                best_rank = rank
                best_id = int(gid)
        return best_id

    def _group_is_receivable(self, group_id: int | None, by_id: dict[int, dict]) -> bool:
        cur = by_id.get(int(group_id)) if group_id else None
        seen: set[int] = set()
        hops = 0
        under_investments = False
        is_receivable = False
        while cur and hops < 40:
            gid = int(cur["GroupID"])
            if gid in seen:
                break
            seen.add(gid)
            name = (cur.get("GroupName") or "").strip().casefold()
            if name == "investments":
                under_investments = True
            if name in RECEIVABLE_GROUP_NAMES:
                is_receivable = True
            pid = cur.get("ParentGroupID")
            cur = by_id.get(int(pid)) if pid else None
            hops += 1
        if under_investments:
            return False
        return is_receivable

    def sort_tally_roots(self, nodes: list[dict], *, side: str) -> list[dict]:
        order = TALLY_ASSET_ROOT_ORDER if side == "asset" else TALLY_LIABILITY_ROOT_ORDER
        rank = {name.casefold(): i for i, name in enumerate(order)}

        def key(node: dict) -> tuple:
            name = (node.get("GroupName") or "").strip()
            return (rank.get(name.casefold(), 80), name.casefold())

        return sorted(nodes, key=key)

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
        try:
            from app.repositories.customer_repository import CustomerRepository

            CustomerRepository().ensure_schema()
        except Exception:
            db.session.rollback()
        try:
            from app.repositories.others_repository import WorkMasterRepository

            WorkMasterRepository().ensure_schema()
        except Exception:
            db.session.rollback()
        try:
            from app.repositories.bank_master_repository import BankMasterRepository

            BankMasterRepository().ensure_schema()
        except Exception:
            db.session.rollback()
        ledgers: list[dict[str, Any]] = []
        groups = self.load_groups(active_only=False)
        groups_by_id = {int(g["GroupID"]): g for g in groups}

        links_by_account: dict[int, list[int]] = defaultdict(list)
        try:
            link_rows = db.session.execute(
                text(
                    """
                    SELECT AccountID, GroupID, DisplayOrder
                    FROM dbo.ChartOfAccountGroupLink
                    ORDER BY DisplayOrder, GroupID
                    """
                )
            ).mappings().all()
            for lr in link_rows:
                links_by_account[int(lr["AccountID"])].append(int(lr["GroupID"]))
        except Exception:
            db.session.rollback()

        try:
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
                        COALESCE(c.PurchaseDate, w.PurchaseDate) AS PurchaseDate,
                        COALESCE(c.DepreciationRate, w.DepreciationRate) AS DepreciationRate,
                        COALESCE(c.AppreciationRate, w.AppreciationRate) AS AppreciationRate,
                        c.OpeningBalanceDate AS CustomerOpeningDate,
                        w.OpeningBalanceDate AS WorkOpeningDate,
                        g.GroupName,
                        g.UnderType,
                        ISNULL(NULLIF(g.GroupNature, N''),
                               CASE WHEN g.UnderType = N'Assets' THEN N'Asset' ELSE N'Liability' END
                        ) AS GroupNature,
                        c.CustomerGroup
                    FROM dbo.ChartOfAccountMaster a
                    INNER JOIN dbo.ChartOfGroupMaster g ON g.GroupID = a.GroupID
                    LEFT JOIN dbo.CustomerMaster c ON c.CustomerID = a.CustomerID
                    LEFT JOIN dbo.WorkMaster w ON w.WorkID = a.WorkID
                    WHERE a.IsActive = 1
                    """
                )
            ).mappings().all()
        except Exception:
            db.session.rollback()
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
                        ) AS GroupNature,
                        c.CustomerGroup
                    FROM dbo.ChartOfAccountMaster a
                    INNER JOIN dbo.ChartOfGroupMaster g ON g.GroupID = a.GroupID
                    LEFT JOIN dbo.CustomerMaster c ON c.CustomerID = a.CustomerID
                    WHERE a.IsActive = 1
                    """
                )
            ).mappings().all()
        for r in coa:
            primary_gid = int(r["GroupID"])
            aid = int(r["AccountID"])
            candidates = links_by_account.get(aid) or [primary_gid]
            if primary_gid not in candidates:
                candidates = [primary_gid] + candidates
            placed_gid = self._pick_placement_group(candidates, groups_by_id) or primary_gid
            placed = groups_by_id.get(placed_gid) or groups_by_id.get(primary_gid)
            nature = self._nature_from_group(placed, groups_by_id)
            ledgers.append(
                {
                    "ledger_key": f"coa-{aid}",
                    "source": "coa",
                    "account_id": aid,
                    "bank_account_id": None,
                    "customer_id": int(r["CustomerID"]) if r.get("CustomerID") else None,
                    "work_id": int(r["WorkID"]) if r.get("WorkID") else None,
                    "ledger_name": (r.get("AccountName") or "").strip(),
                    "group_id": placed_gid,
                    "group_name": (placed or {}).get("GroupName") or (r.get("GroupName") or ""),
                    "nature": nature,
                    "customer_group": (r.get("CustomerGroup") or "").strip(),
                    "opening_raw": r.get("OpeningBalance"),
                    "opening_date": r.get("OpeningBalanceDate") or r.get("CustomerOpeningDate"),
                    "opening_dr_cr": r.get("OpeningBalanceDrCr"),
                    "purchase_date": r.get("PurchaseDate")
                    or r.get("CustomerOpeningDate")
                    or r.get("WorkOpeningDate")
                    or r.get("OpeningBalanceDate"),
                    "depreciation_rate": r.get("DepreciationRate"),
                    "appreciation_rate": r.get("AppreciationRate"),
                }
            )

        try:
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
                        b.PurchaseDate,
                        b.DepreciationRate,
                        b.AppreciationRate,
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
        except Exception:
            db.session.rollback()
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
                    "purchase_date": r.get("PurchaseDate") or r.get("OpeningBalanceDate"),
                    "depreciation_rate": r.get("DepreciationRate"),
                    "appreciation_rate": r.get("AppreciationRate"),
                }
            )
        self._append_fixed_asset_item_ledgers(ledgers, groups_by_id)
        return ledgers

    def _append_fixed_asset_item_ledgers(
        self, ledgers: list[dict[str, Any]], groups_by_id: dict[int, dict]
    ) -> None:
        """Item Master rows under Fixed Assets or Investments appear on the Balance Sheet."""
        try:
            from app.repositories.item_master_repository import ItemMasterRepository

            ItemMasterRepository().ensure_schema()
        except Exception:
            db.session.rollback()
        fa_ids = self.fixed_asset_group_ids()
        inv_ids = self.investment_group_ids()
        wanted = fa_ids | inv_ids
        if not wanted:
            return
        try:
            items = db.session.execute(
                text(
                    """
                    SELECT
                        i.ItemID, i.ItemCode, i.ItemName,
                        i.OpeningBalance, i.OpeningBalanceDate,
                        i.PurchaseDate, i.DepreciationRate,
                        i.AppreciationRate, i.ChartGroupID,
                        g.GroupName, g.UnderType,
                        ISNULL(NULLIF(g.GroupNature, N''), N'Asset') AS GroupNature
                    FROM dbo.ItemMaster i
                    INNER JOIN dbo.ChartOfGroupMaster g ON g.GroupID = i.ChartGroupID
                    WHERE ISNULL(i.IsActive, 1) = 1
                      AND i.ChartGroupID IS NOT NULL
                    """
                )
            ).mappings().all()
        except Exception:
            db.session.rollback()
            return
        for r in items:
            gid = int(r["ChartGroupID"])
            if gid not in wanted:
                continue
            placed = groups_by_id.get(gid)
            nature = self._nature_from_group(placed, groups_by_id) if placed else "Asset"
            code = (r.get("ItemCode") or "").strip()
            name = (r.get("ItemName") or "").strip() or code or f"Item #{r['ItemID']}"
            ledgers.append(
                {
                    "ledger_key": f"item-{int(r['ItemID'])}",
                    "source": "item",
                    "account_id": None,
                    "bank_account_id": None,
                    "customer_id": None,
                    "work_id": None,
                    "item_id": int(r["ItemID"]),
                    "ledger_name": f"{name} ({code})" if code and code.lower() not in name.lower() else name,
                    "group_id": gid,
                    "group_name": (placed or {}).get("GroupName") or (r.get("GroupName") or ""),
                    "nature": nature or "Asset",
                    "opening_raw": r.get("OpeningBalance"),
                    "opening_date": r.get("OpeningBalanceDate"),
                    "opening_dr_cr": "Dr",
                    "purchase_date": r.get("PurchaseDate") or r.get("OpeningBalanceDate"),
                    "depreciation_rate": r.get("DepreciationRate"),
                    "appreciation_rate": r.get("AppreciationRate"),
                }
            )

    def _bank_opening_as_of(self, bank_account_id: int, date_from: date) -> Decimal:
        """Master OB + prior movements on/after OpeningBalanceDate (same as Ledger Export)."""
        row = db.session.execute(
            text(
                """
                SELECT
                    b.OpeningBalance,
                    b.OpeningBalanceDate,
                    g.UnderType,
                    ISNULL(
                        NULLIF(g.GroupNature, N''),
                        CASE
                            WHEN g.UnderType = N'Liabilities' THEN N'Liability'
                            WHEN g.UnderType = N'Assets' THEN N'Asset'
                            ELSE N'Asset'
                        END
                    ) AS GroupNature
                FROM dbo.JtcsBankAccountMaster b
                LEFT JOIN dbo.ChartOfGroupMaster g ON g.GroupID = b.ChartGroupID
                WHERE b.JtcsBankAccountID = :bid
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
        credit_normal = is_credit_normal_nature(row.get("GroupNature"), row.get("UnderType"))
        prior_sql = """
                SELECT
                    ISNULL(SUM(ISNULL(Debit, 0)), 0) AS prior_debit,
                    ISNULL(SUM(ISNULL(Credit, 0)), 0) AS prior_credit
                FROM dbo.JtcsBankTransaction
                WHERE JtcsBankAccountID = :bid
                  AND TransactionDate < :d1
            """
        prior_params = {"bid": bank_account_id, "d1": date_from}
        if ob_date is not None:
            prior_sql += " AND TransactionDate >= :ob_date"
            prior_params["ob_date"] = ob_date
        prior = db.session.execute(text(prior_sql), prior_params).mappings().first()
        return apply_account_running(
            opening,
            self.money(prior["prior_debit"] if prior else 0),
            self.money(prior["prior_credit"] if prior else 0),
            credit_normal=credit_normal,
        )

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
                    ISNULL(SUM(x.billed), 0) AS billed,
                    ISNULL(SUM(x.received), 0) AS received
                FROM (
                    SELECT
                        ISNULL(d.SaleAmount, 0) + ISNULL(d.IncomeAmount, 0) AS billed,
                        {sql_customer_receipt_expr("d", "b")} AS received
                    FROM dbo.JTCSDailyTransaction d
                    LEFT JOIN dbo.JtcsBankTransaction b
                        ON b.JtcsBankTransactionID = d.BankTransactionID
                    WHERE d.CustomerID = :customer_id
                      AND d.Status = N'Posted'
                      {prior_date_sql}
                ) x
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
                          {sql_unpaid_followup_exclusion()}
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

        # Bank transactions → bank ledgers (same date floor as Ledger Export)
        bank_rows = db.session.execute(
            text(
                f"""
                SELECT t.JtcsBankAccountID,
                       SUM(ISNULL(t.Debit, 0)) AS DebitAmt,
                       SUM(ISNULL(t.Credit, 0)) AS CreditAmt
                FROM dbo.JtcsBankTransaction t
                INNER JOIN dbo.JtcsBankAccountMaster a
                    ON a.JtcsBankAccountID = t.JtcsBankAccountID
                WHERE t.TransactionDate >= :d1 AND t.TransactionDate <= :d2
                  AND t.JtcsBankAccountID > 0
                  AND {BANK_MOVEMENT_SINCE_OPENING_SQL}
                GROUP BY t.JtcsBankAccountID
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
                f"""
                SELECT
                    d.CustomerID,
                    ISNULL(d.SaleAmount, 0) + ISNULL(d.IncomeAmount, 0) AS Billed,
                    {sql_customer_receipt_expr("d", "b")} AS ReceiptAmount
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
            receipt = self.money(r["ReceiptAmount"])
            moves[key]["debit"] += billed
            moves[key]["credit"] += receipt

        # Unpaid Followup Tally bills → customer CoA debit (receivable)
        try:
            fu_rows = db.session.execute(
                text(
                    f"""
                    SELECT f.CustomerID, ISNULL(f.BillAmount, 0) AS BillAmount
                    FROM dbo.FollowupEntryMaster f
                    WHERE f.CustomerID IS NOT NULL
                      AND ISNULL(f.IsActive, 1) = 1
                      AND f.BillNo IS NOT NULL
                      AND LTRIM(RTRIM(f.BillNo)) <> N''
                      AND ISNULL(f.BillAmount, 0) > 0
                      AND ISNULL(f.BillDate, f.WorkDate) >= :d1
                      AND ISNULL(f.BillDate, f.WorkDate) <= :d2
                      {sql_unpaid_followup_exclusion()}
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

        self._merge_obc_coa_movements(moves, date_from, date_to)
        self._merge_item_invoice_movements(moves, date_from, date_to)
        return moves

    def _merge_item_invoice_movements(
        self,
        moves: dict[str, dict[str, Decimal]],
        date_from: date,
        date_to: date,
    ) -> None:
        """GST invoice lines credit the item ledger (same as Item Ledger Report)."""
        try:
            rows = db.session.execute(
                text(
                    """
                    SELECT l.ItemID, SUM(ISNULL(l.TaxableValue, 0)) AS CreditAmt
                    FROM dbo.GstInvoiceLine l
                    INNER JOIN dbo.GstInvoice inv ON inv.InvoiceID = l.InvoiceID
                    WHERE l.ItemID IS NOT NULL
                      AND inv.InvoiceDate >= :d1
                      AND inv.InvoiceDate <= :d2
                    GROUP BY l.ItemID
                    """
                ),
                {"d1": date_from, "d2": date_to},
            ).mappings().all()
        except Exception:
            db.session.rollback()
            return
        for r in rows:
            if not r.get("ItemID"):
                continue
            moves[f"item-{int(r['ItemID'])}"]["credit"] += self.money(r["CreditAmt"])

    def _obc_ledger_keys_ready(self) -> bool:
        try:
            if not db.session.execute(
                text("SELECT OBJECT_ID(N'dbo.OthersBankCashTransaction', N'U')")
            ).scalar():
                return False
            return bool(
                db.session.execute(
                    text(
                        "SELECT CASE WHEN COL_LENGTH(N'dbo.OthersBankCashTransaction', "
                        "N'CreditLedgerKey') IS NULL THEN 0 ELSE 1 END"
                    )
                ).scalar()
            )
        except Exception:
            db.session.rollback()
            return False

    def _merge_obc_coa_movements(
        self,
        moves: dict[str, dict[str, Decimal]],
        date_from: date,
        date_to: date,
    ) -> None:
        """Post Other Bank/Cash CoA legs onto chart ledgers (same as Customer Ledger).

        Bank-* legs are already in JtcsBankTransaction — do not double-count them.
        """
        if not self._obc_ledger_keys_ready():
            return
        try:
            rows = db.session.execute(
                text(
                    """
                    SELECT DebitLedgerKey, CreditLedgerKey, Amount
                    FROM dbo.OthersBankCashTransaction
                    WHERE ISNULL(IsActive, 1) = 1
                      AND WorkDate >= :d1
                      AND WorkDate <= :d2
                    """
                ),
                {"d1": date_from, "d2": date_to},
            ).mappings().all()
        except Exception:
            db.session.rollback()
            return
        for r in rows:
            amt = self.money(r.get("Amount"))
            if amt == ZERO:
                continue
            debit_key = (r.get("DebitLedgerKey") or "").strip()
            credit_key = (r.get("CreditLedgerKey") or "").strip()
            if debit_key.startswith("coa-"):
                moves[debit_key]["debit"] += amt
            if credit_key.startswith("coa-"):
                moves[credit_key]["credit"] += amt

    def _obc_coa_net(
        self,
        account_id: int,
        *,
        before: date,
        after: date | None,
    ) -> Decimal:
        """Net Other Bank/Cash posted to a CoA ledger before `before` (optional after OB date)."""
        if not account_id or not self._obc_ledger_keys_ready():
            return ZERO
        key = f"coa-{int(account_id)}"
        sql = """
                SELECT
                    ISNULL(SUM(CASE WHEN e.DebitLedgerKey = :k THEN e.Amount ELSE 0 END), 0) AS DrAmt,
                    ISNULL(SUM(CASE WHEN e.CreditLedgerKey = :k THEN e.Amount ELSE 0 END), 0) AS CrAmt
                FROM dbo.OthersBankCashTransaction e
                WHERE ISNULL(e.IsActive, 1) = 1
                  AND (e.DebitLedgerKey = :k OR e.CreditLedgerKey = :k)
                  AND e.WorkDate < :before
            """
        params: dict[str, Any] = {"k": key, "before": before}
        if after is not None:
            sql += " AND e.WorkDate > :after"
            params["after"] = after
        try:
            row = db.session.execute(text(sql), params).mappings().first()
        except Exception:
            db.session.rollback()
            return ZERO
        return self.money(row["DrAmt"] if row else 0) - self.money(row["CrAmt"] if row else 0)

    def _customer_ob_date(self, customer_id: int) -> date | None:
        if not self._customer_has_opening_cols():
            return None
        row = db.session.execute(
            text(
                """
                SELECT OpeningBalanceDate
                FROM dbo.CustomerMaster
                WHERE CustomerID = :cid
                """
            ),
            {"cid": customer_id},
        ).mappings().first()
        ob_date = row.get("OpeningBalanceDate") if row else None
        if isinstance(ob_date, datetime):
            return ob_date.date()
        return ob_date if isinstance(ob_date, date) else None

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
        groups_by_id = {int(g["GroupID"]): g for g in self.load_groups(active_only=False)}
        item_ids = [
            int(led["item_id"])
            for led in ledgers
            if led.get("source") == "item" and led.get("item_id")
        ]
        item_prior = self._item_prior_credits(item_ids, date_from) if item_ids else {}
        needle = (search or "").strip().lower()
        result = []
        for led in ledgers:
            if needle and needle not in (led["ledger_name"] or "").lower():
                continue
            nature = led["nature"]
            if led.get("source") == "item" and led.get("item_id"):
                opening = self.money(led.get("opening_raw"))
                opening = self.money(
                    opening - item_prior.get(int(led["item_id"]), ZERO)
                )
            elif led.get("source") == "bank" and led.get("bank_account_id"):
                # Align Balance Sheet bank totals with Ledger Export
                # (master OB + prior Dr−Cr, then period Dr−Cr).
                opening = self._bank_opening_as_of(int(led["bank_account_id"]), date_from)
            elif led.get("customer_id") and self._group_is_receivable(
                led.get("group_id"), groups_by_id
            ):
                # Sundry debtors / Individual Client — Customer Ledger closing.
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
                if (
                    led.get("customer_id")
                    and abs(opening) < Decimal("0.01")
                ):
                    cust_open = self._customer_opening_as_of(
                        int(led["customer_id"]), date_from
                    )
                    if abs(cust_open) >= Decimal("0.01"):
                        opening = cust_open
            if led.get("source") == "coa" and led.get("account_id"):
                ob_cut = None
                if led.get("customer_id"):
                    ob_cut = self._customer_ob_date(int(led["customer_id"]))
                else:
                    ob_cut = led.get("opening_date")
                    if isinstance(ob_cut, datetime):
                        ob_cut = ob_cut.date()
                opening = self.money(
                    opening
                    + self._obc_coa_net(
                        int(led["account_id"]),
                        before=date_from,
                        after=ob_cut,
                    )
                )
            mv = moves.get(led["ledger_key"], {"debit": ZERO, "credit": ZERO})
            debit = self.money(mv["debit"])
            credit = self.money(mv["credit"])
            # Bank books follow Ledger Export / dashboard: Asset = +Dr−Cr,
            # Bank OD / liability = +Cr−Dr. Customer books stay +Dr−Cr.
            if led.get("source") == "bank":
                closing = apply_account_running(
                    opening,
                    debit,
                    credit,
                    credit_normal=is_credit_normal_nature(nature),
                )
            elif led.get("customer_id") or nature in {"Asset", "Expense"}:
                closing = opening + debit - credit
            else:
                closing = opening + credit - debit
            pref_kind, pref_id = self.preview_ref_for_ledger(led)
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
                    "display_closing": (
                        closing if led.get("source") == "bank" else abs(closing)
                    ),
                    "preview_kind": pref_kind,
                    "preview_id": pref_id,
                }
            )
        self._apply_item_depreciation(result, date_from, date_to)
        self._apply_item_appreciation(result, date_from, date_to)
        return result

    def _item_prior_credits(self, item_ids: list[int], date_from: date) -> dict[int, Decimal]:
        """One query: invoice credits before date_from, keyed by ItemID."""
        ids = sorted({int(i) for i in item_ids if i})
        if not ids:
            return {}
        id_sql = ",".join(str(i) for i in ids)
        try:
            rows = db.session.execute(
                text(
                    f"""
                    SELECT l.ItemID, SUM(ISNULL(l.TaxableValue, 0)) AS CreditAmt
                    FROM dbo.GstInvoiceLine l
                    INNER JOIN dbo.GstInvoice inv ON inv.InvoiceID = l.InvoiceID
                    WHERE l.ItemID IN ({id_sql})
                      AND inv.InvoiceDate < :d1
                    GROUP BY l.ItemID
                    """
                ),
                {"d1": date_from},
            ).mappings().all()
        except Exception:
            db.session.rollback()
            return {}
        return {int(r["ItemID"]): self.money(r["CreditAmt"]) for r in rows if r.get("ItemID")}

    def _indirect_expense_group(self) -> dict[str, Any] | None:
        groups = self.load_groups(active_only=False)
        exact = None
        fuzzy = None
        for g in groups:
            name = (g.get("GroupName") or "").strip().casefold()
            if name == "indirect expenses":
                exact = g
                break
            if fuzzy is None and "indirect expens" in name:
                fuzzy = g
        return exact or fuzzy

    def _depreciation_expense_group(self) -> dict[str, Any] | None:
        if self._dep_expense_group is not False:
            return self._dep_expense_group  # type: ignore[return-value]
        groups = self.load_groups(active_only=False)
        by_name: dict[str, dict[str, Any]] = {}
        for g in groups:
            name = (g.get("GroupName") or "").strip().casefold()
            if name and name not in by_name:
                by_name[name] = g
        found = (
            by_name.get("depreciation")
            or by_name.get("expenses (direct)")
            or by_name.get("direct expenses")
            or self._indirect_expense_group()
        )
        if found is None:
            for g in groups:
                nature = (g.get("GroupNature") or "").strip()
                name = (g.get("GroupName") or "").strip().casefold()
                if nature == "Expense" or "expens" in name:
                    found = g
                    break
        self._dep_expense_group = found
        return found

    @staticmethod
    def _is_asset_class_ledger(led: dict[str, Any], group_ids: set[int]) -> bool:
        """Item Master or Customer Master row posted under FA / Investments."""
        if not group_ids:
            return False
        try:
            gid = int(led.get("group_id") or 0)
        except (TypeError, ValueError):
            return False
        if gid not in group_ids:
            return False
        if led.get("source") == "item" and led.get("item_id"):
            return True
        if led.get("source") == "bank" and led.get("bank_account_id"):
            return True
        if led.get("customer_id"):
            return True
        return bool(led.get("work_id"))

    def _apply_item_depreciation(
        self, ledgers: list[dict[str, Any]], date_from: date, date_to: date
    ) -> None:
        """Charge current-year WDV depreciation to P&L and reduce FA closing (WDV)."""
        from app.services.depreciation_service import DepreciationService

        fa_ids = self.fixed_asset_group_ids()
        if not fa_ids:
            return
        svc = DepreciationService()
        total_cy = ZERO
        as_of = svc.resolve_as_of(date_to)
        for led in ledgers:
            if not self._is_asset_class_ledger(led, fa_ids):
                continue
            book = self.money(led.get("closing"))
            rate = self.money(led.get("depreciation_rate"))
            if book <= ZERO or rate <= ZERO:
                continue
            calc = svc.calculate(
                cost=book,
                rate=rate,
                purchase_date=led.get("purchase_date"),
                opening_date=led.get("opening_date"),
                as_of=as_of,
                method="WDV",
            )
            cy = self.money(calc["current_year"])
            if cy <= ZERO:
                continue
            if cy > book:
                cy = book
            led["credit"] = self.money(led.get("credit")) + cy
            led["closing"] = self.money(book - cy)
            led["display_closing"] = abs(led["closing"])
            led["depreciation"] = cy
            total_cy += cy
        if total_cy < Decimal("0.01"):
            return
        target = self._find_depreciation_ledger(ledgers)
        if target is not None:
            target["nature"] = "Expense"
            target["debit"] = self.money(target.get("debit")) + total_cy
            target["closing"] = self.money(target.get("closing")) + total_cy
            target["display_closing"] = abs(self.money(target["closing"]))
            target["closing_dr_cr"] = "Dr"
            target["depreciation"] = self.money(target.get("depreciation")) + total_cy
            return
        exp_group = self._depreciation_expense_group()
        if not exp_group:
            return
        ledgers.append(
            {
                "ledger_key": "dep-expense",
                "source": "depreciation",
                "account_id": None,
                "bank_account_id": None,
                "customer_id": None,
                "work_id": None,
                "item_id": None,
                "ledger_name": "Depreciation",
                "group_id": int(exp_group["GroupID"]),
                "group_name": exp_group.get("GroupName") or "Expenses (Direct)",
                "nature": "Expense",
                "opening_raw": ZERO,
                "opening_date": None,
                "opening_dr_cr": "Dr",
                "opening": ZERO,
                "debit": total_cy,
                "credit": ZERO,
                "closing": total_cy,
                "closing_dr_cr": "Dr",
                "display_closing": total_cy,
                "preview_kind": "",
                "preview_id": None,
                "depreciation": total_cy,
            }
        )

    @staticmethod
    def _find_depreciation_ledger(ledgers: list[dict[str, Any]]) -> dict[str, Any] | None:
        exact = None
        in_dep_group = None
        fuzzy = None
        for led in ledgers:
            if led.get("source") in {"depreciation", "item"}:
                continue
            name = (led.get("ledger_name") or "").strip().casefold()
            gname = (led.get("group_name") or "").strip().casefold()
            if "accumulated" in name:
                continue
            if led.get("nature") == "Asset":
                continue
            if name == "depreciation":
                exact = led
                break
            if in_dep_group is None and gname == "depreciation":
                in_dep_group = led
            if (
                fuzzy is None
                and "depreciat" in name
                and led.get("nature") == "Expense"
            ):
                fuzzy = led
        return exact or in_dep_group or fuzzy

    def _indirect_income_group(self) -> dict[str, Any] | None:
        groups = self.load_groups(active_only=False)
        exact = None
        fuzzy = None
        for g in groups:
            name = (g.get("GroupName") or "").strip().casefold()
            if name in {"indirect incomes", "indirect income"}:
                exact = g
                break
            if fuzzy is None and "indirect income" in name:
                fuzzy = g
        return exact or fuzzy

    def _appreciation_income_group(self) -> dict[str, Any] | None:
        if self._app_income_group is not False:
            return self._app_income_group  # type: ignore[return-value]
        groups = self.load_groups(active_only=False)
        by_name: dict[str, dict[str, Any]] = {}
        for g in groups:
            name = (g.get("GroupName") or "").strip().casefold()
            if name and name not in by_name:
                by_name[name] = g
        found = (
            by_name.get("appreciation")
            or by_name.get("income (indirect)")
            or self._indirect_income_group()
            or by_name.get("other income")
        )
        self._app_income_group = found
        return found

    def _apply_item_appreciation(
        self, ledgers: list[dict[str, Any]], date_from: date, date_to: date
    ) -> None:
        """Credit current-year appreciation to P&L and increase investment closing."""
        from app.services.depreciation_service import DepreciationService

        inv_ids = self.investment_group_ids()
        if not inv_ids:
            return
        svc = DepreciationService()
        total_cy = ZERO
        as_of = svc.resolve_as_of(date_to)
        for led in ledgers:
            if not self._is_asset_class_ledger(led, inv_ids):
                continue
            book = self.money(led.get("closing"))
            rate = self.money(led.get("appreciation_rate"))
            purchase = led.get("purchase_date")
            opening = led.get("opening_date")
            if book <= ZERO or rate <= ZERO or (purchase is None and opening is None):
                continue
            calc = svc.calculate_appreciation(
                cost=book,
                rate=rate,
                purchase_date=purchase,
                opening_date=opening,
                as_of=as_of,
            )
            cy = self.money(calc["current_year"])
            if cy <= ZERO:
                continue
            led["debit"] = self.money(led.get("debit")) + cy
            led["closing"] = self.money(book + cy)
            led["display_closing"] = abs(led["closing"])
            led["appreciation"] = cy
            total_cy += cy
        if total_cy < Decimal("0.01"):
            return
        target = self._find_appreciation_ledger(ledgers)
        if target is not None:
            target["nature"] = "Income"
            target["credit"] = self.money(target.get("credit")) + total_cy
            target["closing"] = self.money(target.get("closing")) + total_cy
            target["display_closing"] = abs(self.money(target["closing"]))
            target["closing_dr_cr"] = "Cr"
            target["appreciation"] = self.money(target.get("appreciation")) + total_cy
            return
        inc_group = self._appreciation_income_group()
        if not inc_group:
            return
        ledgers.append(
            {
                "ledger_key": "app-income",
                "source": "appreciation",
                "account_id": None,
                "bank_account_id": None,
                "customer_id": None,
                "work_id": None,
                "item_id": None,
                "ledger_name": "Appreciation",
                "group_id": int(inc_group["GroupID"]),
                "group_name": inc_group.get("GroupName") or "Indirect Incomes",
                "nature": "Income",
                "opening_raw": ZERO,
                "opening_date": None,
                "opening_dr_cr": "Cr",
                "opening": ZERO,
                "debit": ZERO,
                "credit": total_cy,
                "closing": total_cy,
                "closing_dr_cr": "Cr",
                "display_closing": total_cy,
                "preview_kind": "",
                "preview_id": None,
                "appreciation": total_cy,
            }
        )

    @staticmethod
    def _find_appreciation_ledger(ledgers: list[dict[str, Any]]) -> dict[str, Any] | None:
        exact = None
        in_group = None
        for led in ledgers:
            if led.get("source") in {"appreciation", "item", "depreciation"}:
                continue
            name = (led.get("ledger_name") or "").strip().casefold()
            gname = (led.get("group_name") or "").strip().casefold()
            if led.get("nature") == "Asset":
                continue
            if name in {"appreciation", "appreciation income"}:
                exact = led
                break
            if in_group is None and gname == "appreciation":
                in_group = led
        return exact or in_group

    @staticmethod
    def preview_ref_for_ledger(led: dict[str, Any]) -> tuple[str, int | None]:
        """Map a FS ledger row to Ledger Report preview kind/id (dashboard path)."""
        key = str(led.get("ledger_key") or "")
        if led.get("bank_account_id"):
            return "bank", int(led["bank_account_id"])
        if key.startswith("bank-"):
            try:
                return "bank", int(key.split("-", 1)[1])
            except (TypeError, ValueError):
                pass
        if led.get("customer_id"):
            return "customer", int(led["customer_id"])
        if led.get("work_id"):
            return "work", int(led["work_id"])
        if led.get("item_id"):
            return "item", int(led["item_id"])
        if key.startswith("item-"):
            try:
                return "item", int(key.split("-", 1)[1])
            except (TypeError, ValueError):
                pass
        return "", None

    def rollup_groups(
        self,
        ledgers: list[dict[str, Any]],
        *,
        natures: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Attach ledgers to group tree and sum closing balances recursively."""
        groups = self.load_groups()
        by_id = {int(g["GroupID"]): g for g in groups}
        if natures:
            allowed = {
                g["GroupID"]
                for g in groups
                if self._nature_from_group(g, by_id) in natures
            }
            for led in ledgers:
                if led.get("nature") in natures and led.get("group_id"):
                    allowed.add(int(led["group_id"]))
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
        chart_group_name = ""
        customer_group_name = ""
        if ledger_key.startswith("coa-"):
            aid = int(ledger_key.split("-", 1)[1])
            info = db.session.execute(
                text(
                    """
                    SELECT a.AccountName,
                           a.OpeningBalance, a.OpeningBalanceDate, a.OpeningBalanceDrCr,
                           a.CustomerID, a.WorkID, a.GroupID,
                           g.GroupName, g.GroupNature, g.UnderType,
                           c.CustomerGroup
                    FROM dbo.ChartOfAccountMaster a
                    LEFT JOIN dbo.ChartOfGroupMaster g ON g.GroupID = a.GroupID
                    LEFT JOIN dbo.CustomerMaster c ON c.CustomerID = a.CustomerID
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
                chart_group_name = (info.get("GroupName") or "").strip()
                customer_group_name = (info.get("CustomerGroup") or "").strip()
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
                {"label": "Chart of Account Group", "value": chart_group_name or "—"},
                {"label": "Customer Group", "value": customer_group_name or "—"},
                {"label": "Ledger Balance", "value": str(self.money(running))},
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
