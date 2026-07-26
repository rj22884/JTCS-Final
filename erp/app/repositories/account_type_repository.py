from __future__ import annotations

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.account_type import AccountTypeMaster
from app.models.transactions import JtcsBankAccountMaster

SEED_TYPES = (
    ("CA-Current Asset", "Current Asset", "Current asset bank account", 1),
    ("CA-Current Account", "Current Account", "Current account", 2),
    ("SB", "Savings Bank", "Savings bank account", 3),
    ("CC/OD", "Cash Credit / Overdraft", "Cash credit or overdraft", 4),
    ("LN-Loan Account", "Loan Account", "Loan account", 5),
    ("DA-Demat Account", "Demat Account", "Demat account", 6),
    ("OTH", "Other", "Other account type", 7),
    ("RD", "Recurring Deposit", "Recurring deposit account", 8),
)


class AccountTypeRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.AccountTypeMaster', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.AccountTypeMaster (
                        AccountTypeID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        AccountTypeCode NVARCHAR(20) NOT NULL,
                        AccountTypeName NVARCHAR(100) NOT NULL,
                        Description NVARCHAR(255) NULL,
                        OrderNo INT NOT NULL CONSTRAINT DF_AccountTypeMaster_OrderNo DEFAULT (100),
                        IsActive BIT NOT NULL CONSTRAINT DF_AccountTypeMaster_IsActive DEFAULT (1),
                        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_AccountTypeMaster_CreatedAt DEFAULT (SYSUTCDATETIME()),
                        UpdatedAt DATETIME2 NULL,
                        CONSTRAINT UX_AccountTypeMaster_Code UNIQUE (AccountTypeCode)
                    );
                END
                """
            )
        )
        self.session.execute(
            text(
                """
                IF EXISTS (
                    SELECT 1 FROM sys.check_constraints
                    WHERE name = N'CK_JtcsBankAccountMaster_AccountType'
                      AND parent_object_id = OBJECT_ID(N'dbo.JtcsBankAccountMaster')
                )
                    ALTER TABLE dbo.JtcsBankAccountMaster
                    DROP CONSTRAINT CK_JtcsBankAccountMaster_AccountType;
                """
            )
        )
        self.session.execute(
            text(
                """
                IF COL_LENGTH(N'dbo.JtcsBankAccountMaster', N'AccountType') IS NOT NULL
                    ALTER TABLE dbo.JtcsBankAccountMaster ALTER COLUMN AccountType NVARCHAR(20) NULL;
                """
            )
        )
        for code, name, desc, order_no in SEED_TYPES:
            self.session.execute(
                text(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM dbo.AccountTypeMaster WHERE AccountTypeCode = :code
                    )
                        INSERT INTO dbo.AccountTypeMaster
                            (AccountTypeCode, AccountTypeName, Description, OrderNo, IsActive)
                        VALUES (:code, :name, :desc, :ord, 1);
                    """
                ),
                {"code": code, "name": name, "desc": desc, "ord": order_no},
            )
        # Pull any AccountType values already used on bank accounts into the master.
        self.session.execute(
            text(
                """
                INSERT INTO dbo.AccountTypeMaster
                    (AccountTypeCode, AccountTypeName, Description, OrderNo, IsActive)
                SELECT DISTINCT
                    LTRIM(RTRIM(b.AccountType)),
                    LTRIM(RTRIM(b.AccountType)),
                    N'Synced from Bank Master',
                    200,
                    1
                FROM dbo.JtcsBankAccountMaster b
                WHERE b.AccountType IS NOT NULL
                  AND LTRIM(RTRIM(b.AccountType)) <> N''
                  AND NOT EXISTS (
                      SELECT 1
                      FROM dbo.AccountTypeMaster t
                      WHERE t.AccountTypeCode = LTRIM(RTRIM(b.AccountType))
                  );
                """
            )
        )
        self.session.commit()
        self._schema_ready = True

    def list_all(self, *, search: str | None = None, active_only: bool = False) -> list[AccountTypeMaster]:
        self.ensure_schema()
        stmt = select(AccountTypeMaster)
        if active_only:
            stmt = stmt.where(AccountTypeMaster.IsActive == True)  # noqa: E712
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    AccountTypeMaster.AccountTypeCode.like(term),
                    AccountTypeMaster.AccountTypeName.like(term),
                    AccountTypeMaster.Description.like(term),
                )
            )
        stmt = stmt.order_by(
            AccountTypeMaster.OrderNo.asc(),
            AccountTypeMaster.AccountTypeCode.asc(),
        )
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, account_type_id: int) -> AccountTypeMaster | None:
        self.ensure_schema()
        return self.session.get(AccountTypeMaster, account_type_id)

    def find_by_code(self, code: str) -> AccountTypeMaster | None:
        self.ensure_schema()
        stmt = select(AccountTypeMaster).where(AccountTypeMaster.AccountTypeCode == code.strip())
        return self.session.scalars(stmt).first()

    def create(self, data: dict) -> AccountTypeMaster:
        self.ensure_schema()
        row = AccountTypeMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: AccountTypeMaster, data: dict) -> AccountTypeMaster:
        for key, value in data.items():
            setattr(row, key, value)
        self.session.flush()
        return row

    def delete(self, row: AccountTypeMaster) -> None:
        self.session.delete(row)
        self.session.flush()

    def usage_count(self, account_type_code: str) -> int:
        self.ensure_schema()
        code = (account_type_code or "").strip()
        if not code:
            return 0
        stmt = select(func.count()).select_from(JtcsBankAccountMaster).where(
            JtcsBankAccountMaster.AccountType == code
        )
        return int(self.session.scalar(stmt) or 0)
