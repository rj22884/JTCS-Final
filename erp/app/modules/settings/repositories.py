"""Repository for dbo.IntegrationSettings."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.extensions import db

_SCHEMA_READY = False
_AUDIT_SCHEMA_READY = False


class IntegrationSettingsRepository:
    def ensure_schema(self) -> None:
        global _SCHEMA_READY
        if _SCHEMA_READY:
            return
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.IntegrationSettings', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.IntegrationSettings (
                        SettingID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        Provider NVARCHAR(50) NOT NULL,
                        SettingKey NVARCHAR(100) NOT NULL,
                        SettingValueEncrypted NVARCHAR(MAX) NULL,
                        Description NVARCHAR(300) NULL,
                        IsActive BIT NOT NULL CONSTRAINT DF_IntegrationSettings_IsActive DEFAULT (1),
                        CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_IntegrationSettings_CreatedOn DEFAULT (SYSUTCDATETIME()),
                        ModifiedOn DATETIME2 NULL,
                        CONSTRAINT UX_IntegrationSettings_ProviderKey UNIQUE (Provider, SettingKey)
                    );
                    CREATE INDEX IX_IntegrationSettings_Provider
                        ON dbo.IntegrationSettings (Provider, IsActive);
                END;
                """
            )
        )
        db.session.commit()
        _SCHEMA_READY = True

    def ensure_audit_schema(self) -> None:
        global _AUDIT_SCHEMA_READY
        if _AUDIT_SCHEMA_READY:
            return
        self.ensure_schema()
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.IntegrationSettingsAudit', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.IntegrationSettingsAudit (
                        AuditID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        Provider NVARCHAR(50) NOT NULL,
                        SettingKey NVARCHAR(100) NOT NULL,
                        OldValueMasked NVARCHAR(MAX) NULL,
                        NewValueMasked NVARCHAR(MAX) NULL,
                        ChangedByUserID INT NULL,
                        ChangedByUserName NVARCHAR(150) NULL,
                        IPAddress NVARCHAR(64) NULL,
                        Browser NVARCHAR(500) NULL,
                        CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_IntegrationSettingsAudit_CreatedOn DEFAULT (SYSUTCDATETIME())
                    );
                    CREATE INDEX IX_IntegrationSettingsAudit_Provider
                        ON dbo.IntegrationSettingsAudit (Provider, CreatedOn DESC);
                END;
                """
            )
        )
        db.session.commit()
        _AUDIT_SCHEMA_READY = True

    def ensure_menu(self) -> None:
        """Insert Admin Role → Integration Settings if missing (does not alter other menus)."""
        row = db.session.execute(
            text(
                """
                SELECT TOP 1 MenuID
                FROM dbo.MenuMaster
                WHERE MenuName = N'Admin Role' AND ParentMenuID IS NULL
                ORDER BY MenuID
                """
            )
        ).first()
        if not row:
            return
        parent_id = int(row[0])
        exists = db.session.execute(
            text(
                """
                SELECT TOP 1 MenuID
                FROM dbo.MenuMaster
                WHERE ParentMenuID = :parent AND MenuName = N'Integration Settings'
                """
            ),
            {"parent": parent_id},
        ).first()
        if exists:
            return
        db.session.execute(
            text(
                """
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    :parent, N'Integration Settings', N'bi-plugin', N'/admin/integrations', 4,
                    N'External API credentials and integration configuration',
                    1, N'Administrator,Admin'
                )
                """
            ),
            {"parent": parent_id},
        )
        db.session.commit()

    def list_by_provider(self, provider: str) -> list[dict]:
        self.ensure_schema()
        rows = db.session.execute(
            text(
                """
                SELECT SettingID, Provider, SettingKey, SettingValueEncrypted,
                       Description, IsActive, CreatedOn, ModifiedOn
                FROM dbo.IntegrationSettings
                WHERE Provider = :provider AND IsActive = 1
                ORDER BY SettingKey
                """
            ),
            {"provider": provider},
        ).mappings().all()
        return [dict(r) for r in rows]

    def list_all_active(self) -> list[dict]:
        self.ensure_schema()
        rows = db.session.execute(
            text(
                """
                SELECT SettingID, Provider, SettingKey, SettingValueEncrypted,
                       Description, IsActive, CreatedOn, ModifiedOn
                FROM dbo.IntegrationSettings
                WHERE IsActive = 1
                ORDER BY Provider, SettingKey
                """
            )
        ).mappings().all()
        return [dict(r) for r in rows]

    def upsert(
        self,
        *,
        provider: str,
        setting_key: str,
        value_encrypted: str | None,
        description: str | None = None,
    ) -> None:
        self.ensure_schema()
        now = datetime.utcnow()
        existing = db.session.execute(
            text(
                """
                SELECT TOP 1 SettingID
                FROM dbo.IntegrationSettings
                WHERE Provider = :provider AND SettingKey = :key
                """
            ),
            {"provider": provider, "key": setting_key},
        ).scalar()
        if existing:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.IntegrationSettings
                    SET SettingValueEncrypted = :value,
                        Description = COALESCE(:description, Description),
                        IsActive = 1,
                        ModifiedOn = :now
                    WHERE SettingID = :id
                    """
                ),
                {
                    "value": value_encrypted,
                    "description": description,
                    "now": now,
                    "id": int(existing),
                },
            )
        else:
            db.session.execute(
                text(
                    """
                    INSERT INTO dbo.IntegrationSettings
                        (Provider, SettingKey, SettingValueEncrypted, Description, IsActive, CreatedOn)
                    VALUES
                        (:provider, :key, :value, :description, 1, :now)
                    """
                ),
                {
                    "provider": provider[:50],
                    "key": setting_key[:100],
                    "value": value_encrypted,
                    "description": (description or "")[:300] or None,
                    "now": now,
                },
            )
        db.session.commit()

    def get_encrypted_value(self, provider: str, setting_key: str) -> str | None:
        self.ensure_schema()
        return db.session.execute(
            text(
                """
                SELECT TOP 1 SettingValueEncrypted
                FROM dbo.IntegrationSettings
                WHERE Provider = :provider AND SettingKey = :key AND IsActive = 1
                """
            ),
            {"provider": provider, "key": setting_key},
        ).scalar()
