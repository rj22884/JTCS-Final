"""SQL Server persistence for System Health scans, alerts, and metric samples."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.extensions import db

_SCHEMA_READY = False


class SystemHealthRepository:
    """Own tables only — does not duplicate IntegrationSettings / Backup tables."""

    def ensure_schema(self) -> None:
        global _SCHEMA_READY
        if _SCHEMA_READY:
            return
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.SystemHealthScan', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.SystemHealthScan (
                        ScanID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        OverallScore INT NOT NULL CONSTRAINT DF_SHS_Score DEFAULT (0),
                        StatusLabel NVARCHAR(40) NULL,
                        SummaryJson NVARCHAR(MAX) NULL,
                        DetailsJson NVARCHAR(MAX) NULL,
                        ScannedOn DATETIME2 NOT NULL CONSTRAINT DF_SHS_On DEFAULT (SYSUTCDATETIME()),
                        ScannedByUserID INT NULL
                    );
                    CREATE INDEX IX_SHS_ScannedOn ON dbo.SystemHealthScan (ScannedOn DESC);
                END;

                IF OBJECT_ID(N'dbo.SystemHealthAlert', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.SystemHealthAlert (
                        AlertID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        AlertType NVARCHAR(60) NOT NULL,
                        Severity NVARCHAR(20) NOT NULL CONSTRAINT DF_SHA_Sev DEFAULT (N'Warning'),
                        Title NVARCHAR(255) NOT NULL,
                        Message NVARCHAR(1000) NULL,
                        IsResolved BIT NOT NULL CONSTRAINT DF_SHA_Res DEFAULT (0),
                        CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_SHA_On DEFAULT (SYSUTCDATETIME()),
                        ResolvedOn DATETIME2 NULL
                    );
                    CREATE INDEX IX_SHA_Open ON dbo.SystemHealthAlert (IsResolved, CreatedOn DESC);
                END;

                IF OBJECT_ID(N'dbo.SystemHealthMetric', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.SystemHealthMetric (
                        MetricID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        MetricKey NVARCHAR(40) NOT NULL,
                        MetricValue FLOAT NOT NULL,
                        SampledOn DATETIME2 NOT NULL CONSTRAINT DF_SHM_On DEFAULT (SYSUTCDATETIME())
                    );
                    CREATE INDEX IX_SHM_KeyOn ON dbo.SystemHealthMetric (MetricKey, SampledOn DESC);
                END;
                """
            )
        )
        db.session.commit()
        _SCHEMA_READY = True

    def insert_scan(
        self,
        *,
        overall_score: int,
        status_label: str,
        summary: dict[str, Any],
        details: dict[str, Any],
        user_id: int | None,
    ) -> int:
        self.ensure_schema()
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.SystemHealthScan
                    (OverallScore, StatusLabel, SummaryJson, DetailsJson, ScannedByUserID)
                OUTPUT INSERTED.ScanID
                VALUES (:score, :label, :summary, :details, :uid)
                """
            ),
            {
                "score": max(0, min(100, int(overall_score))),
                "label": (status_label or "")[:40] or None,
                "summary": json.dumps(summary, default=str),
                "details": json.dumps(details, default=str),
                "uid": user_id,
            },
        ).first()
        db.session.commit()
        return int(row[0]) if row else 0

    def latest_scan(self) -> dict | None:
        self.ensure_schema()
        row = db.session.execute(
            text(
                """
                SELECT TOP 1 *
                FROM dbo.SystemHealthScan
                ORDER BY ScannedOn DESC, ScanID DESC
                """
            )
        ).mappings().first()
        return dict(row) if row else None

    def insert_metrics(self, samples: list[tuple[str, float]]) -> None:
        self.ensure_schema()
        for key, value in samples:
            db.session.execute(
                text(
                    """
                    INSERT INTO dbo.SystemHealthMetric (MetricKey, MetricValue)
                    VALUES (:k, :v)
                    """
                ),
                {"k": key[:40], "v": float(value)},
            )
        db.session.commit()
        # Keep last ~2000 rows
        db.session.execute(
            text(
                """
                ;WITH cte AS (
                    SELECT MetricID,
                           ROW_NUMBER() OVER (PARTITION BY MetricKey ORDER BY SampledOn DESC) AS rn
                    FROM dbo.SystemHealthMetric
                )
                DELETE FROM cte WHERE rn > 200
                """
            )
        )
        db.session.commit()

    def metric_series(self, key: str, limit: int = 60) -> list[dict]:
        self.ensure_schema()
        rows = db.session.execute(
            text(
                """
                SELECT TOP (:limit) MetricValue, SampledOn
                FROM dbo.SystemHealthMetric
                WHERE MetricKey = :k
                ORDER BY SampledOn DESC
                """
            ),
            {"k": key, "limit": min(max(1, limit), 200)},
        ).mappings().all()
        return [dict(r) for r in reversed(rows)]

    def upsert_alert(
        self,
        *,
        alert_type: str,
        severity: str,
        title: str,
        message: str | None,
    ) -> None:
        self.ensure_schema()
        existing = db.session.execute(
            text(
                """
                SELECT TOP 1 AlertID FROM dbo.SystemHealthAlert
                WHERE AlertType = :t AND IsResolved = 0
                """
            ),
            {"t": alert_type},
        ).scalar()
        if existing:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.SystemHealthAlert
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
                    INSERT INTO dbo.SystemHealthAlert (AlertType, Severity, Title, Message)
                    VALUES (:t, :sev, :title, :msg)
                    """
                ),
                {
                    "t": alert_type[:60],
                    "sev": severity[:20],
                    "title": title[:255],
                    "msg": (message or "")[:1000] or None,
                },
            )
        db.session.commit()

    def resolve_alert(self, alert_type: str) -> None:
        self.ensure_schema()
        db.session.execute(
            text(
                """
                UPDATE dbo.SystemHealthAlert
                SET IsResolved = 1, ResolvedOn = SYSUTCDATETIME()
                WHERE AlertType = :t AND IsResolved = 0
                """
            ),
            {"t": alert_type},
        )
        db.session.commit()

    def list_open_alerts(self, limit: int = 40) -> list[dict]:
        self.ensure_schema()
        rows = db.session.execute(
            text(
                """
                SELECT TOP (:limit) *
                FROM dbo.SystemHealthAlert
                WHERE IsResolved = 0
                ORDER BY CreatedOn DESC
                """
            ),
            {"limit": min(max(1, limit), 100)},
        ).mappings().all()
        return [dict(r) for r in rows]
