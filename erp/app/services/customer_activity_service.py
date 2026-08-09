from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.extensions import db
from app.repositories.customer_repository import CustomerRepository


class CustomerActivityService:
    """Admin view of Customer Portal login / activation activity."""

    def __init__(self) -> None:
        self.repo = CustomerRepository()

    def ensure(self) -> None:
        self.repo.ensure_schema()

    def summary(self) -> dict[str, int]:
        self.ensure()
        row = (
            db.session.execute(
                text(
                    """
                    SELECT
                        SUM(CASE WHEN ISNULL(Logged, 0) = 1 THEN 1 ELSE 0 END) AS logged_count,
                        SUM(CASE WHEN ISNULL(PasswordChanged, 0) = 1 THEN 1 ELSE 0 END) AS password_set_count,
                        COUNT(1) AS total_customers
                    FROM dbo.CustomerMaster
                    WHERE ISNULL(CustomerStatus, N'Active') <> N'Inactive'
                    """
                )
            )
            .mappings()
            .first()
        ) or {}
        return {
            "logged_count": int(row.get("logged_count") or 0),
            "password_set_count": int(row.get("password_set_count") or 0),
            "total_customers": int(row.get("total_customers") or 0),
        }

    def list_logged_customers(
        self,
        *,
        search: str | None = None,
        only_logged: bool | None = True,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        self.ensure()
        lim = max(1, min(int(limit or 200), 1000))
        sql = """
            SELECT TOP (:lim)
                c.CustomerID,
                c.CustomerName,
                c.MobileNumber,
                c.PANNumber,
                c.AadhaarNumber,
                c.EmailID,
                ISNULL(c.Logged, 0) AS Logged,
                ISNULL(c.PasswordChanged, 0) AS PasswordChanged,
                c.LastLogin,
                c.LastPasswordChange,
                c.CustomerStatus
            FROM dbo.CustomerMaster c
            WHERE 1 = 1
        """
        params: dict[str, Any] = {"lim": lim}
        if only_logged is True:
            sql += " AND ISNULL(c.Logged, 0) = 1"
        elif only_logged is False:
            sql += " AND ISNULL(c.Logged, 0) = 0"
        if search:
            sql += """
              AND (
                c.CustomerName LIKE :search
                OR c.MobileNumber LIKE :search
                OR c.PANNumber LIKE :search_upper
                OR c.EmailID LIKE :search
                OR c.AadhaarNumber LIKE :search
              )
            """
            params["search"] = f"%{search.strip()}%"
            params["search_upper"] = f"%{search.strip().upper()}%"
        sql += " ORDER BY CASE WHEN c.LastLogin IS NULL THEN 1 ELSE 0 END, c.LastLogin DESC, c.CustomerName"
        rows = db.session.execute(text(sql), params).mappings().all()
        return [self._customer_row(r) for r in rows]

    def list_login_attempts(
        self,
        *,
        period: str = "7d",
        search: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.ensure()
        lim = max(1, min(int(limit or 100), 500))
        sql = """
            SELECT TOP (:lim)
                l.LogID,
                l.CustomerID,
                c.CustomerName,
                l.UserIdInput,
                l.DetectedType,
                l.AttemptResult,
                l.IpAddress,
                l.CreatedDate
            FROM dbo.CustomerPortalLoginLog l
            LEFT JOIN dbo.CustomerMaster c ON c.CustomerID = l.CustomerID
            WHERE 1 = 1
        """
        params: dict[str, Any] = {"lim": lim}
        since = self._period_since(period)
        if since is not None:
            sql += " AND l.CreatedDate >= :since"
            params["since"] = since
        if search:
            sql += """
              AND (
                l.UserIdInput LIKE :search
                OR c.CustomerName LIKE :search
                OR CAST(l.CustomerID AS NVARCHAR(20)) = :search_exact
              )
            """
            params["search"] = f"%{search.strip()}%"
            params["search_exact"] = search.strip()
        sql += " ORDER BY l.CreatedDate DESC, l.LogID DESC"
        rows = db.session.execute(text(sql), params).mappings().all()
        return [self._log_row(r) for r in rows]

    @staticmethod
    def _period_since(period: str) -> datetime | None:
        key = (period or "7d").strip().lower()
        now = datetime.utcnow()
        if key in {"today", "1d"}:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if key in {"7d", "week"}:
            return now - timedelta(days=7)
        if key in {"30d", "month"}:
            return now - timedelta(days=30)
        return None

    @staticmethod
    def _fmt_dt(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

    def _customer_row(self, row: Any) -> dict[str, Any]:
        return {
            "customer_id": int(row["CustomerID"]),
            "customer_name": row.get("CustomerName") or "",
            "mobile_number": row.get("MobileNumber") or "",
            "pan_number": row.get("PANNumber") or "",
            "aadhaar_number": row.get("AadhaarNumber") or "",
            "email_id": row.get("EmailID") or "",
            "logged": bool(row.get("Logged")),
            "password_changed": bool(row.get("PasswordChanged")),
            "last_login": self._fmt_dt(row.get("LastLogin")),
            "last_password_change": self._fmt_dt(row.get("LastPasswordChange")),
            "customer_status": row.get("CustomerStatus") or "",
        }

    def _log_row(self, row: Any) -> dict[str, Any]:
        return {
            "log_id": int(row["LogID"]),
            "customer_id": int(row["CustomerID"]) if row.get("CustomerID") is not None else None,
            "customer_name": row.get("CustomerName") or "",
            "user_id_input": row.get("UserIdInput") or "",
            "detected_type": row.get("DetectedType") or "",
            "attempt_result": row.get("AttemptResult") or "",
            "ip_address": row.get("IpAddress") or "",
            "created_date": self._fmt_dt(row.get("CreatedDate")),
        }
