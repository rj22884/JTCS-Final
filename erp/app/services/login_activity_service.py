"""Staff login activity + password event tracking (Admin Dashboard)."""

from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from flask import has_request_context, request
from sqlalchemy import text

from app.extensions import db

logger = logging.getLogger(__name__)

_SCHEMA_READY = False

STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
EVENT_FIRST_SET = "FIRST_SET"
EVENT_RESET = "RESET"


class LoginActivityService:
    def ensure_schema(self) -> None:
        global _SCHEMA_READY
        if _SCHEMA_READY:
            return
        statements = (
            """
            IF COL_LENGTH(N'dbo.Users', N'IsPasswordSet') IS NULL
                ALTER TABLE dbo.Users ADD IsPasswordSet BIT NOT NULL
                    CONSTRAINT DF_Users_IsPasswordSet DEFAULT (0);
            """,
            """
            UPDATE dbo.Users
            SET IsPasswordSet = 1
            WHERE IsPasswordSet = 0
              AND (
                    EmailVerified = 1
                    OR UserStatus = N'Active'
                    OR Role LIKE N'%Administrator%'
                    OR Role LIKE N'%Admin%'
                  );
            """,
            """
            IF OBJECT_ID(N'dbo.user_login_activity', N'U') IS NULL
            BEGIN
                CREATE TABLE dbo.user_login_activity (
                    id INT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_user_login_activity PRIMARY KEY,
                    user_id NVARCHAR(100) NOT NULL,
                    user_pk INT NULL,
                    login_time DATETIME NOT NULL CONSTRAINT DF_user_login_activity_login_time DEFAULT (GETDATE()),
                    ip_address NVARCHAR(50) NULL,
                    device NVARCHAR(300) NULL,
                    status NVARCHAR(20) NOT NULL,
                    session_id NVARCHAR(200) NULL,
                    logout_time DATETIME NULL
                );
                CREATE INDEX IX_user_login_activity_login_time
                    ON dbo.user_login_activity (login_time DESC);
                CREATE INDEX IX_user_login_activity_user_id
                    ON dbo.user_login_activity (user_id, login_time DESC);
            END;
            """,
            """
            IF OBJECT_ID(N'dbo.user_password_events', N'U') IS NULL
            BEGIN
                CREATE TABLE dbo.user_password_events (
                    id INT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_user_password_events PRIMARY KEY,
                    user_id NVARCHAR(100) NOT NULL,
                    user_pk INT NULL,
                    event_type NVARCHAR(50) NOT NULL,
                    event_time DATETIME NOT NULL CONSTRAINT DF_user_password_events_event_time DEFAULT (GETDATE())
                );
                CREATE INDEX IX_user_password_events_event_time
                    ON dbo.user_password_events (event_time DESC);
            END;
            """,
        )
        try:
            for sql in statements:
                db.session.execute(text(sql))
            db.session.commit()
            _SCHEMA_READY = True
        except Exception:
            db.session.rollback()
            logger.exception("Login activity schema ensure failed")
            raise

    @staticmethod
    def _client_ip() -> str | None:
        if not has_request_context():
            return None
        forwarded = (request.headers.get("X-Forwarded-For") or "").strip()
        if forwarded:
            return forwarded.split(",")[0].strip()[:50]
        return (request.remote_addr or "")[:50] or None

    @staticmethod
    def _device() -> str | None:
        if not has_request_context():
            return None
        return (request.headers.get("User-Agent") or "")[:300] or None

    def log_login_activity(
        self,
        user_id: str,
        status: str,
        *,
        user_pk: int | None = None,
        session_id: str | None = None,
        ip_address: str | None = None,
        device: str | None = None,
    ) -> str | None:
        """Insert a login attempt. Returns session_id for SUCCESS rows."""
        self.ensure_schema()
        status_norm = (status or "").strip().upper()
        if status_norm not in {STATUS_SUCCESS, STATUS_FAILED}:
            status_norm = STATUS_FAILED
        user_key = (user_id or "unknown").strip()[:100] or "unknown"
        sid = session_id
        if status_norm == STATUS_SUCCESS and not sid:
            sid = str(uuid.uuid4())
        try:
            db.session.execute(
                text(
                    """
                    INSERT INTO dbo.user_login_activity
                        (user_id, user_pk, login_time, ip_address, device, status, session_id)
                    VALUES
                        (:user_id, :user_pk, GETDATE(), :ip_address, :device, :status, :session_id)
                    """
                ),
                {
                    "user_id": user_key,
                    "user_pk": user_pk,
                    "ip_address": (ip_address if ip_address is not None else self._client_ip()),
                    "device": (device if device is not None else self._device()),
                    "status": status_norm,
                    "session_id": sid,
                },
            )
            db.session.commit()
            return sid
        except Exception:
            db.session.rollback()
            logger.exception("Failed to log login activity for %s", user_key)
            return sid

    def mark_logout(self, session_id: str | None) -> None:
        sid = (session_id or "").strip()
        if not sid:
            return
        self.ensure_schema()
        try:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.user_login_activity
                    SET logout_time = GETDATE()
                    WHERE session_id = :session_id
                      AND logout_time IS NULL
                    """
                ),
                {"session_id": sid[:200]},
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Failed to mark logout for session")

    def log_password_event(
        self,
        user_id: str,
        event_type: str,
        *,
        user_pk: int | None = None,
    ) -> None:
        self.ensure_schema()
        et = (event_type or "").strip().upper()
        if et not in {EVENT_FIRST_SET, EVENT_RESET}:
            et = EVENT_RESET
        try:
            db.session.execute(
                text(
                    """
                    INSERT INTO dbo.user_password_events
                        (user_id, user_pk, event_type, event_time)
                    VALUES
                        (:user_id, :user_pk, :event_type, GETDATE())
                    """
                ),
                {
                    "user_id": (user_id or "unknown").strip()[:100] or "unknown",
                    "user_pk": user_pk,
                    "event_type": et,
                },
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Failed to log password event")

    def _range_bounds(self, period: str) -> tuple[datetime | None, datetime | None]:
        today = date.today()
        p = (period or "all").strip().lower()
        if p == "today":
            start = datetime.combine(today, datetime.min.time())
            return start, None
        if p in {"7d", "last_7_days", "week"}:
            start = datetime.combine(today - timedelta(days=6), datetime.min.time())
            return start, None
        return None, None

    def recent_logins(
        self,
        *,
        limit: int = 10,
        period: str = "all",
        search: str = "",
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        limit = min(max(int(limit or 10), 1), 200)
        start, _ = self._range_bounds(period)
        q = (search or "").strip()[:100]
        clauses = ["1=1"]
        params: dict[str, Any] = {"limit": limit}
        if start is not None:
            clauses.append("login_time >= :start")
            params["start"] = start
        if q:
            clauses.append("user_id LIKE :q")
            params["q"] = f"%{q}%"
        where = " AND ".join(clauses)
        rows = db.session.execute(
            text(
                f"""
                SELECT TOP (:limit)
                    id, user_id, user_pk, login_time, ip_address, device, status, session_id, logout_time
                FROM dbo.user_login_activity
                WHERE {where}
                ORDER BY login_time DESC, id DESC
                """
            ),
            params,
        ).mappings().all()
        return [self._serialize_login(r) for r in rows]

    def recent_password_events(
        self,
        *,
        limit: int = 10,
        period: str = "all",
        search: str = "",
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        limit = min(max(int(limit or 10), 1), 200)
        start, _ = self._range_bounds(period)
        q = (search or "").strip()[:100]
        clauses = ["1=1"]
        params: dict[str, Any] = {"limit": limit}
        if start is not None:
            clauses.append("event_time >= :start")
            params["start"] = start
        if q:
            clauses.append("user_id LIKE :q")
            params["q"] = f"%{q}%"
        where = " AND ".join(clauses)
        rows = db.session.execute(
            text(
                f"""
                SELECT TOP (:limit)
                    id, user_id, user_pk, event_type, event_time
                FROM dbo.user_password_events
                WHERE {where}
                ORDER BY event_time DESC, id DESC
                """
            ),
            params,
        ).mappings().all()
        return [self._serialize_password_event(r) for r in rows]

    def export_logins_csv(
        self,
        *,
        period: str = "all",
        search: str = "",
    ) -> str:
        rows = self.recent_logins(limit=200, period=period, search=search)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["user_id", "login_time", "ip_address", "device", "status", "logout_time"])
        for r in rows:
            writer.writerow(
                [
                    r.get("user_id"),
                    r.get("login_time"),
                    r.get("ip_address"),
                    r.get("device"),
                    r.get("status"),
                    r.get("logout_time"),
                ]
            )
        return buf.getvalue()

    @staticmethod
    def _serialize_login(row: Any) -> dict[str, Any]:
        login_time = row.get("login_time")
        logout_time = row.get("logout_time")
        return {
            "id": row.get("id"),
            "user_id": row.get("user_id") or "",
            "user_pk": row.get("user_pk"),
            "login_time": login_time.isoformat(sep=" ", timespec="seconds") if login_time else "",
            "ip_address": row.get("ip_address") or "—",
            "device": row.get("device") or "—",
            "status": (row.get("status") or "").upper(),
            "session_id": row.get("session_id"),
            "logout_time": logout_time.isoformat(sep=" ", timespec="seconds") if logout_time else "",
        }

    @staticmethod
    def _serialize_password_event(row: Any) -> dict[str, Any]:
        event_time = row.get("event_time")
        return {
            "id": row.get("id"),
            "user_id": row.get("user_id") or "",
            "user_pk": row.get("user_pk"),
            "event_type": (row.get("event_type") or "").upper(),
            "event_time": event_time.isoformat(sep=" ", timespec="seconds") if event_time else "",
        }
