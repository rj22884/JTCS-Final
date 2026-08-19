"""Audit log writer for important CRM/ERP mutations."""

from __future__ import annotations

import json
from typing import Any

from flask import has_request_context, request, session
from sqlalchemy import text

from app.extensions import db
from app.modules.shared.schema import ensure_crm_schema


class AuditService:
    def log(
        self,
        *,
        action_name: str,
        entity_type: str | None = None,
        entity_id: int | None = None,
        old_value: Any = None,
        new_value: Any = None,
        user_id: int | None = None,
        user_name: str | None = None,
        ip_address: str | None = None,
        browser: str | None = None,
        module: str | None = None,
        status: str | None = None,
    ) -> int:
        ensure_crm_schema()
        if has_request_context():
            user_id = user_id if user_id is not None else session.get("user_id")
            user_name = user_name or session.get("user_name")
            ip_address = ip_address or (request.headers.get("X-Forwarded-For") or request.remote_addr)
            browser = browser or (request.headers.get("User-Agent") or "")[:500]

        def _dump(value: Any) -> str | None:
            if value is None:
                return None
            if isinstance(value, str):
                return value
            try:
                return json.dumps(value, default=str)
            except Exception:
                return str(value)

        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.AuditLog
                    (UserID, UserName, ActionName, EntityType, EntityID, OldValue, NewValue,
                     IPAddress, Browser, Module, Status)
                OUTPUT INSERTED.AuditID
                VALUES
                    (:user_id, :user_name, :action_name, :entity_type, :entity_id, :old_value, :new_value,
                     :ip_address, :browser, :module, :status)
                """
            ),
            {
                "user_id": user_id,
                "user_name": (user_name or "")[:150] or None,
                "action_name": (action_name or "Action")[:100],
                "entity_type": entity_type,
                "entity_id": entity_id,
                "old_value": _dump(old_value),
                "new_value": _dump(new_value),
                "ip_address": (ip_address or "")[:64] or None,
                "browser": (browser or "")[:500] or None,
                "module": (module or entity_type or "")[:100] or None,
                "status": (status or "SUCCESS")[:30],
            },
        ).first()
        db.session.commit()
        return int(row[0]) if row else 0

    def list_logs(
        self,
        *,
        entity_type: str | None = None,
        entity_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        ensure_crm_schema()
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size
        clauses = ["1=1"]
        params: dict = {"limit": page_size, "offset": offset}
        if entity_type:
            clauses.append("EntityType = :entity_type")
            params["entity_type"] = entity_type
        if entity_id:
            clauses.append("EntityID = :entity_id")
            params["entity_id"] = entity_id
        where = " AND ".join(clauses)
        total = db.session.execute(
            text(f"SELECT COUNT(1) FROM dbo.AuditLog WHERE {where}"),
            params,
        ).scalar() or 0
        rows = db.session.execute(
            text(
                f"""
                SELECT AuditID, UserID, UserName, ActionName, EntityType, EntityID,
                       OldValue, NewValue, IPAddress, Browser, CreatedDate
                FROM dbo.AuditLog
                WHERE {where}
                ORDER BY CreatedDate DESC, AuditID DESC
                OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
                """
            ),
            params,
        ).mappings().all()
        return {
            "total": int(total),
            "page": page,
            "page_size": page_size,
            "rows": [dict(r) for r in rows],
        }
