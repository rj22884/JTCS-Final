from __future__ import annotations

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.gst_billing import ItemMaster


class ItemMasterRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
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
                        UpdatedAt DATETIME2 NULL,
                        CONSTRAINT UX_ItemMaster_Code UNIQUE (ItemCode)
                    );
                END
                """
            )
        )
        self.session.commit()
        for col, ddl in (
            ("GstApplicable", "BIT NOT NULL CONSTRAINT DF_ItemMaster_GstApplicable DEFAULT (1)"),
            ("OpeningQty", "DECIMAL(18, 3) NOT NULL CONSTRAINT DF_ItemMaster_OpeningQty DEFAULT (0)"),
            ("OpeningRate", "DECIMAL(18, 2) NOT NULL CONSTRAINT DF_ItemMaster_OpeningRate DEFAULT (0)"),
            ("OpeningBalance", "DECIMAL(18, 2) NOT NULL CONSTRAINT DF_ItemMaster_OpeningBalance DEFAULT (0)"),
            ("OpeningBalanceDate", "DATE NULL"),
        ):
            self.session.execute(
                text(
                    f"""
                    IF COL_LENGTH(N'dbo.ItemMaster', N'{col}') IS NULL
                        ALTER TABLE dbo.ItemMaster ADD {col} {ddl};
                    """
                )
            )
            self.session.commit()
        self._schema_ready = True

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
