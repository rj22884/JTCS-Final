from __future__ import annotations

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.chart_account import ChartOfAccountMaster
from app.models.chart_group import ChartOfGroupMaster


class ChartAccountRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        from app.repositories.chart_group_repository import ChartGroupRepository

        ChartGroupRepository(self.session).ensure_schema()
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.ChartOfAccountMaster (
                        AccountID     INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        AccountName   NVARCHAR(200) NOT NULL,
                        GroupID       INT NOT NULL,
                        CustomerID    INT NULL,
                        WorkID        INT NULL,
                        IsActive      BIT NOT NULL CONSTRAINT DF_ChartOfAccountMaster_IsActive DEFAULT (1),
                        CreatedDate   DATETIME2 NOT NULL CONSTRAINT DF_ChartOfAccountMaster_Created DEFAULT (SYSUTCDATETIME()),
                        UpdatedDate   DATETIME2 NULL,
                        CONSTRAINT FK_ChartOfAccountMaster_Group
                            FOREIGN KEY (GroupID) REFERENCES dbo.ChartOfGroupMaster (GroupID),
                        CONSTRAINT UX_ChartOfAccountMaster_AccountName UNIQUE (AccountName)
                    );
                    CREATE INDEX IX_ChartOfAccountMaster_GroupID ON dbo.ChartOfAccountMaster (GroupID);
                END
                """
            )
        )
        for col_sql in (
            """
            IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
               AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'CustomerID') IS NULL
                ALTER TABLE dbo.ChartOfAccountMaster ADD CustomerID INT NULL;
            """,
            """
            IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
               AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'WorkID') IS NULL
                ALTER TABLE dbo.ChartOfAccountMaster ADD WorkID INT NULL;
            """,
            """
            IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
               AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'OpeningBalance') IS NULL
                ALTER TABLE dbo.ChartOfAccountMaster ADD OpeningBalance DECIMAL(18, 2) NULL;
            """,
            """
            IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
               AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'OpeningBalanceDate') IS NULL
                ALTER TABLE dbo.ChartOfAccountMaster ADD OpeningBalanceDate DATE NULL;
            """,
            """
            IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
               AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'OpeningBalanceDrCr') IS NULL
                ALTER TABLE dbo.ChartOfAccountMaster ADD OpeningBalanceDrCr NVARCHAR(2) NULL;
            """,
        ):
            self.session.execute(text(col_sql))

        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
                   AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'CustomerID') IS NOT NULL
                   AND OBJECT_ID(N'dbo.CustomerMaster', N'U') IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM sys.foreign_keys
                       WHERE name = N'FK_ChartOfAccountMaster_Customer'
                         AND parent_object_id = OBJECT_ID(N'dbo.ChartOfAccountMaster')
                   )
                    ALTER TABLE dbo.ChartOfAccountMaster
                        ADD CONSTRAINT FK_ChartOfAccountMaster_Customer
                        FOREIGN KEY (CustomerID) REFERENCES dbo.CustomerMaster (CustomerID);
                """
            )
        )
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
                   AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'WorkID') IS NOT NULL
                   AND OBJECT_ID(N'dbo.WorkMaster', N'U') IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM sys.foreign_keys
                       WHERE name = N'FK_ChartOfAccountMaster_Work'
                         AND parent_object_id = OBJECT_ID(N'dbo.ChartOfAccountMaster')
                   )
                    ALTER TABLE dbo.ChartOfAccountMaster
                        ADD CONSTRAINT FK_ChartOfAccountMaster_Work
                        FOREIGN KEY (WorkID) REFERENCES dbo.WorkMaster (WorkID);
                """
            )
        )
        for idx_sql in (
            """
            IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
               AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'CustomerID') IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM sys.indexes
                   WHERE name = N'UX_ChartOfAccountMaster_CustomerID'
                     AND object_id = OBJECT_ID(N'dbo.ChartOfAccountMaster')
               )
                CREATE UNIQUE INDEX UX_ChartOfAccountMaster_CustomerID
                    ON dbo.ChartOfAccountMaster (CustomerID)
                    WHERE CustomerID IS NOT NULL;
            """,
            """
            IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
               AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'WorkID') IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM sys.indexes
                   WHERE name = N'UX_ChartOfAccountMaster_WorkID'
                     AND object_id = OBJECT_ID(N'dbo.ChartOfAccountMaster')
               )
                CREATE UNIQUE INDEX UX_ChartOfAccountMaster_WorkID
                    ON dbo.ChartOfAccountMaster (WorkID)
                    WHERE WorkID IS NOT NULL;
            """,
        ):
            self.session.execute(text(idx_sql))

        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.ChartOfAccountGroupLink', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.ChartOfAccountGroupLink (
                        AccountID    INT NOT NULL,
                        GroupID      INT NOT NULL,
                        DisplayOrder TINYINT NOT NULL CONSTRAINT DF_ChartOfAccountGroupLink_Order DEFAULT (1),
                        CONSTRAINT PK_ChartOfAccountGroupLink PRIMARY KEY (AccountID, GroupID),
                        CONSTRAINT FK_ChartOfAccountGroupLink_Account
                            FOREIGN KEY (AccountID) REFERENCES dbo.ChartOfAccountMaster (AccountID) ON DELETE CASCADE,
                        CONSTRAINT FK_ChartOfAccountGroupLink_Group
                            FOREIGN KEY (GroupID) REFERENCES dbo.ChartOfGroupMaster (GroupID)
                    );
                    CREATE INDEX IX_ChartOfAccountGroupLink_GroupID
                        ON dbo.ChartOfAccountGroupLink (GroupID);
                END
                """
            )
        )
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.ChartOfAccountGroupLink', N'U') IS NOT NULL
                    INSERT INTO dbo.ChartOfAccountGroupLink (AccountID, GroupID, DisplayOrder)
                    SELECT a.AccountID, a.GroupID, 1
                    FROM dbo.ChartOfAccountMaster a
                    WHERE a.GroupID IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM dbo.ChartOfAccountGroupLink l
                          WHERE l.AccountID = a.AccountID AND l.GroupID = a.GroupID
                      );
                """
            )
        )
        self.session.commit()
        self._schema_ready = True

    def list_customer_ledger_rows(self, *, search: str | None = None) -> list[dict]:
        """Active CustomerMaster rows LEFT JOIN chart-account group mapping (read-only on customers)."""
        self.ensure_schema()
        params: dict = {}
        search_sql = ""
        if search and search.strip():
            params["like"] = f"%{search.strip()}%"
            search_sql = """
              AND (
                    c.CustomerName LIKE :like
                 OR ISNULL(gx.GroupNames, N'') LIKE :like
                 OR ISNULL(gx.UnderTypes, N'') LIKE :like
                 OR ISNULL(g.GroupName, N'') LIKE :like
              )
            """
        rows = self.session.execute(
            text(
                f"""
                SELECT
                    c.CustomerID,
                    c.CustomerName,
                    c.CustomerStatus,
                    a.AccountID,
                    a.GroupID,
                    a.IsActive AS AccountIsActive,
                    a.CreatedDate AS AccountCreatedDate,
                    a.UpdatedDate AS AccountUpdatedDate,
                    a.OpeningBalance,
                    a.OpeningBalanceDate,
                    a.OpeningBalanceDrCr,
                    g.GroupName,
                    g.UnderType,
                    gx.GroupIDs,
                    gx.GroupNames,
                    gx.UnderTypes
                FROM dbo.CustomerMaster c
                LEFT JOIN dbo.ChartOfAccountMaster a
                    ON a.CustomerID = c.CustomerID
                LEFT JOIN dbo.ChartOfGroupMaster g
                    ON g.GroupID = a.GroupID
                OUTER APPLY (
                    SELECT
                        STRING_AGG(CAST(l.GroupID AS NVARCHAR(20)), N',')
                            WITHIN GROUP (ORDER BY l.DisplayOrder, l.GroupID) AS GroupIDs,
                        STRING_AGG(gm.GroupName, N', ')
                            WITHIN GROUP (ORDER BY l.DisplayOrder, l.GroupID) AS GroupNames,
                        STRING_AGG(gm.UnderType, N', ')
                            WITHIN GROUP (ORDER BY l.DisplayOrder, l.GroupID) AS UnderTypes
                    FROM dbo.ChartOfAccountGroupLink l
                    INNER JOIN dbo.ChartOfGroupMaster gm ON gm.GroupID = l.GroupID
                    WHERE l.AccountID = a.AccountID
                ) gx
                WHERE ISNULL(c.CustomerStatus, N'Active') <> N'Inactive'
                  AND ISNULL(c.CustomerStatus, N'Active') <> N'Rejected'
                  {search_sql}
                ORDER BY c.CustomerName ASC
                """
            ),
            params,
        ).mappings().all()
        return [dict(row) for row in rows]

    def list_work_ledger_rows(self, *, search: str | None = None) -> list[dict]:
        """Active WorkMaster (Income/Expense) rows LEFT JOIN CoA mapping — read-only on WorkMaster."""
        self.ensure_schema()
        params: dict = {}
        search_sql = ""
        if search and search.strip():
            params["like"] = f"%{search.strip()}%"
            search_sql = """
              AND (
                    w.WorkName LIKE :like
                 OR ISNULL(w.LedgerKind, N'') LIKE :like
                 OR ISNULL(gx.GroupNames, N'') LIKE :like
                 OR ISNULL(gx.UnderTypes, N'') LIKE :like
                 OR ISNULL(g.GroupName, N'') LIKE :like
              )
            """
        rows = self.session.execute(
            text(
                f"""
                SELECT
                    w.WorkID,
                    w.WorkName,
                    w.LedgerKind,
                    w.ActiveStatus,
                    a.AccountID,
                    a.GroupID,
                    a.IsActive AS AccountIsActive,
                    a.CreatedDate AS AccountCreatedDate,
                    a.UpdatedDate AS AccountUpdatedDate,
                    a.OpeningBalance,
                    a.OpeningBalanceDate,
                    a.OpeningBalanceDrCr,
                    g.GroupName,
                    g.UnderType,
                    gx.GroupIDs,
                    gx.GroupNames,
                    gx.UnderTypes
                FROM dbo.WorkMaster w
                LEFT JOIN dbo.ChartOfAccountMaster a
                    ON a.WorkID = w.WorkID
                LEFT JOIN dbo.ChartOfGroupMaster g
                    ON g.GroupID = a.GroupID
                OUTER APPLY (
                    SELECT
                        STRING_AGG(CAST(l.GroupID AS NVARCHAR(20)), N',')
                            WITHIN GROUP (ORDER BY l.DisplayOrder, l.GroupID) AS GroupIDs,
                        STRING_AGG(gm.GroupName, N', ')
                            WITHIN GROUP (ORDER BY l.DisplayOrder, l.GroupID) AS GroupNames,
                        STRING_AGG(gm.UnderType, N', ')
                            WITHIN GROUP (ORDER BY l.DisplayOrder, l.GroupID) AS UnderTypes
                    FROM dbo.ChartOfAccountGroupLink l
                    INNER JOIN dbo.ChartOfGroupMaster gm ON gm.GroupID = l.GroupID
                    WHERE l.AccountID = a.AccountID
                ) gx
                WHERE ISNULL(w.ActiveStatus, 1) = 1
                  {search_sql}
                ORDER BY w.WorkName ASC
                """
            ),
            params,
        ).mappings().all()
        return [dict(row) for row in rows]

    def list_manual_accounts(self, *, search: str | None = None, active_only: bool = False):
        """Manual chart accounts (not linked to customer or work)."""
        self.ensure_schema()
        stmt = (
            select(ChartOfAccountMaster)
            .outerjoin(ChartOfGroupMaster, ChartOfAccountMaster.GroupID == ChartOfGroupMaster.GroupID)
            .where(
                and_(
                    ChartOfAccountMaster.CustomerID.is_(None),
                    ChartOfAccountMaster.WorkID.is_(None),
                )
            )
        )
        if active_only:
            stmt = stmt.where(ChartOfAccountMaster.IsActive == True)  # noqa: E712
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    ChartOfAccountMaster.AccountName.like(like),
                    ChartOfGroupMaster.GroupName.like(like),
                )
            )
        stmt = stmt.order_by(ChartOfAccountMaster.AccountName.asc())
        return list(self.session.scalars(stmt).unique().all())

    def get_by_id(self, account_id: int) -> ChartOfAccountMaster | None:
        self.ensure_schema()
        return self.session.get(ChartOfAccountMaster, account_id)

    def get_by_customer_id(self, customer_id: int) -> ChartOfAccountMaster | None:
        self.ensure_schema()
        stmt = select(ChartOfAccountMaster).where(ChartOfAccountMaster.CustomerID == customer_id)
        return self.session.scalars(stmt).first()

    def get_by_work_id(self, work_id: int) -> ChartOfAccountMaster | None:
        self.ensure_schema()
        stmt = select(ChartOfAccountMaster).where(ChartOfAccountMaster.WorkID == work_id)
        return self.session.scalars(stmt).first()

    def get_customer_name(self, customer_id: int) -> str | None:
        """Read-only lookup on CustomerMaster — does not alter customer tables/files."""
        self.ensure_schema()
        row = self.session.execute(
            text(
                """
                SELECT TOP 1 CustomerName
                FROM dbo.CustomerMaster
                WHERE CustomerID = :cid
                  AND ISNULL(CustomerStatus, N'Active') <> N'Inactive'
                  AND ISNULL(CustomerStatus, N'Active') <> N'Rejected'
                """
            ),
            {"cid": customer_id},
        ).first()
        if not row:
            return None
        return (row[0] or "").strip() or None

    def get_work_info(self, work_id: int) -> dict | None:
        """Read-only lookup on WorkMaster — does not alter work/income-expense master files."""
        self.ensure_schema()
        row = self.session.execute(
            text(
                """
                SELECT TOP 1 WorkID, WorkName, LedgerKind
                FROM dbo.WorkMaster
                WHERE WorkID = :wid
                  AND ISNULL(ActiveStatus, 1) = 1
                """
            ),
            {"wid": work_id},
        ).mappings().first()
        if not row:
            return None
        return {
            "work_id": int(row["WorkID"]),
            "work_name": (row.get("WorkName") or "").strip(),
            "ledger_kind": (row.get("LedgerKind") or "").strip(),
        }

    def find_by_name(self, name: str, *, exclude_id: int | None = None) -> ChartOfAccountMaster | None:
        self.ensure_schema()
        stmt = select(ChartOfAccountMaster).where(
            func.lower(ChartOfAccountMaster.AccountName) == name.strip().lower(),
            ChartOfAccountMaster.IsActive == True,  # noqa: E712
        )
        if exclude_id is not None:
            stmt = stmt.where(ChartOfAccountMaster.AccountID != exclude_id)
        return self.session.scalars(stmt).first()

    def create(self, data: dict) -> ChartOfAccountMaster:
        self.ensure_schema()
        row = ChartOfAccountMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: ChartOfAccountMaster, data: dict) -> ChartOfAccountMaster:
        for key, value in data.items():
            setattr(row, key, value)
        self.session.flush()
        return row

    def delete(self, row: ChartOfAccountMaster) -> None:
        self.session.delete(row)
        self.session.flush()

    def list_group_links(self, account_id: int) -> list[dict]:
        """Ordered group links for one account."""
        self.ensure_schema()
        rows = self.session.execute(
            text(
                """
                SELECT l.GroupID, l.DisplayOrder, g.GroupName, g.UnderType
                FROM dbo.ChartOfAccountGroupLink l
                INNER JOIN dbo.ChartOfGroupMaster g ON g.GroupID = l.GroupID
                WHERE l.AccountID = :aid
                ORDER BY l.DisplayOrder, l.GroupID
                """
            ),
            {"aid": account_id},
        ).mappings().all()
        return [dict(row) for row in rows]

    def replace_group_links(self, account_id: int, group_ids: list[int]) -> None:
        """Replace all group links for an account (caller enforces max 5)."""
        self.ensure_schema()
        self.session.execute(
            text("DELETE FROM dbo.ChartOfAccountGroupLink WHERE AccountID = :aid"),
            {"aid": account_id},
        )
        for order, gid in enumerate(group_ids, start=1):
            self.session.execute(
                text(
                    """
                    INSERT INTO dbo.ChartOfAccountGroupLink (AccountID, GroupID, DisplayOrder)
                    VALUES (:aid, :gid, :ord)
                    """
                ),
                {"aid": account_id, "gid": gid, "ord": order},
            )
        self.session.flush()
