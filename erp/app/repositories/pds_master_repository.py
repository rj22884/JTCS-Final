from __future__ import annotations

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.ration_card import PdsGeoImport, PdsRationCardMaster
from app.utils.timezone import now_app

_SCHEMA_BLOCKS = (
    """
IF OBJECT_ID(N'dbo.PdsStateMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsStateMaster (
        StateID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        StateCode NVARCHAR(10) NOT NULL,
        StateName NVARCHAR(120) NOT NULL,
        Source NVARCHAR(80) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_PdsStateMaster_Active DEFAULT (1),
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsStateMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME2 NULL
    );
    CREATE UNIQUE INDEX UX_PdsStateMaster_StateCode ON dbo.PdsStateMaster (StateCode);
END;
""",
    """
IF OBJECT_ID(N'dbo.PdsDistrictMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsDistrictMaster (
        DistrictID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        StateID INT NOT NULL,
        DistrictCode NVARCHAR(20) NOT NULL,
        DistrictName NVARCHAR(120) NOT NULL,
        Headquarters NVARCHAR(120) NULL,
        DivisionName NVARCHAR(80) NULL,
        Source NVARCHAR(80) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_PdsDistrictMaster_Active DEFAULT (1),
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsDistrictMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT FK_PdsDistrictMaster_State FOREIGN KEY (StateID) REFERENCES dbo.PdsStateMaster (StateID)
    );
    CREATE UNIQUE INDEX UX_PdsDistrictMaster_StateCode ON dbo.PdsDistrictMaster (StateID, DistrictCode);
    CREATE INDEX IX_PdsDistrictMaster_Name ON dbo.PdsDistrictMaster (DistrictName);
END;
""",
    """
IF OBJECT_ID(N'dbo.PdsDsoMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsDsoMaster (
        DsoID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        DistrictID INT NOT NULL,
        DsoCode NVARCHAR(40) NOT NULL,
        DsoName NVARCHAR(200) NOT NULL,
        OfficerName NVARCHAR(200) NULL,
        MobileNumber NVARCHAR(20) NULL,
        Address NVARCHAR(400) NULL,
        Source NVARCHAR(80) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_PdsDsoMaster_Active DEFAULT (1),
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsDsoMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT FK_PdsDsoMaster_District FOREIGN KEY (DistrictID) REFERENCES dbo.PdsDistrictMaster (DistrictID)
    );
    CREATE UNIQUE INDEX UX_PdsDsoMaster_DistrictCode ON dbo.PdsDsoMaster (DistrictID, DsoCode);
END;
""",
    """
IF OBJECT_ID(N'dbo.PdsAroMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsAroMaster (
        AroID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        DsoID INT NOT NULL,
        AroCode NVARCHAR(40) NOT NULL,
        AroName NVARCHAR(200) NOT NULL,
        OfficerName NVARCHAR(200) NULL,
        MobileNumber NVARCHAR(20) NULL,
        Address NVARCHAR(400) NULL,
        Source NVARCHAR(80) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_PdsAroMaster_Active DEFAULT (1),
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsAroMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT FK_PdsAroMaster_Dso FOREIGN KEY (DsoID) REFERENCES dbo.PdsDsoMaster (DsoID)
    );
    CREATE UNIQUE INDEX UX_PdsAroMaster_DsoCode ON dbo.PdsAroMaster (DsoID, AroCode);
END;
""",
    """
IF OBJECT_ID(N'dbo.PdsFpsMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsFpsMaster (
        FpsRowID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        DistrictID INT NOT NULL,
        DsoID INT NULL,
        AroID INT NULL,
        FpsCode NVARCHAR(80) NOT NULL,
        ExistingFpsId NVARCHAR(80) NULL,
        FpsName NVARCHAR(200) NOT NULL,
        DealerName NVARCHAR(200) NULL,
        TehsilName NVARCHAR(120) NULL,
        VillageName NVARCHAR(120) NULL,
        PinCode NVARCHAR(12) NULL,
        MobileNumber NVARCHAR(20) NULL,
        Address NVARCHAR(400) NULL,
        Source NVARCHAR(80) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_PdsFpsMaster_Active DEFAULT (1),
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsFpsMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT FK_PdsFpsMaster_District FOREIGN KEY (DistrictID) REFERENCES dbo.PdsDistrictMaster (DistrictID),
        CONSTRAINT FK_PdsFpsMaster_Dso FOREIGN KEY (DsoID) REFERENCES dbo.PdsDsoMaster (DsoID),
        CONSTRAINT FK_PdsFpsMaster_Aro FOREIGN KEY (AroID) REFERENCES dbo.PdsAroMaster (AroID)
    );
    CREATE UNIQUE INDEX UX_PdsFpsMaster_FpsCode ON dbo.PdsFpsMaster (FpsCode) WHERE FpsCode <> N'';
    CREATE INDEX IX_PdsFpsMaster_District ON dbo.PdsFpsMaster (DistrictID);
END;
""",
    """
IF OBJECT_ID(N'dbo.PdsRationCardMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsRationCardMaster (
        CardID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        FpsRowID INT NOT NULL,
        RcNumber NVARCHAR(80) NOT NULL,
        ExistingRcNumber NVARCHAR(80) NULL,
        SchemeName NVARCHAR(80) NULL,
        HofName NVARCHAR(200) NULL,
        MemberCount INT NULL,
        MobileNumber NVARCHAR(20) NULL,
        Source NVARCHAR(80) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_PdsRationCardMaster_Active DEFAULT (1),
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsRationCardMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT FK_PdsRationCardMaster_Fps FOREIGN KEY (FpsRowID) REFERENCES dbo.PdsFpsMaster (FpsRowID)
    );
    CREATE UNIQUE INDEX UX_PdsRationCardMaster_FpsRc ON dbo.PdsRationCardMaster (FpsRowID, RcNumber) WHERE RcNumber <> N'';
    CREATE INDEX IX_PdsRationCardMaster_Fps ON dbo.PdsRationCardMaster (FpsRowID);
END;
""",
    """
IF OBJECT_ID(N'dbo.PdsGeoImport', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsGeoImport (
        ImportKey NVARCHAR(80) NOT NULL PRIMARY KEY,
        Source NVARCHAR(260) NULL,
        ImportRowCount INT NOT NULL CONSTRAINT DF_PdsGeoImport_RowCount DEFAULT (0),
        Detail NVARCHAR(500) NULL,
        ImportedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsGeoImport_Imported DEFAULT (SYSUTCDATETIME())
    );
END;
""",
)

