from __future__ import annotations

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.gst_billing import ItemMaster
from app.utils.db_session import commit_schema


class ItemMasterRepository:
    _schema_ready = False

    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def ensure_schema(self) -> None:
        if ItemMasterRepository._schema_ready:
            return
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.ItemMaster', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.ItemMaster (
                        ItemID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        ItemCode NVARCHAR(40) NOT NULL,
                        ItemName NVARCHAR(200) NOT NULL,
                        Description NVARCHAR(500) NULL,
                        HsnSac NVARCHAR(20) NULL,
                        HsnSacType NVARCHAR(10) NOT NULL CONSTRAINT DF_ItemMaster_HsnSacType DEFAULT (N'SAC'),
                        Unit NVARCHAR(30) NOT NULL CONSTRAINT DF_ItemMaster_Unit DEFAULT (N'NOS'),
                        DefaultRate DECIMAL(18, 2) NOT NULL CONSTRAINT DF_ItemMaster_DefaultRate DEFAULT (0),
                        GstApplicable BIT NOT NULL CONSTRAINT DF_ItemMaster_GstApplicable DEFAULT (1),
                        GstRatePercent DECIMAL(5, 2) NOT NULL CONSTRAINT DF_ItemMaster_GstRate DEFAULT (18),
                        OpeningQty DECIMAL(18, 3) NOT NULL CONSTRAINT DF_ItemMaster_OpeningQty DEFAULT (0),
                        OpeningRate DECIMAL(18, 2) NOT NULL CONSTRAINT DF_ItemMaster_OpeningRate DEFAULT (0),
                        OpeningBalance DECIMAL(18, 2) NOT NULL CONSTRAINT DF_ItemMaster_OpeningBalance DEFAULT (0),
                        OpeningBalanceDate DATE NULL,
                        OrderNo INT NOT NULL CONSTRAINT DF_ItemMaster_OrderNo DEFAULT (100),
                        IsActive BIT NOT NULL CONSTRAINT DF_ItemMaster_IsActive DEFAULT (1),
                        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_ItemMaster_CreatedAt DEFAULT (SYSUTCDATETIME()),
                        UpdatedAt DATETIME2 NULL
                    );
                END

                -- Item codes are labels and may repeat. Item names are unique
                -- after trimming and case normalization.
                IF EXISTS (
                    SELECT 1 FROM sys.key_constraints
                    WHERE parent_object_id = OBJECT_ID(N'dbo.ItemMaster')
                      AND name = N'UX_ItemMaster_Code'
                )
                    ALTER TABLE dbo.ItemMaster DROP CONSTRAINT UX_ItemMaster_Code;

                IF EXISTS (
                    SELECT 1 FROM sys.indexes
                    WHERE object_id = OBJECT_ID(N'dbo.ItemMaster')
                      AND name = N'UX_ItemMaster_Code'
                      AND is_unique_constraint = 0
                )
                    DROP INDEX UX_ItemMaster_Code ON dbo.ItemMaster;

                IF COL_LENGTH(N'dbo.ItemMaster', N'ItemNameNormalized') IS NULL
                    ALTER TABLE dbo.ItemMaster
                    ADD ItemNameNormalized AS LOWER(LTRIM(RTRIM(ItemName))) PERSISTED;
                """
            )
        )
        commit_schema(self.session)
        self.session.execute(
            text(
                """
                IF NOT EXISTS (
                    SELECT 1 FROM sys.indexes
                    WHERE object_id = OBJECT_ID(N'dbo.ItemMaster')
                      AND name = N'UX_ItemMaster_Name'
                )
                   AND NOT EXISTS (
                    SELECT ItemNameNormalized
                    FROM dbo.ItemMaster
                    GROUP BY ItemNameNormalized
                    HAVING COUNT(*) > 1
                )
                    CREATE UNIQUE INDEX UX_ItemMaster_Name
                    ON dbo.ItemMaster (ItemNameNormalized);
                """
            )
        )
        commit_schema(self.session)
        for col, ddl in (
            ("GstApplicable", "BIT NOT NULL CONSTRAINT DF_ItemMaster_GstApplicable DEFAULT (1)"),
            ("OpeningQty", "DECIMAL(18, 3) NOT NULL CONSTRAINT DF_ItemMaster_OpeningQty DEFAULT (0)"),
            ("OpeningRate", "DECIMAL(18, 2) NOT NULL CONSTRAINT DF_ItemMaster_OpeningRate DEFAULT (0)"),
            ("OpeningBalance", "DECIMAL(18, 2) NOT NULL CONSTRAINT DF_ItemMaster_OpeningBalance DEFAULT (0)"),
            ("OpeningBalanceDate", "DATE NULL"),
            ("PurchaseDate", "DATE NULL"),
            ("DepreciationRate", "DECIMAL(9, 4) NOT NULL CONSTRAINT DF_ItemMaster_DepreciationRate DEFAULT (0)"),
            ("AppreciationRate", "DECIMAL(9, 4) NOT NULL CONSTRAINT DF_ItemMaster_AppreciationRate DEFAULT (0)"),
            ("ChartGroupID", "INT NULL"),
        ):
            self.session.execute(
                text(
                    f"""
                    IF COL_LENGTH(N'dbo.ItemMaster', N'{col}') IS NULL
                        ALTER TABLE dbo.ItemMaster ADD {col} {ddl};
                    """
                )
            )
            commit_schema(self.session)
        # Optional FK to Chart of Group Master (same pattern as WorkMaster / Bank).
        self.session.execute(
            text(
                """
                IF COL_LENGTH(N'dbo.ItemMaster', N'ChartGroupID') IS NOT NULL
                   AND OBJECT_ID(N'dbo.ChartOfGroupMaster', N'U') IS NOT NULL
                   AND NOT EXISTS (
                        SELECT 1
                        FROM sys.foreign_keys
                        WHERE name = N'FK_ItemMaster_ChartGroup'
                   )
                BEGIN
                    ALTER TABLE dbo.ItemMaster
                    ADD CONSTRAINT FK_ItemMaster_ChartGroup
                    FOREIGN KEY (ChartGroupID)
                    REFERENCES dbo.ChartOfGroupMaster (GroupID);
                END
                """
            )
        )
        commit_schema(self.session)
        ItemMasterRepository._schema_ready = True

    def list_all(self, *, search: str | None = None, active_only: bool = False) -> list[ItemMaster]:
        self.ensure_schema()
        stmt = select(ItemMaster)
        if active_only:
            stmt = stmt.where(ItemMaster.IsActive == True)  # noqa: E712
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    ItemMaster.ItemCode.like(term),
                    ItemMaster.ItemName.like(term),
                    ItemMaster.HsnSac.like(term),
                    ItemMaster.Description.like(term),
                )
            )
        stmt = stmt.order_by(ItemMaster.OrderNo.asc(), ItemMaster.ItemName.asc())
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, item_id: int) -> ItemMaster | None:
        self.ensure_schema()
        return self.session.get(ItemMaster, item_id)

    def find_by_code(self, code: str) -> ItemMaster | None:
        self.ensure_schema()
        stmt = select(ItemMaster).where(ItemMaster.ItemCode == code.strip())
        return self.session.scalars(stmt).first()

    def find_by_name(self, name: str, *, exclude_id: int | None = None) -> ItemMaster | None:
        self.ensure_schema()
        normalized = name.strip().lower()
        stmt = select(ItemMaster).where(
            func.lower(func.ltrim(func.rtrim(ItemMaster.ItemName))) == normalized
        )
        if exclude_id is not None:
            stmt = stmt.where(ItemMaster.ItemID != exclude_id)
        return self.session.scalars(stmt).first()

    def create(self, data: dict) -> ItemMaster:
        self.ensure_schema()
        row = ItemMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: ItemMaster, data: dict) -> ItemMaster:
        for key, value in data.items():
            setattr(row, key, value)
        self.session.flush()
        return row

    def delete(self, row: ItemMaster) -> None:
        self.session.delete(row)
        self.session.flush()
