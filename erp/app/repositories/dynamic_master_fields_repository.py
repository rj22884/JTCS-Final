from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.extensions import db


class DynamicMasterFieldsRepository:
    _schema_ready = False

    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def ensure_schema(self) -> None:
        if DynamicMasterFieldsRepository._schema_ready:
            return
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.DynMasterFieldDef', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.DynMasterFieldDef (
                        FieldKey    NVARCHAR(80)  NOT NULL PRIMARY KEY,
                        Label       NVARCHAR(150) NOT NULL,
                        FieldType   NVARCHAR(20)  NOT NULL,
                        Source      NVARCHAR(20)  NOT NULL
                            CONSTRAINT DF_DynMasterFieldDef_Source DEFAULT (N'custom'),
                        Hint        NVARCHAR(400) NULL,
                        IsActive    BIT NOT NULL
                            CONSTRAINT DF_DynMasterFieldDef_IsActive DEFAULT (1),
                        CreatedDate DATETIME2 NOT NULL
                            CONSTRAINT DF_DynMasterFieldDef_Created DEFAULT (SYSUTCDATETIME()),
                        UpdatedDate DATETIME2 NULL
                    );
                END
                """
            )
        )
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.DynMasterFieldGroupMap', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.DynMasterFieldGroupMap (
                        GroupID      INT NOT NULL,
                        FieldKey     NVARCHAR(80) NOT NULL,
                        IsRequired   BIT NOT NULL
                            CONSTRAINT DF_DynMasterFieldGroupMap_Req DEFAULT (0),
                        DisplayOrder INT NOT NULL
                            CONSTRAINT DF_DynMasterFieldGroupMap_Ord DEFAULT (100),
                        CONSTRAINT PK_DynMasterFieldGroupMap PRIMARY KEY (GroupID, FieldKey)
                    );
                END
                """
            )
        )
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.ChartOfGroupMaster', N'U') IS NOT NULL
                   AND OBJECT_ID(N'dbo.DynMasterFieldGroupMap', N'U') IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM sys.foreign_keys
                       WHERE name = N'FK_DynMasterFieldGroupMap_Group'
                   )
                    ALTER TABLE dbo.DynMasterFieldGroupMap
                        ADD CONSTRAINT FK_DynMasterFieldGroupMap_Group
                        FOREIGN KEY (GroupID) REFERENCES dbo.ChartOfGroupMaster (GroupID)
                        ON DELETE CASCADE;
                """
            )
        )
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.CustomerDynFieldValue', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.CustomerDynFieldValue (
                        CustomerID INT NOT NULL,
                        FieldKey   NVARCHAR(80) NOT NULL,
                        FieldValue NVARCHAR(MAX) NULL,
                        CONSTRAINT PK_CustomerDynFieldValue PRIMARY KEY (CustomerID, FieldKey)
                    );
                END
                """
            )
        )
        self.session.commit()
        DynamicMasterFieldsRepository._schema_ready = True

    def list_custom_fields(self, *, active_only: bool = True) -> list[dict]:
        self.ensure_schema()
        sql = """
            SELECT FieldKey, Label, FieldType, Source, Hint, IsActive
            FROM dbo.DynMasterFieldDef
        """
        if active_only:
            sql += " WHERE IsActive = 1"
        sql += " ORDER BY Label, FieldKey"
        return [dict(r) for r in self.session.execute(text(sql)).mappings().all()]

    def get_custom_field(self, field_key: str) -> dict | None:
        self.ensure_schema()
        row = self.session.execute(
            text(
                """
                SELECT FieldKey, Label, FieldType, Source, Hint, IsActive
                FROM dbo.DynMasterFieldDef
                WHERE FieldKey = :key
                """
            ),
            {"key": field_key},
        ).mappings().first()
        return dict(row) if row else None

    def create_custom_field(self, data: dict) -> dict:
        self.ensure_schema()
        self.session.execute(
            text(
                """
                INSERT INTO dbo.DynMasterFieldDef (FieldKey, Label, FieldType, Source, Hint, IsActive)
                VALUES (:key, :label, :type, N'custom', :hint, 1)
                """
            ),
            data,
        )
        self.session.flush()
        return self.get_custom_field(data["key"]) or data

    def update_custom_field(self, field_key: str, data: dict) -> dict:
        self.ensure_schema()
        self.session.execute(
            text(
                """
                UPDATE dbo.DynMasterFieldDef
                SET Label = :label,
                    FieldType = :type,
                    Hint = :hint,
                    UpdatedDate = SYSUTCDATETIME()
                WHERE FieldKey = :key AND Source = N'custom'
                """
            ),
            {**data, "key": field_key},
        )
        self.session.flush()
        row = self.get_custom_field(field_key)
        if row is None:
            raise ValueError("Custom field not found.")
        return row

    def delete_custom_field(self, field_key: str) -> None:
        self.ensure_schema()
        self.session.execute(
            text("DELETE FROM dbo.DynMasterFieldGroupMap WHERE FieldKey = :key"),
            {"key": field_key},
        )
        self.session.execute(
            text("DELETE FROM dbo.CustomerDynFieldValue WHERE FieldKey = :key"),
            {"key": field_key},
        )
        self.session.execute(
            text(
                "DELETE FROM dbo.DynMasterFieldDef WHERE FieldKey = :key AND Source = N'custom'"
            ),
            {"key": field_key},
        )
        self.session.flush()

    def configured_group_ids(self) -> set[int]:
        self.ensure_schema()
        rows = self.session.execute(
            text("SELECT DISTINCT GroupID FROM dbo.DynMasterFieldGroupMap")
        ).all()
        return {int(r[0]) for r in rows}

    def list_group_fields(self, group_id: int) -> list[dict]:
        self.ensure_schema()
        rows = self.session.execute(
            text(
                """
                SELECT FieldKey, IsRequired, DisplayOrder
                FROM dbo.DynMasterFieldGroupMap
                WHERE GroupID = :gid
                ORDER BY DisplayOrder, FieldKey
                """
            ),
            {"gid": int(group_id)},
        ).mappings().all()
        return [dict(r) for r in rows]

    def list_all_group_fields(self) -> list[dict]:
        self.ensure_schema()
        rows = self.session.execute(
            text(
                """
                SELECT GroupID, FieldKey, IsRequired, DisplayOrder
                FROM dbo.DynMasterFieldGroupMap
                ORDER BY GroupID, DisplayOrder, FieldKey
                """
            )
        ).mappings().all()
        return [dict(r) for r in rows]

    def replace_group_fields(self, group_id: int, fields: list[dict]) -> None:
        self.ensure_schema()
        self.session.execute(
            text("DELETE FROM dbo.DynMasterFieldGroupMap WHERE GroupID = :gid"),
            {"gid": int(group_id)},
        )
        for idx, item in enumerate(fields):
            self.session.execute(
                text(
                    """
                    INSERT INTO dbo.DynMasterFieldGroupMap
                        (GroupID, FieldKey, IsRequired, DisplayOrder)
                    VALUES (:gid, :key, :req, :ord)
                    """
                ),
                {
                    "gid": int(group_id),
                    "key": item["key"],
                    "req": 1 if item.get("required") else 0,
                    "ord": int(item.get("order") or (idx + 1) * 10),
                },
            )
        self.session.flush()

    def get_customer_values(self, customer_id: int) -> dict[str, str]:
        self.ensure_schema()
        rows = self.session.execute(
            text(
                """
                SELECT FieldKey, FieldValue
                FROM dbo.CustomerDynFieldValue
                WHERE CustomerID = :cid
                """
            ),
            {"cid": int(customer_id)},
        ).mappings().all()
        return {str(r["FieldKey"]): (r["FieldValue"] or "") for r in rows}

    def replace_customer_values(self, customer_id: int, values: dict[str, str]) -> None:
        self.ensure_schema()
        self.session.execute(
            text("DELETE FROM dbo.CustomerDynFieldValue WHERE CustomerID = :cid"),
            {"cid": int(customer_id)},
        )
        for key, value in values.items():
            if not key:
                continue
            self.session.execute(
                text(
                    """
                    INSERT INTO dbo.CustomerDynFieldValue (CustomerID, FieldKey, FieldValue)
                    VALUES (:cid, :key, :val)
                    """
                ),
                {"cid": int(customer_id), "key": str(key)[:80], "val": value},
            )
        self.session.flush()