_SCHEMA_UPGRADES = (
    """
IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_PdsRationCardMaster_RcNumber'
      AND object_id = OBJECT_ID(N'dbo.PdsRationCardMaster')
)
    DROP INDEX UX_PdsRationCardMaster_RcNumber ON dbo.PdsRationCardMaster;
""",
    """
IF OBJECT_ID(N'dbo.PdsRationCardMaster', N'U') IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_PdsRationCardMaster_FpsRc'
      AND object_id = OBJECT_ID(N'dbo.PdsRationCardMaster')
)
    CREATE UNIQUE INDEX UX_PdsRationCardMaster_FpsRc
        ON dbo.PdsRationCardMaster (FpsRowID, RcNumber)
        WHERE RcNumber <> N'';
""",
    """
IF EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = N'FK_PdsFpsMaster_Si'
      AND parent_object_id = OBJECT_ID(N'dbo.PdsFpsMaster')
)
    ALTER TABLE dbo.PdsFpsMaster DROP CONSTRAINT FK_PdsFpsMaster_Si;
""",
    """
IF COL_LENGTH(N'dbo.PdsFpsMaster', N'SiID') IS NOT NULL
BEGIN
    DECLARE @dropSiIx NVARCHAR(MAX) = N'';
    SELECT @dropSiIx = @dropSiIx + N'DROP INDEX ' + QUOTENAME(i.name) + N' ON dbo.PdsFpsMaster;'
    FROM sys.indexes i
    INNER JOIN sys.index_columns ic
        ON i.object_id = ic.object_id AND i.index_id = ic.index_id
    INNER JOIN sys.columns c
        ON ic.object_id = c.object_id AND ic.column_id = c.column_id
    WHERE i.object_id = OBJECT_ID(N'dbo.PdsFpsMaster')
      AND c.name = N'SiID'
      AND i.is_primary_key = 0
      AND ISNULL(i.is_unique_constraint, 0) = 0
      AND i.name IS NOT NULL;
    IF @dropSiIx <> N''
        EXEC sp_executesql @dropSiIx;
END;
""",
    """
IF COL_LENGTH(N'dbo.PdsFpsMaster', N'SiID') IS NOT NULL
    ALTER TABLE dbo.PdsFpsMaster DROP COLUMN SiID;
""",
    """
IF OBJECT_ID(N'dbo.PdsSiMaster', N'U') IS NOT NULL
    DROP TABLE dbo.PdsSiMaster;
""",
    """
IF COL_LENGTH(N'dbo.PdsFpsMaster', N'VillageName') IS NULL
    ALTER TABLE dbo.PdsFpsMaster ADD VillageName NVARCHAR(120) NULL;
""",
    """
IF COL_LENGTH(N'dbo.PdsFpsMaster', N'PinCode') IS NULL
    ALTER TABLE dbo.PdsFpsMaster ADD PinCode NVARCHAR(12) NULL;
""",
    """
IF OBJECT_ID(N'dbo.PdsDistrictMaster', N'U') IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_PdsDistrictMaster_DistrictCodeOnly'
      AND object_id = OBJECT_ID(N'dbo.PdsDistrictMaster')
)
    CREATE UNIQUE INDEX UX_PdsDistrictMaster_DistrictCodeOnly
        ON dbo.PdsDistrictMaster (DistrictCode)
        WHERE DistrictCode <> N'';
""",
    """
IF OBJECT_ID(N'dbo.PdsDsoMaster', N'U') IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_PdsDsoMaster_DsoCodeOnly'
      AND object_id = OBJECT_ID(N'dbo.PdsDsoMaster')
)
    CREATE UNIQUE INDEX UX_PdsDsoMaster_DsoCodeOnly
        ON dbo.PdsDsoMaster (DsoCode)
        WHERE DsoCode <> N'';
""",
    """
IF OBJECT_ID(N'dbo.PdsAroMaster', N'U') IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_PdsAroMaster_AroCodeOnly'
      AND object_id = OBJECT_ID(N'dbo.PdsAroMaster')
)
    CREATE UNIQUE INDEX UX_PdsAroMaster_AroCodeOnly
        ON dbo.PdsAroMaster (AroCode)
        WHERE AroCode <> N'';
""",
)


