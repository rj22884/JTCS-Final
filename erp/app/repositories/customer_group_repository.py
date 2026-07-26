from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.customer_group import CustomerGroupMaster


class CustomerGroupRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.CustomerGroupMaster', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.CustomerGroupMaster (
                        GroupID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        GroupCode NVARCHAR(20) NOT NULL,
                        GroupName NVARCHAR(100) NOT NULL,
                        TabCodes NVARCHAR(500) NOT NULL,
                        DisplayOrder INT NOT NULL
                            CONSTRAINT DF_CustomerGroupMaster_DisplayOrder DEFAULT (1),
                        ActiveStatus BIT NOT NULL
                            CONSTRAINT DF_CustomerGroupMaster_ActiveStatus DEFAULT (1),
                        CreatedDate DATETIME2 NOT NULL
                            CONSTRAINT DF_CustomerGroupMaster_CreatedDate DEFAULT (SYSUTCDATETIME()),
                        CONSTRAINT UX_CustomerGroupMaster_GroupCode UNIQUE (GroupCode)
                    );
                END
                """
            )
        )
        self.session.execute(
            text(
                """
                MERGE dbo.CustomerGroupMaster AS t
                USING (
                    VALUES
                        (N'ITR', N'ITR', N'basic,contact,address,itr,bank,social', 1),
                        (N'TDS', N'TDS', N'basic,contact,address,tds,compliance,bank', 2),
                        (N'GST', N'GST', N'basic,contact,address,gst,business,bank', 3),
                        (N'DSC', N'DSC', N'basic,contact,address,dsc,bank', 4)
                ) AS s (GroupCode, GroupName, TabCodes, DisplayOrder)
                ON t.GroupCode = s.GroupCode
                WHEN NOT MATCHED THEN
                    INSERT (GroupCode, GroupName, TabCodes, DisplayOrder)
                    VALUES (s.GroupCode, s.GroupName, s.TabCodes, s.DisplayOrder)
                WHEN MATCHED THEN
                    UPDATE SET
                        GroupName = s.GroupName,
                        TabCodes = s.TabCodes,
                        DisplayOrder = s.DisplayOrder;
                """
            )
        )
        self.session.flush()
        self._ensure_menu_entry()
        self._schema_ready = True

    def _ensure_menu_entry(self) -> None:
        self.session.execute(
            text(
                """
                DECLARE @MastersID INT = (
                    SELECT TOP 1 MenuID FROM dbo.MenuMaster
                    WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
                );
                IF @MastersID IS NOT NULL
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM dbo.MenuMaster
                        WHERE MenuName IN (N'Group Master', N'Customer Group Master')
                          AND ParentMenuID = @MastersID
                    )
                        UPDATE dbo.MenuMaster
                        SET MenuName = N'Customer Group Master',
                            MenuIcon = N'bi-collection',
                            MenuURL = N'/masters/group',
                            IsActive = 1,
                            Description = N'Customer group master for Customer Master tabs'
                        WHERE ParentMenuID = @MastersID
                          AND MenuName IN (N'Group Master', N'Customer Group Master');
                    ELSE
                        INSERT INTO dbo.MenuMaster (
                            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive
                        )
                        VALUES (
                            @MastersID, N'Customer Group Master', N'bi-collection', N'/masters/group',
                            4, N'Customer group master for Customer Master tabs', 1
                        );
                END
                """
            )
        )

    @staticmethod
    def _row_dict(row: CustomerGroupMaster) -> dict:
        tabs = [part.strip() for part in (row.TabCodes or "").split(",") if part.strip()]
        return {
            "group_id": row.GroupID,
            "group_code": row.GroupCode,
            "group_name": row.GroupName,
            "tab_codes": tabs,
            "tab_codes_raw": row.TabCodes,
            "display_order": row.DisplayOrder,
            "active_status": bool(row.ActiveStatus),
        }

    def list_all(self, *, active_only: bool = False) -> list[CustomerGroupMaster]:
        self.ensure_schema()
        stmt = select(CustomerGroupMaster)
        if active_only:
            stmt = stmt.where(CustomerGroupMaster.ActiveStatus == True)  # noqa: E712
        stmt = stmt.order_by(CustomerGroupMaster.DisplayOrder, CustomerGroupMaster.GroupID)
        return list(self.session.scalars(stmt).all())

    def list_dicts(self, *, active_only: bool = False) -> list[dict]:
        return [self._row_dict(row) for row in self.list_all(active_only=active_only)]

    def get_by_id(self, group_id: int) -> CustomerGroupMaster | None:
        self.ensure_schema()
        return self.session.get(CustomerGroupMaster, group_id)

    def get_by_code(self, group_code: str) -> CustomerGroupMaster | None:
        self.ensure_schema()
        code = (group_code or "").strip().upper()
        if not code:
            return None
        stmt = select(CustomerGroupMaster).where(CustomerGroupMaster.GroupCode == code)
        return self.session.scalars(stmt).first()

    def create(self, data: dict) -> CustomerGroupMaster:
        row = CustomerGroupMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: CustomerGroupMaster, data: dict) -> CustomerGroupMaster:
        for key, value in data.items():
            setattr(row, key, value)
        self.session.flush()
        return row

    def deactivate(self, row: CustomerGroupMaster) -> CustomerGroupMaster:
        row.ActiveStatus = False
        self.session.flush()
        return row

    def activate(self, row: CustomerGroupMaster) -> CustomerGroupMaster:
        row.ActiveStatus = True
        self.session.flush()
        return row
