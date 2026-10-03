from __future__ import annotations

import re
from calendar import monthrange

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.ration_card import RationCardFollowupMaster
from app.utils.tally_bill import normalize_tally_bill_key, tally_bill_compact

BILL_NO_PATTERN = re.compile(r"^R-(\d{8})/(\d+)$", re.IGNORECASE)
BILL_NO_PREFIX = "R"


class RationCardFollowupRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.RationCardFollowupMaster', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.RationCardFollowupMaster (
                        EntryID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        BillNo NVARCHAR(50) NOT NULL,
                        WorkDate DATE NOT NULL,
                        Amount DECIMAL(18, 2) NOT NULL,
                        FpsRowID INT NULL,
                        FpsCode NVARCHAR(80) NULL,
                        FpsName NVARCHAR(200) NULL,
                        DealerName NVARCHAR(200) NULL,
                        StateName NVARCHAR(120) NULL,
                        DistrictName NVARCHAR(120) NULL,
                        DsoName NVARCHAR(200) NULL,
                        AroName NVARCHAR(200) NULL,
                        WorkDone BIT NOT NULL CONSTRAINT DF_RCF_WorkDone DEFAULT (0),
                        TallyBillGenerated BIT NOT NULL CONSTRAINT DF_RCF_TallyBillGenerated DEFAULT (0),
                        PaymentReceived BIT NOT NULL CONSTRAINT DF_RCF_PaymentReceived DEFAULT (0),
                        TallyBillNo NVARCHAR(50) NULL,
                        TallyBillDate DATE NULL,
                        TallyBillAmount DECIMAL(18, 2) NULL,
                        Remarks NVARCHAR(500) NULL,
                        CreatedBy NVARCHAR(100) NULL,
                        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_RCF_CreatedDate DEFAULT (SYSUTCDATETIME()),
                        IsActive BIT NOT NULL CONSTRAINT DF_RCF_IsActive DEFAULT (1),
                        CONSTRAINT UX_RationCardFollowupMaster_BillNo UNIQUE (BillNo)
                    );
                    CREATE INDEX IX_RCF_WorkDate ON dbo.RationCardFollowupMaster (WorkDate DESC);
                    CREATE INDEX IX_RCF_FpsRowID ON dbo.RationCardFollowupMaster (FpsRowID);
                END
                """
            )
        )
        if self.session.execute(
            text(
                """
                SELECT CASE
                    WHEN OBJECT_ID(N'dbo.PdsFpsMaster', N'U') IS NOT NULL
                     AND OBJECT_ID(N'dbo.RationCardFollowupMaster', N'U') IS NOT NULL
                     AND NOT EXISTS (
                        SELECT 1 FROM sys.foreign_keys
                        WHERE name = N'FK_RCF_FpsRow'
                          AND parent_object_id = OBJECT_ID(N'dbo.RationCardFollowupMaster')
                     )
                    THEN 1 ELSE 0
                END
                """
            )
        ).scalar():
            self.session.execute(
                text(
                    """
                    ALTER TABLE dbo.RationCardFollowupMaster
                    ADD CONSTRAINT FK_RCF_FpsRow
                    FOREIGN KEY (FpsRowID) REFERENCES dbo.PdsFpsMaster (FpsRowID);
                    """
                )
            )
        self.session.commit()
        self._schema_ready = True

    def create(self, data: dict) -> RationCardFollowupMaster:
        self.ensure_schema()
        row = RationCardFollowupMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def get_by_id(self, entry_id: int) -> RationCardFollowupMaster | None:
        self.ensure_schema()
        return self.session.get(RationCardFollowupMaster, entry_id)

    def find_by_bill_no(self, bill_no: str) -> RationCardFollowupMaster | None:
        self.ensure_schema()
        normalized = (bill_no or "").strip().upper()
        stmt = select(RationCardFollowupMaster).where(RationCardFollowupMaster.BillNo == normalized)
        return self.session.scalars(stmt).first()

    def find_by_tally_bill_no(self, bill_no: str) -> RationCardFollowupMaster | None:
        self.ensure_schema()
        key = normalize_tally_bill_key(bill_no)
        if not key:
            return None
        compact = tally_bill_compact(bill_no)
        entry_id = self.session.execute(
            text(
                """
                SELECT TOP 1 e.EntryID
                FROM dbo.RationCardFollowupMaster e
                WHERE e.IsActive = 1
                  AND (
                        (
                            e.TallyBillNo IS NOT NULL
                            AND LTRIM(RTRIM(e.TallyBillNo)) <> N''
                            AND (
                                UPPER(LTRIM(RTRIM(e.TallyBillNo))) = :bill_key
                                OR UPPER(
                                    REPLACE(
                                        REPLACE(LTRIM(RTRIM(e.TallyBillNo)), N' ', N''),
                                        N'-', N''
                                    )
                                ) = :bill_compact
                            )
                        )
                     OR UPPER(LTRIM(RTRIM(e.BillNo))) = :bill_key
                     OR UPPER(
                            REPLACE(
                                REPLACE(LTRIM(RTRIM(e.BillNo)), N' ', N''),
                                N'-', N''
                            )
                        ) = :bill_compact
                  )
                ORDER BY
                    CASE WHEN ISNULL(e.TallyBillGenerated, 0) = 1 THEN 0 ELSE 1 END,
                    e.EntryID DESC
                """
            ),
            {"bill_key": key, "bill_compact": compact},
        ).scalar()
        if not entry_id:
            return None
        return self.get_by_id(int(entry_id))

    def update(self, row: RationCardFollowupMaster, data: dict) -> RationCardFollowupMaster:
        self.ensure_schema()
        for key, value in data.items():
            setattr(row, key, value)
        self.session.flush()
        return row

    def deactivate(self, row: RationCardFollowupMaster) -> RationCardFollowupMaster:
        row.IsActive = False
        self.session.flush()
        return row

    def list_recent(self, *, limit: int | None = None) -> list[RationCardFollowupMaster]:
        self.ensure_schema()
        stmt = (
            select(RationCardFollowupMaster)
            .where(RationCardFollowupMaster.IsActive == True)  # noqa: E712
            .order_by(
                RationCardFollowupMaster.WorkDate.desc(),
                RationCardFollowupMaster.EntryID.desc(),
            )
        )
        if limit:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt).all())

    def next_bill_no(self, work_date) -> str:
        self.ensure_schema()
        month_start = work_date.replace(day=1)
        last_day = monthrange(work_date.year, work_date.month)[1]
        month_end = work_date.replace(day=last_day)
        stmt = select(RationCardFollowupMaster.BillNo).where(
            RationCardFollowupMaster.WorkDate >= month_start,
            RationCardFollowupMaster.WorkDate <= month_end,
            RationCardFollowupMaster.IsActive == True,  # noqa: E712
        )
        max_seq = 0
        date_part = work_date.strftime("%d%m%Y")
        for bill_no in self.session.scalars(stmt).all():
            match = BILL_NO_PATTERN.match((bill_no or "").strip())
            if match and match.group(1) == date_part:
                max_seq = max(max_seq, int(match.group(2)))
        return f"{BILL_NO_PREFIX}-{date_part}/{max_seq + 1:03d}"

    def next_bill_no_after(self, bill_no: str) -> str:
        match = BILL_NO_PATTERN.match((bill_no or "").strip())
        if not match:
            raise ValueError("Invalid bill number format.")
        date_part = match.group(1)
        seq = int(match.group(2)) + 1
        return f"{BILL_NO_PREFIX}-{date_part}/{seq:03d}"