class PdsMasterRepository:
    _schema_ready_global = False

    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = PdsMasterRepository._schema_ready_global

    def ensure_schema(self) -> None:
        if self._schema_ready or PdsMasterRepository._schema_ready_global:
            self._schema_ready = True
            PdsMasterRepository._schema_ready_global = True
            return
        for block in _SCHEMA_BLOCKS:
            self.session.execute(text(block))
            self.session.commit()
        for block in _SCHEMA_UPGRADES:
            self.session.execute(text(block))
            self.session.commit()
        self._schema_ready = True
        PdsMasterRepository._schema_ready_global = True

    def import_done(self, key: str) -> bool:
        self.ensure_schema()
        return self.session.get(PdsGeoImport, key) is not None

    def mark_import(self, key: str, *, source: str, row_count: int, detail: str) -> None:
        self.ensure_schema()
        row = self.session.get(PdsGeoImport, key)
        now = now_app().replace(tzinfo=None)
        if row is None:
            self.session.add(
                PdsGeoImport(
                    ImportKey=key,
                    Source=source,
                    ImportRowCount=row_count,
                    Detail=detail,
                    ImportedDate=now,
                )
            )
        else:
            row.Source = source
            row.ImportRowCount = row_count
            row.Detail = detail
            row.ImportedDate = now
        self.session.flush()

    def list_rows(self, model, *, search: str | None = None, filters: dict | None = None, limit: int | None = 20000):
        self.ensure_schema()
        stmt = select(model)
        filters = filters or {}
        for column, value in filters.items():
            if value in (None, ""):
                continue
            stmt = stmt.where(getattr(model, column) == value)
        cleaned = (search or "").strip()
        if cleaned:
            like = f"%{cleaned}%"
            text_columns = [
                col
                for col in (
                    "StateName",
                    "StateCode",
                    "DistrictName",
                    "DistrictCode",
                    "DsoName",
                    "DsoCode",
                    "AroName",
                    "AroCode",
                    "FpsName",
                    "FpsCode",
                    "ExistingFpsId",
                    "DealerName",
                    "RcNumber",
                    "ExistingRcNumber",
                    "HofName",
                    "SchemeName",
                    "OfficerName",
                    "Headquarters",
                    "VillageName",
                    "PinCode",
                )
                if hasattr(model, col)
            ]
            if text_columns:
                stmt = stmt.where(or_(*[getattr(model, col).like(like) for col in text_columns]))
        pk = list(model.__mapper__.primary_key)[0]
        name_col = next(
            (getattr(model, name) for name in ("StateName", "DistrictName", "DsoName", "AroName", "FpsName", "RcNumber") if hasattr(model, name)),
            pk,
        )
        stmt = stmt.order_by(name_col, pk)
        if limit:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt).all())

    def find_by_code(self, model, column: str, code: str, *, exclude_id: int | None = None):
        self.ensure_schema()
        cleaned = (code or "").strip()
        if not cleaned or not hasattr(model, column):
            return None
        pk = list(model.__mapper__.primary_key)[0]
        stmt = select(model).where(func.lower(getattr(model, column)) == cleaned.lower())
        if exclude_id:
            stmt = stmt.where(pk != int(exclude_id))
        return self.session.scalars(stmt).first()

    def find_ration_card(self, fps_row_id: int | None, rc_number: str | None) -> PdsRationCardMaster | None:
        self.ensure_schema()
        fps_id = int(fps_row_id or 0)
        cleaned = (rc_number or "").strip()
        if not fps_id or not cleaned:
            return None
        stmt = select(PdsRationCardMaster).where(
            PdsRationCardMaster.FpsRowID == fps_id,
            func.lower(PdsRationCardMaster.RcNumber) == cleaned.lower(),
        )
        return self.session.scalars(stmt).first()

    def get(self, model, row_id: int):
        self.ensure_schema()
        return self.session.get(model, row_id)

    def create(self, model, data: dict):
        self.ensure_schema()
        now = now_app().replace(tzinfo=None)
        data.setdefault("CreatedDate", now)
        data.setdefault("ModifiedDate", now)
        data.setdefault("ActiveStatus", True)
        row = model(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row, data: dict):
        preserve = {list(type(row).__mapper__.primary_key)[0].key, "CreatedDate", "CreatedBy"}
        for key, value in data.items():
            if key not in preserve:
                setattr(row, key, value)
        row.ModifiedDate = now_app().replace(tzinfo=None)
        self.session.flush()
        return row

    def delete(self, row) -> None:
        self.session.delete(row)
        self.session.flush()
