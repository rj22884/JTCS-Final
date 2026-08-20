from __future__ import annotations

import re
from calendar import monthrange

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from sqlalchemy import text

from app.extensions import db
from app.models.others import (
    OthersIncomeExpenseDetail,
    OthersIncomeExpenseMaster,
    PrintingScanMaster,
    WorkMaster,
)

BILL_NO_PATTERNS = {
    "Income": re.compile(r"^S-(\d{8})/(\d+)$", re.IGNORECASE),
    "Expense": re.compile(r"^E-(\d{8})/(\d+)$", re.IGNORECASE),
    "Misc.": re.compile(r"^M-(\d{8})/(\d+)$", re.IGNORECASE),
}
BILL_NO_PREFIX = {"Income": "S", "Expense": "E", "Misc.": "M"}


class WorkMasterRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = False

    def ensure_schema(self) -> None:
        """Add ChartGroupID + opening balance columns on WorkMaster — masters only."""
        if self._schema_ready:
            return
        for col_sql in (
            """
            IF COL_LENGTH(N'dbo.WorkMaster', N'ChartGroupID') IS NULL
                ALTER TABLE dbo.WorkMaster ADD ChartGroupID INT NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.WorkMaster', N'OpeningBalance') IS NULL
                ALTER TABLE dbo.WorkMaster ADD OpeningBalance DECIMAL(18, 2) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.WorkMaster', N'OpeningBalanceDate') IS NULL
                ALTER TABLE dbo.WorkMaster ADD OpeningBalanceDate DATE NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.WorkMaster', N'OpeningBalanceDrCr') IS NULL
                ALTER TABLE dbo.WorkMaster ADD OpeningBalanceDrCr NVARCHAR(2) NULL;
            """,
        ):
            self.session.execute(text(col_sql))
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.WorkMaster', N'U') IS NOT NULL
                   AND COL_LENGTH(N'dbo.WorkMaster', N'ChartGroupID') IS NOT NULL
                   AND OBJECT_ID(N'dbo.ChartOfGroupMaster', N'U') IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM sys.foreign_keys
                       WHERE name = N'FK_WorkMaster_ChartGroup'
                         AND parent_object_id = OBJECT_ID(N'dbo.WorkMaster')
                   )
                    ALTER TABLE dbo.WorkMaster
                        ADD CONSTRAINT FK_WorkMaster_ChartGroup
                        FOREIGN KEY (ChartGroupID) REFERENCES dbo.ChartOfGroupMaster (GroupID);
                """
            )
        )
        self.session.commit()
        self._schema_ready = True

    def list_active(self, *, ledger_kind: str | None = None) -> list[WorkMaster]:
        return self.list_records(ledger_kind=ledger_kind, active_only=True)

    def list_records(
        self,
        *,
        ledger_kind: str | None = None,
        active_only: bool | None = None,
    ) -> list[WorkMaster]:
        """List WorkMaster rows. active_only=None → all; True/False → filter."""
        self.ensure_schema()
        stmt = select(WorkMaster)
        if active_only is True:
            stmt = stmt.where(WorkMaster.ActiveStatus == True)  # noqa: E712
        elif active_only is False:
            stmt = stmt.where(WorkMaster.ActiveStatus == False)  # noqa: E712
        if ledger_kind:
            stmt = stmt.where(WorkMaster.LedgerKind == ledger_kind)
        stmt = stmt.order_by(
            WorkMaster.ActiveStatus.desc(),
            WorkMaster.LedgerKind,
            WorkMaster.WorkName,
        )
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, work_id: int) -> WorkMaster | None:
        self.ensure_schema()
        return self.session.get(WorkMaster, work_id)

    def find_by_name_kind(self, work_name: str, ledger_kind: str) -> WorkMaster | None:
        self.ensure_schema()
        stmt = select(WorkMaster).where(
            WorkMaster.WorkName == work_name.strip(),
            WorkMaster.LedgerKind == ledger_kind.strip(),
        )
        return self.session.scalars(stmt).first()

    def release_inactive_name_kind(
        self,
        work_name: str,
        ledger_kind: str,
        *,
        keep_work_id: int,
    ) -> None:
        """
        Free UNIQUE(WorkName, LedgerKind) when an inactive conflicting row blocks
        a ledger-kind change (e.g. Expense → Misc. on the same name).
        """
        existing = self.find_by_name_kind(work_name, ledger_kind)
        if existing is None or existing.WorkID == keep_work_id:
            return
        if existing.ActiveStatus:
            return
        archived = f"__archived_{existing.WorkID}_{work_name}".strip()[:100]
        existing.WorkName = archived
        existing.ActiveStatus = False
        self.session.flush()

    def create(self, data: dict) -> WorkMaster:
        self.ensure_schema()
        row = WorkMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: WorkMaster, data: dict) -> WorkMaster:
        self.ensure_schema()
        for key, value in data.items():
            setattr(row, key, value)
        self.session.flush()
        return row

    def deactivate(self, row: WorkMaster) -> WorkMaster:
        self.ensure_schema()
        row.ActiveStatus = False
        self.session.flush()
        return row

    def activate(self, row: WorkMaster) -> WorkMaster:
        self.ensure_schema()
        row.ActiveStatus = True
        self.session.flush()
        return row


class PrintingScanRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def create(self, data: dict) -> PrintingScanMaster:
        row = PrintingScanMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def get_by_id(self, printing_scan_id: int) -> PrintingScanMaster | None:
        return self.session.get(PrintingScanMaster, printing_scan_id)

    def find_by_bill_no(self, bill_no: str) -> PrintingScanMaster | None:
        normalized = (bill_no or "").strip().upper()
        stmt = select(PrintingScanMaster).where(PrintingScanMaster.BillNo == normalized)
        return self.session.scalars(stmt).first()

    def update(self, row: PrintingScanMaster, data: dict) -> PrintingScanMaster:
        for key, value in data.items():
            setattr(row, key, value)
        self.session.flush()
        return row

    def deactivate(self, row: PrintingScanMaster) -> PrintingScanMaster:
        row.IsActive = False
        self.session.flush()
        return row

    @staticmethod
    def _month_bounds(work_date):
        month_start = work_date.replace(day=1)
        last_day = monthrange(work_date.year, work_date.month)[1]
        month_end = work_date.replace(day=last_day)
        return month_start, month_end

    def next_bill_no(
        self,
        work_date,
        *,
        ledger_kind: str = "Income",
        exclude_id: int | None = None,
    ) -> str:
        kind = ledger_kind if ledger_kind in BILL_NO_PATTERNS else "Income"
        pattern = BILL_NO_PATTERNS[kind]
        prefix = BILL_NO_PREFIX[kind]
        month_start, month_end = self._month_bounds(work_date)
        stmt = (
            select(PrintingScanMaster.BillNo)
            .join(WorkMaster, PrintingScanMaster.WorkID == WorkMaster.WorkID)
            .where(
                PrintingScanMaster.IsActive == True,  # noqa: E712
                PrintingScanMaster.WorkDate >= month_start,
                PrintingScanMaster.WorkDate <= month_end,
                WorkMaster.LedgerKind == kind,
            )
        )
        if exclude_id:
            stmt = stmt.where(PrintingScanMaster.PrintingScanID != exclude_id)

        max_seq = 0
        for bill_no in self.session.scalars(stmt).all():
            match = pattern.match((bill_no or "").strip())
            if match:
                max_seq = max(max_seq, int(match.group(2)))

        return f"{prefix}-{work_date.strftime('%d%m%Y')}/{max_seq + 1:03d}"

    def list_recent(self, *, ledger_kind: str | None = None, limit: int = 200) -> list[PrintingScanMaster]:
        stmt = (
            select(PrintingScanMaster)
            .join(WorkMaster, PrintingScanMaster.WorkID == WorkMaster.WorkID)
            .where(PrintingScanMaster.IsActive == True)  # noqa: E712
        )
        if ledger_kind:
            stmt = stmt.where(WorkMaster.LedgerKind == ledger_kind)
        stmt = (
            stmt.order_by(PrintingScanMaster.WorkDate.desc(), PrintingScanMaster.PrintingScanID.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())


class OthersIncomeExpenseRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        # Separate batches: SQL Server validates column names for the whole batch.
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.OthersIncomeExpenseDetail', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.OthersIncomeExpenseDetail (
                        DetailID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        EntryID INT NOT NULL,
                        LineSequence INT NOT NULL,
                        WorkID INT NOT NULL,
                        WorkTypeID INT NULL,
                        Amount DECIMAL(18, 2) NOT NULL,
                        CONSTRAINT FK_OthersIncomeExpenseDetail_Entry
                            FOREIGN KEY (EntryID) REFERENCES dbo.OthersIncomeExpenseMaster (EntryID),
                        CONSTRAINT FK_OthersIncomeExpenseDetail_Work
                            FOREIGN KEY (WorkID) REFERENCES dbo.WorkMaster (WorkID),
                        CONSTRAINT UX_OthersIncomeExpenseDetail_Entry_Seq UNIQUE (EntryID, LineSequence)
                    );
                    CREATE INDEX IX_OthersIncomeExpenseDetail_EntryID
                        ON dbo.OthersIncomeExpenseDetail (EntryID);
                END
                """
            )
        )
        self.session.execute(
            text(
                """
                IF COL_LENGTH(N'dbo.OthersIncomeExpenseDetail', N'WorkTypeID') IS NULL
                    ALTER TABLE dbo.OthersIncomeExpenseDetail ADD WorkTypeID INT NULL;
                """
            )
        )
        self.session.execute(
            text(
                """
                IF EXISTS (
                    SELECT 1 FROM sys.check_constraints
                    WHERE name = N'CK_WorkMaster_LedgerKind'
                      AND parent_object_id = OBJECT_ID(N'dbo.WorkMaster')
                )
                    ALTER TABLE dbo.WorkMaster DROP CONSTRAINT CK_WorkMaster_LedgerKind;
                """
            )
        )
        self.session.execute(
            text(
                """
                IF NOT EXISTS (
                    SELECT 1 FROM sys.check_constraints
                    WHERE name = N'CK_WorkMaster_LedgerKind'
                      AND parent_object_id = OBJECT_ID(N'dbo.WorkMaster')
                )
                    ALTER TABLE dbo.WorkMaster WITH NOCHECK
                    ADD CONSTRAINT CK_WorkMaster_LedgerKind
                    CHECK (LedgerKind IN (N'Income', N'Expense', N'Misc.'));
                """
            )
        )
        self.session.execute(
            text(
                """
                IF COL_LENGTH(N'dbo.WorkTypeMaster', N'SubWorkType') IS NULL
                   AND COL_LENGTH(N'dbo.WorkTypeMaster', N'WorkTypeName') IS NOT NULL
                BEGIN
                    ALTER TABLE dbo.WorkTypeMaster ADD WorkTypeNameNew NVARCHAR(100) NULL;
                END
                """
            )
        )
        self.session.execute(
            text(
                """
                IF COL_LENGTH(N'dbo.WorkTypeMaster', N'WorkTypeNameNew') IS NOT NULL
                   AND COL_LENGTH(N'dbo.WorkTypeMaster', N'SubWorkType') IS NULL
                BEGIN
                    EXEC sp_executesql N'
                        UPDATE dbo.WorkTypeMaster
                        SET WorkTypeNameNew = WorkTypeName
                        WHERE WorkTypeNameNew IS NULL;
                        EXEC sp_rename N''dbo.WorkTypeMaster.WorkTypeName'', N''SubWorkType'', N''COLUMN'';
                        EXEC sp_rename N''dbo.WorkTypeMaster.WorkTypeNameNew'', N''WorkTypeName'', N''COLUMN'';
                    ';
                END
                """
            )
        )
        self.session.execute(
            text(
                """
                IF COL_LENGTH(N'dbo.WorkTypeMaster', N'SubWorkType') IS NOT NULL
                   AND COL_LENGTH(N'dbo.WorkTypeMaster', N'WorkTypeName') IS NOT NULL
                BEGIN
                    EXEC sp_executesql N'
                        ALTER TABLE dbo.WorkTypeMaster ALTER COLUMN WorkTypeName NVARCHAR(100) NOT NULL;
                        ALTER TABLE dbo.WorkTypeMaster ALTER COLUMN SubWorkType NVARCHAR(100) NOT NULL;
                    ';
                END
                """
            )
        )
        self.session.execute(
            text(
                """
                IF NOT EXISTS (
                    SELECT 1 FROM dbo.WorkMaster
                    WHERE WorkName = N'NSDL' AND LedgerKind = N'Misc.'
                )
                    INSERT INTO dbo.WorkMaster (WorkName, LedgerKind, ActiveStatus)
                    VALUES (N'NSDL', N'Misc.', 1);
                """
            )
        )
        self.session.execute(
            text(
                """
                IF COL_LENGTH(N'dbo.WorkTypeMaster', N'SubWorkType') IS NOT NULL
                   AND NOT EXISTS (
                        SELECT 1 FROM dbo.WorkTypeMaster
                        WHERE WorkTypeName = N'NSDL' AND SubWorkType = N'New-Pan'
                   )
                    EXEC sp_executesql N'
                        INSERT INTO dbo.WorkTypeMaster (WorkTypeName, SubWorkType, ActiveStatus)
                        VALUES (N''NSDL'', N''New-Pan'', 1);
                    ';
                """
            )
        )
        self.session.execute(
            text(
                """
                INSERT INTO dbo.OthersIncomeExpenseDetail (EntryID, LineSequence, WorkID, Amount)
                SELECT m.EntryID, 1, m.WorkID, m.Amount
                FROM dbo.OthersIncomeExpenseMaster m
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM dbo.OthersIncomeExpenseDetail d
                    WHERE d.EntryID = m.EntryID
                )
                """
            )
        )
        self.session.commit()
        self._schema_ready = True

    def create(self, data: dict) -> OthersIncomeExpenseMaster:
        self.ensure_schema()
        row = OthersIncomeExpenseMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def get_by_id(self, entry_id: int) -> OthersIncomeExpenseMaster | None:
        self.ensure_schema()
        stmt = (
            select(OthersIncomeExpenseMaster)
            .options(
                joinedload(OthersIncomeExpenseMaster.work_type),
                joinedload(OthersIncomeExpenseMaster.detail_lines).joinedload(
                    OthersIncomeExpenseDetail.work_type
                ),
                joinedload(OthersIncomeExpenseMaster.detail_lines).joinedload(
                    OthersIncomeExpenseDetail.sub_work_type
                ),
            )
            .where(OthersIncomeExpenseMaster.EntryID == entry_id)
        )
        return self.session.scalars(stmt).unique().first()

    def find_by_bill_no(self, bill_no: str) -> OthersIncomeExpenseMaster | None:
        self.ensure_schema()
        normalized = (bill_no or "").strip().upper()
        stmt = select(OthersIncomeExpenseMaster).where(OthersIncomeExpenseMaster.BillNo == normalized)
        return self.session.scalars(stmt).first()

    def update(self, row: OthersIncomeExpenseMaster, data: dict) -> OthersIncomeExpenseMaster:
        self.ensure_schema()
        for key, value in data.items():
            setattr(row, key, value)
        self.session.flush()
        return row

    def deactivate(self, row: OthersIncomeExpenseMaster) -> OthersIncomeExpenseMaster:
        row.IsActive = False
        self.session.flush()
        return row

    def replace_detail_lines(self, entry_id: int, lines: list[dict]) -> list[OthersIncomeExpenseDetail]:
        self.ensure_schema()
        existing = self.session.scalars(
            select(OthersIncomeExpenseDetail).where(OthersIncomeExpenseDetail.EntryID == entry_id)
        ).all()
        for row in existing:
            self.session.delete(row)
        self.session.flush()

        created: list[OthersIncomeExpenseDetail] = []
        for index, line in enumerate(lines, start=1):
            work_type_id = line.get("work_type_id")
            detail = OthersIncomeExpenseDetail(
                EntryID=entry_id,
                LineSequence=index,
                WorkID=int(line["work_id"]),
                WorkTypeID=int(work_type_id) if work_type_id else None,
                Amount=line["amount"],
            )
            self.session.add(detail)
            created.append(detail)
        self.session.flush()
        return created

    def list_detail_lines(self, entry_id: int) -> list[OthersIncomeExpenseDetail]:
        self.ensure_schema()
        stmt = (
            select(OthersIncomeExpenseDetail)
            .options(joinedload(OthersIncomeExpenseDetail.work_type))
            .where(OthersIncomeExpenseDetail.EntryID == entry_id)
            .order_by(OthersIncomeExpenseDetail.LineSequence.asc())
        )
        return list(self.session.scalars(stmt).unique().all())

    def next_bill_no(
        self,
        work_date,
        *,
        ledger_kind: str = "Income",
        exclude_id: int | None = None,
    ) -> str:
        kind = ledger_kind if ledger_kind in BILL_NO_PATTERNS else "Income"
        pattern = BILL_NO_PATTERNS[kind]
        prefix = BILL_NO_PREFIX[kind]
        month_start, month_end = PrintingScanRepository._month_bounds(work_date)
        filters = [
            OthersIncomeExpenseMaster.WorkDate >= month_start,
            OthersIncomeExpenseMaster.WorkDate <= month_end,
            WorkMaster.LedgerKind == kind,
        ]
        if kind == "Income":
            filters.append(OthersIncomeExpenseMaster.IsActive == True)  # noqa: E712
        stmt = (
            select(OthersIncomeExpenseMaster.BillNo)
            .join(WorkMaster, OthersIncomeExpenseMaster.WorkID == WorkMaster.WorkID)
            .where(*filters)
        )
        if exclude_id:
            stmt = stmt.where(OthersIncomeExpenseMaster.EntryID != exclude_id)

        max_seq = 0
        date_part = work_date.strftime("%d%m%Y")
        for bill_no in self.session.scalars(stmt).all():
            match = pattern.match((bill_no or "").strip())
            if match and match.group(1) == date_part:
                max_seq = max(max_seq, int(match.group(2)))

        return f"{prefix}-{date_part}/{max_seq + 1:03d}"

    def next_bill_no_after(self, bill_no: str, *, ledger_kind: str) -> str:
        """Next sequence for same date prefix — used when an inactive bill still occupies a number."""
        kind = ledger_kind if ledger_kind in BILL_NO_PATTERNS else "Income"
        pattern = BILL_NO_PATTERNS[kind]
        prefix = BILL_NO_PREFIX[kind]
        match = pattern.match((bill_no or "").strip())
        if not match:
            raise ValueError("Invalid bill number format.")
        date_part = match.group(1)
        seq = int(match.group(2)) + 1
        return f"{prefix}-{date_part}/{seq:03d}"

    def list_recent(self, *, ledger_kind: str | None = None, limit: int | None = None) -> list[OthersIncomeExpenseMaster]:
        self.ensure_schema()
        stmt = (
            select(OthersIncomeExpenseMaster)
            .options(
                joinedload(OthersIncomeExpenseMaster.work_type),
                joinedload(OthersIncomeExpenseMaster.detail_lines).joinedload(
                    OthersIncomeExpenseDetail.work_type
                ),
            )
            .join(WorkMaster, OthersIncomeExpenseMaster.WorkID == WorkMaster.WorkID)
            .where(OthersIncomeExpenseMaster.IsActive == True)  # noqa: E712
        )
        if ledger_kind:
            stmt = stmt.where(WorkMaster.LedgerKind == ledger_kind)
        stmt = stmt.order_by(
            OthersIncomeExpenseMaster.WorkDate.desc(),
            OthersIncomeExpenseMaster.EntryID.desc(),
        )
        if limit:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt).unique().all())
