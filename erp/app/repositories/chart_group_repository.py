from __future__ import annotations

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.chart_group import ChartOfGroupMaster

SEED_GROUPS = (
    ("Bank Accounts", "Assets"),
    ("Bank OCC A/c", "Assets"),
    ("Bank OD A/c", "Liabilities"),
    ("Branch / Divisions", "Liabilities"),
    ("Capital Account", "Liabilities"),
    ("Cash-in-Hand", "Assets"),
    ("Commission Income", "Liabilities"),
    ("Computers Printers & Electric Items", "Assets"),
    ("Current Assets", "Assets"),
    ("Current Liabilities", "Liabilities"),
    ("Deposits (Asset)", "Assets"),
    ("Direct Expenses", "Assets"),
    ("Direct Incomes", "Liabilities"),
    ("Duties & Taxes", "Liabilities"),
    ("Electricity Expenses", "Assets"),
    ("Expenses (Direct)", "Assets"),
    ("Expenses (Indirect)", "Assets"),
    ("Fixed Assets", "Assets"),
    ("Immovable Property", "Assets"),
    ("Income (Direct)", "Liabilities"),
    ("Income (Indirect)", "Liabilities"),
    ("Indirect Expenses", "Assets"),
    ("Indirect Incomes", "Liabilities"),
    ("Individual Client", "Assets"),
    ("Investments", "Assets"),
    ("Loans & Advances (Asset)", "Assets"),
    ("Loans (Liability)", "Liabilities"),
    ("Misc. Expenses (ASSET)", "Assets"),
    ("Provisions", "Liabilities"),
    ("Purchase Accounts", "Assets"),
    ("Rent Income", "Liabilities"),
    ("Reserves & Surplus", "Liabilities"),
    ("Retained Earnings", "Liabilities"),
    ("Salary and Wages", "Assets"),
    ("Sales Accounts", "Liabilities"),
    ("Secured Loans", "Liabilities"),
    ("Stock Holding Corporation of India", "Assets"),
    ("Stock-in-Hand", "Assets"),
    ("Sundry Creditors", "Liabilities"),
    ("Sundry Debtors", "Assets"),
    ("Suspense A/c", "Assets"),
    ("Unsecured Loans", "Liabilities"),
)


class ChartGroupRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.ChartOfGroupMaster', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.ChartOfGroupMaster (
                        GroupID       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        GroupName     NVARCHAR(150) NOT NULL,
                        UnderType     NVARCHAR(20)  NOT NULL,
                        ParentGroupID INT NULL,
                        GroupNature   NVARCHAR(20) NULL,
                        IsActive      BIT NOT NULL CONSTRAINT DF_ChartOfGroupMaster_IsActive DEFAULT (1),
                        CreatedDate   DATETIME2 NOT NULL CONSTRAINT DF_ChartOfGroupMaster_Created DEFAULT (SYSUTCDATETIME()),
                        UpdatedDate   DATETIME2 NULL,
                        CONSTRAINT CK_ChartOfGroupMaster_UnderType CHECK (UnderType IN (N'Assets', N'Liabilities')),
                        CONSTRAINT UX_ChartOfGroupMaster_GroupName UNIQUE (GroupName)
                    );
                END
                IF OBJECT_ID(N'dbo.ChartOfGroupMaster', N'U') IS NOT NULL
                   AND COL_LENGTH(N'dbo.ChartOfGroupMaster', N'ParentGroupID') IS NULL
                    ALTER TABLE dbo.ChartOfGroupMaster ADD ParentGroupID INT NULL;
                IF OBJECT_ID(N'dbo.ChartOfGroupMaster', N'U') IS NOT NULL
                   AND COL_LENGTH(N'dbo.ChartOfGroupMaster', N'GroupNature') IS NULL
                    ALTER TABLE dbo.ChartOfGroupMaster ADD GroupNature NVARCHAR(20) NULL;
                """
            )
        )
        for name, under in SEED_GROUPS:
            self.session.execute(
                text(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM dbo.ChartOfGroupMaster WHERE GroupName = :name
                    )
                        INSERT INTO dbo.ChartOfGroupMaster (GroupName, UnderType, IsActive)
                        VALUES (:name, :under, 1);
                    """
                ),
                {"name": name, "under": under},
            )
        self.session.commit()
        self._schema_ready = True

    def list_all(self, *, search: str | None = None, active_only: bool = False):
        self.ensure_schema()
        stmt = select(ChartOfGroupMaster)
        if active_only:
            stmt = stmt.where(ChartOfGroupMaster.IsActive == True)  # noqa: E712
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    ChartOfGroupMaster.GroupName.like(like),
                    ChartOfGroupMaster.UnderType.like(like),
                )
            )
        stmt = stmt.order_by(ChartOfGroupMaster.GroupName.asc())
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, group_id: int) -> ChartOfGroupMaster | None:
        self.ensure_schema()
        return self.session.get(ChartOfGroupMaster, group_id)

    def find_by_name(self, name: str, *, exclude_id: int | None = None) -> ChartOfGroupMaster | None:
        self.ensure_schema()
        stmt = select(ChartOfGroupMaster).where(
            func.lower(ChartOfGroupMaster.GroupName) == name.strip().lower()
        )
        if exclude_id is not None:
            stmt = stmt.where(ChartOfGroupMaster.GroupID != exclude_id)
        return self.session.scalars(stmt).first()

    def count_accounts(self, group_id: int) -> int:
        self.ensure_schema()
        row = self.session.execute(
            text(
                """
                SELECT COUNT(1) AS cnt
                FROM dbo.ChartOfAccountMaster
                WHERE GroupID = :gid
                """
            ),
            {"gid": group_id},
        ).first()
        return int(row[0] if row else 0)

    def create(self, data: dict) -> ChartOfGroupMaster:
        self.ensure_schema()
        row = ChartOfGroupMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: ChartOfGroupMaster, data: dict) -> ChartOfGroupMaster:
        for key, value in data.items():
            setattr(row, key, value)
        self.session.flush()
        return row

    def delete(self, row: ChartOfGroupMaster) -> None:
        self.session.delete(row)
        self.session.flush()
