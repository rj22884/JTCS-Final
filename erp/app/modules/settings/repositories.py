"""Repository for dbo.IntegrationSettings."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.extensions import db

_SCHEMA_READY = False
_AUDIT_SCHEMA_READY = False
_HEALTH_SCHEMA_READY = False


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

    def ensure_health_schema(self) -> None:
        """Health check history + alerts — does not duplicate IntegrationSettings."""
        global _HEALTH_SCHEMA_READY
        if _HEALTH_SCHEMA_READY:
            return
        self.ensure_schema()
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.IntegrationHealthCheck', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.IntegrationHealthCheck (
                        HealthCheckID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        Provider NVARCHAR(50) NOT NULL,
                        StatusCode NVARCHAR(40) NOT NULL,
                        HealthScore INT NOT NULL CONSTRAINT DF_IHC_Score DEFAULT (0),
                        StatusLabel NVARCHAR(80) NULL,
                        TokenStatus NVARCHAR(40) NULL,
                        WebhookStatus NVARCHAR(40) NULL,
                        ApiVersion NVARCHAR(40) NULL,
                        AvgResponseMs INT NULL,
                        LastError NVARCHAR(1000) NULL,
                        DetailsJson NVARCHAR(MAX) NULL,
                        CheckedOn DATETIME2 NOT NULL CONSTRAINT DF_IHC_CheckedOn DEFAULT (SYSUTCDATETIME()),
                        CheckedByUserID INT NULL
                    );
                    CREATE INDEX IX_IHC_Provider ON dbo.IntegrationHealthCheck (Provider, CheckedOn DESC);
                END;

                IF OBJECT_ID(N'dbo.IntegrationHealthAlert', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.IntegrationHealthAlert (
                        AlertID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        Provider NVARCHAR(50) NOT NULL,
                        AlertType NVARCHAR(60) NOT NULL,
                        Severity NVARCHAR(20) NOT NULL CONSTRAINT DF_IHA_Severity DEFAULT (N'Warning'),
                        Title NVARCHAR(255) NOT NULL,
                        Message NVARCHAR(1000) NULL,
                        IsResolved BIT NOT NULL CONSTRAINT DF_IHA_Resolved DEFAULT (0),
                        CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_IHA_CreatedOn DEFAULT (SYSUTCDATETIME()),
                        ResolvedOn DATETIME2 NULL
                    );
                    CREATE INDEX IX_IHA_Open ON dbo.IntegrationHealthAlert (IsResolved, CreatedOn DESC);
                END;
                """
            )
        )
        db.session.commit()
        _HEALTH_SCHEMA_READY = True

    def insert_health_check(
        self,
        *,
        provider: str,
        status_code: str,
        health_score: int,
        status_label: str | None,
        token_status: str | None,
        webhook_status: str | None,
        api_version: str | None,
        avg_response_ms: int | None,
        last_error: str | None,
        details_json: str | None,
        user_id: int | None,
    ) -> int:
        self.ensure_health_schema()
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.IntegrationHealthCheck
                    (Provider, StatusCode, HealthScore, StatusLabel, TokenStatus, WebhookStatus,
                     ApiVersion, AvgResponseMs, LastError, DetailsJson, CheckedByUserID)
                OUTPUT INSERTED.HealthCheckID
                VALUES
                    (:provider, :status_code, :score, :label, :token_status, :webhook_status,
                     :api_version, :avg_ms, :last_error, :details, :uid)
                """
            ),
            {
                "provider": provider[:50],
                "status_code": status_code[:40],
                "score": max(0, min(100, int(health_score))),
                "label": (status_label or "")[:80] or None,
                "token_status": (token_status or "")[:40] or None,
                "webhook_status": (webhook_status or "")[:40] or None,
                "api_version": (api_version or "")[:40] or None,
                "avg_ms": avg_response_ms,
                "last_error": (last_error or "")[:1000] or None,
                "details": details_json,
                "uid": user_id,
            },
        ).first()
        db.session.commit()
        return int(row[0]) if row else 0

    def latest_health_by_provider(self) -> dict[str, dict]:
        self.ensure_health_schema()
        rows = db.session.execute(
            text(
                """
                SELECT h.*
                FROM dbo.IntegrationHealthCheck h
                INNER JOIN (
                    SELECT Provider, MAX(HealthCheckID) AS MaxID
                    FROM dbo.IntegrationHealthCheck
                    GROUP BY Provider
                ) x ON x.MaxID = h.HealthCheckID
                """
            )
        ).mappings().all()
        return {str(r["Provider"]): dict(r) for r in rows}

    def list_health_history(self, provider: str | None = None, limit: int = 50) -> list[dict]:
        self.ensure_health_schema()
        limit = min(max(1, limit), 200)
        if provider:
            rows = db.session.execute(
                text(
                    """
                    SELECT TOP (:limit) *
                    FROM dbo.IntegrationHealthCheck
                    WHERE Provider = :provider
                    ORDER BY CheckedOn DESC, HealthCheckID DESC
                    """
                ),
                {"provider": provider, "limit": limit},
            ).mappings().all()
        else:
            rows = db.session.execute(
                text(
                    """
                    SELECT TOP (:limit) *
                    FROM dbo.IntegrationHealthCheck
                    ORDER BY CheckedOn DESC, HealthCheckID DESC
                    """
                ),
                {"limit": limit},
            ).mappings().all()
        return [dict(r) for r in rows]

    def upsert_open_alert(
        self,
        *,
        provider: str,
        alert_type: str,
        severity: str,
        title: str,
        message: str | None,
    ) -> None:
        self.ensure_health_schema()
        existing = db.session.execute(
            text(
                """
                SELECT TOP 1 AlertID FROM dbo.IntegrationHealthAlert
                WHERE Provider = :provider AND AlertType = :atype AND IsResolved = 0
                """
            ),
            {"provider": provider, "atype": alert_type},
        ).scalar()
        if existing:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.IntegrationHealthAlert
                    SET Severity = :sev, Title = :title, Message = :msg
                    WHERE AlertID = :id
                    """
                ),
                {
                    "sev": severity[:20],
                    "title": title[:255],
                    "msg": (message or "")[:1000] or None,
                    "id": int(existing),
                },
            )
        else:
            db.session.execute(
                text(
                    """
                    INSERT INTO dbo.IntegrationHealthAlert
                        (Provider, AlertType, Severity, Title, Message)
                    VALUES (:provider, :atype, :sev, :title, :msg)
                    """
                ),
                {
                    "provider": provider[:50],
                    "atype": alert_type[:60],
                    "sev": severity[:20],
                    "title": title[:255],
                    "msg": (message or "")[:1000] or None,
                },
            )
        db.session.commit()

    def resolve_alerts(self, provider: str, alert_type: str | None = None) -> None:
        self.ensure_health_schema()
        if alert_type:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.IntegrationHealthAlert
                    SET IsResolved = 1, ResolvedOn = SYSUTCDATETIME()
                    WHERE Provider = :provider AND AlertType = :atype AND IsResolved = 0
                    """
                ),
                {"provider": provider, "atype": alert_type},
            )
        else:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.IntegrationHealthAlert
                    SET IsResolved = 1, ResolvedOn = SYSUTCDATETIME()
                    WHERE Provider = :provider AND IsResolved = 0
                    """
                ),
                {"provider": provider},
            )
        db.session.commit()

    def list_open_alerts(self, limit: int = 40) -> list[dict]:
        self.ensure_health_schema()
        rows = db.session.execute(
            text(
                """
                SELECT TOP (:limit) *
                FROM dbo.IntegrationHealthAlert
                WHERE IsResolved = 0
                ORDER BY CreatedOn DESC
                """
            ),
            {"limit": min(max(1, limit), 100)},
        ).mappings().all()
        return [dict(r) for r in rows]

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
