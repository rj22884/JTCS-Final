from __future__ import annotations

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.ration_card import RationCardMember, RationCardUploadBatch, RationDealerMaster
from app.utils.timezone import now_app


class RationDealerRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.RationDealerMaster', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.RationDealerMaster (
                        DealerID            INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        DealerName          NVARCHAR(200) NOT NULL,
                        FPSID               NVARCHAR(80) NULL,
                        ExistingFPSID       NVARCHAR(80) NULL,
                        DistrictName        NVARCHAR(120) NULL,
                        TehsilName          NVARCHAR(120) NULL,
                        MobileNumber        NVARCHAR(20) NULL,
                        Address             NVARCHAR(400) NULL,
                        ActiveStatus        BIT NOT NULL CONSTRAINT DF_RationDealerMaster_Active DEFAULT (1),
                        CreatedBy           NVARCHAR(150) NULL,
                        CreatedDate         DATETIME2 NOT NULL CONSTRAINT DF_RationDealerMaster_Created DEFAULT (SYSUTCDATETIME()),
                        ModifiedBy          NVARCHAR(150) NULL,
                        ModifiedDate        DATETIME2 NULL
                    );
                    CREATE UNIQUE INDEX UX_RationDealerMaster_DealerName
                        ON dbo.RationDealerMaster (DealerName);
                    CREATE UNIQUE INDEX UX_RationDealerMaster_FPSID
                        ON dbo.RationDealerMaster (FPSID)
                        WHERE FPSID IS NOT NULL AND FPSID <> N'';
                    CREATE INDEX IX_RationDealerMaster_ExistingFPSID
                        ON dbo.RationDealerMaster (ExistingFPSID);
                END;

                IF OBJECT_ID(N'dbo.RationCardUploadBatch', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.RationCardUploadBatch (
                        BatchID             INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        DealerID            INT NOT NULL,
                        SourceFileName      NVARCHAR(260) NULL,
                        FPSID               NVARCHAR(80) NULL,
                        UploadedBy          NVARCHAR(150) NULL,
                        UploadedDate        DATETIME2 NOT NULL CONSTRAINT DF_RationCardUploadBatch_Uploaded DEFAULT (SYSUTCDATETIME()),
                        TotalRows           INT NOT NULL CONSTRAINT DF_RationCardUploadBatch_TotalRows DEFAULT (0),
                        CardCount           INT NOT NULL CONSTRAINT DF_RationCardUploadBatch_CardCount DEFAULT (0),
                        MemberCount         INT NOT NULL CONSTRAINT DF_RationCardUploadBatch_MemberCount DEFAULT (0),
                        ImportMode          NVARCHAR(20) NULL,
                        CONSTRAINT FK_RationCardUploadBatch_Dealer
                            FOREIGN KEY (DealerID) REFERENCES dbo.RationDealerMaster (DealerID)
                    );
                    CREATE INDEX IX_RationCardUploadBatch_DealerID
                        ON dbo.RationCardUploadBatch (DealerID, UploadedDate DESC);
                END;

                IF OBJECT_ID(N'dbo.RationCardMember', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.RationCardMember (
                        MemberRowID         INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        BatchID             INT NOT NULL,
                        DealerID            INT NOT NULL,
                        RowNumber           INT NOT NULL CONSTRAINT DF_RationCardMember_RowNumber DEFAULT (0),
                        DistrictName        NVARCHAR(120) NULL,
                        TehsilName          NVARCHAR(120) NULL,
                        SchemeName          NVARCHAR(80) NULL,
                        ExistingFPSID       NVARCHAR(80) NULL,
                        FPSID               NVARCHAR(80) NULL,
                        RCNumber            NVARCHAR(80) NULL,
                        ExistingRCNumber    NVARCHAR(80) NULL,
                        MemberID            NVARCHAR(80) NULL,
                        ExistingMemberID    NVARCHAR(80) NULL,
                        FullName            NVARCHAR(200) NULL,
                        FatherName          NVARCHAR(200) NULL,
                        MotherName          NVARCHAR(200) NULL,
                        Gender              NVARCHAR(20) NULL,
                        MobileNumber        NVARCHAR(30) NULL,
                        Age                 INT NULL,
                        IsHOF               BIT NOT NULL CONSTRAINT DF_RationCardMember_IsHOF DEFAULT (0),
                        Ekyc                NVARCHAR(80) NULL,
                        UIDStatus           NVARCHAR(80) NULL,
                        ChangeStatus        NVARCHAR(20) NULL,
                        ChangeDetail        NVARCHAR(800) NULL,
                        CONSTRAINT FK_RationCardMember_Batch
                            FOREIGN KEY (BatchID) REFERENCES dbo.RationCardUploadBatch (BatchID),
                        CONSTRAINT FK_RationCardMember_Dealer
                            FOREIGN KEY (DealerID) REFERENCES dbo.RationDealerMaster (DealerID)
                    );
                    CREATE INDEX IX_RationCardMember_BatchID ON dbo.RationCardMember (BatchID, RowNumber);
                    CREATE INDEX IX_RationCardMember_Group
                        ON dbo.RationCardMember (TehsilName, SchemeName, FPSID, RCNumber);
                END;
                """
            )
        )
        self.session.commit()
        self._ensure_import_change_columns()
        self._schema_ready = True

    def _ensure_import_change_columns(self) -> None:
        statements = (
            """
            IF COL_LENGTH(N'dbo.RationCardUploadBatch', N'ImportMode') IS NULL
                ALTER TABLE dbo.RationCardUploadBatch ADD ImportMode NVARCHAR(20) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.RationCardMember', N'ChangeStatus') IS NULL
                ALTER TABLE dbo.RationCardMember ADD ChangeStatus NVARCHAR(20) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.RationCardMember', N'ChangeDetail') IS NULL
                ALTER TABLE dbo.RationCardMember ADD ChangeDetail NVARCHAR(800) NULL;
            """,
        )
        for statement in statements:
            self.session.execute(text(statement))
            self.session.commit()

    def search(
        self,
        term: str | None = None,
        *,
        active_only: bool = False,
        limit: int = 400,
    ) -> list[RationDealerMaster]:
        self.ensure_schema()
        stmt = select(RationDealerMaster).order_by(
            RationDealerMaster.DealerName, RationDealerMaster.DealerID
        )
        if active_only:
            stmt = stmt.where(RationDealerMaster.ActiveStatus == True)  # noqa: E712
        cleaned = (term or "").strip()
        if cleaned:
            like = f"%{cleaned}%"
            stmt = stmt.where(
                or_(
                    RationDealerMaster.DealerName.like(like),
                    RationDealerMaster.FPSID.like(like),
                    RationDealerMaster.ExistingFPSID.like(like),
                    RationDealerMaster.MobileNumber.like(like),
                    RationDealerMaster.TehsilName.like(like),
                    RationDealerMaster.DistrictName.like(like),
                )
            )
        return list(self.session.scalars(stmt.limit(limit)).all())

    def get_by_id(self, dealer_id: int) -> RationDealerMaster | None:
        self.ensure_schema()
        return self.session.get(RationDealerMaster, dealer_id)

    def find_by_name(self, name: str, *, exclude_id: int | None = None) -> RationDealerMaster | None:
        self.ensure_schema()
        cleaned = (name or "").strip()
        if not cleaned:
            return None
        stmt = select(RationDealerMaster).where(
            func.lower(RationDealerMaster.DealerName) == cleaned.lower()
        )
        if exclude_id:
            stmt = stmt.where(RationDealerMaster.DealerID != exclude_id)
        return self.session.scalars(stmt).first()

    def find_by_fps(
        self, fps_id: str, *, exclude_id: int | None = None
    ) -> RationDealerMaster | None:
        self.ensure_schema()
        cleaned = (fps_id or "").strip()
        if not cleaned:
            return None
        stmt = select(RationDealerMaster).where(
            or_(
                func.lower(RationDealerMaster.FPSID) == cleaned.lower(),
                func.lower(RationDealerMaster.ExistingFPSID) == cleaned.lower(),
            )
        )
        if exclude_id:
            stmt = stmt.where(RationDealerMaster.DealerID != exclude_id)
        return self.session.scalars(stmt).first()

    def create(self, data: dict) -> RationDealerMaster:
        self.ensure_schema()
        now = now_app().replace(tzinfo=None)
        data.setdefault("CreatedDate", now)
        data.setdefault("ModifiedDate", now)
        data.setdefault("ActiveStatus", True)
        row = RationDealerMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: RationDealerMaster, data: dict) -> RationDealerMaster:
        preserve = {"DealerID", "CreatedDate", "CreatedBy"}
        for key, value in data.items():
            if key not in preserve:
                setattr(row, key, value)
        row.ModifiedDate = now_app().replace(tzinfo=None)
        self.session.flush()
        return row

    def delete(self, row: RationDealerMaster) -> None:
        self.session.delete(row)
        self.session.flush()

    def create_batch(self, data: dict) -> RationCardUploadBatch:
        self.ensure_schema()
        data.setdefault("UploadedDate", now_app().replace(tzinfo=None))
        batch = RationCardUploadBatch(**data)
        self.session.add(batch)
        self.session.flush()
        return batch

    def add_members(self, rows: list[RationCardMember]) -> None:
        if not rows:
            return
        self.session.add_all(rows)
        self.session.flush()

    def delete_imports_for_dealer(self, dealer_id: int) -> None:
        self.ensure_schema()
        self.session.execute(delete(RationCardMember).where(RationCardMember.DealerID == dealer_id))
        self.session.execute(
            delete(RationCardUploadBatch).where(RationCardUploadBatch.DealerID == dealer_id)
        )
        self.session.flush()

    def latest_batch(self, dealer_id: int) -> RationCardUploadBatch | None:
        self.ensure_schema()
        stmt = (
            select(RationCardUploadBatch)
            .where(RationCardUploadBatch.DealerID == dealer_id)
            .order_by(RationCardUploadBatch.UploadedDate.desc(), RationCardUploadBatch.BatchID.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def members_for_batch(self, batch_id: int) -> list[RationCardMember]:
        self.ensure_schema()
        stmt = (
            select(RationCardMember)
            .where(RationCardMember.BatchID == batch_id)
            .order_by(RationCardMember.RowNumber, RationCardMember.MemberRowID)
        )
        return list(self.session.scalars(stmt).all())
