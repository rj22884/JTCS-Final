"""Server authentication + important-activity trail (reuses dbo.AuditLog)."""

from __future__ import annotations

import json
import logging
from typing import Any

from flask import has_request_context, request, session
from sqlalchemy import text

from app.extensions import db

logger = logging.getLogger(__name__)

STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"

_SKIP_ENDPOINT_PREFIXES = (
    "static",
    "auth.",
    "server_auth.",
    "setup.",
    "customer_portal.",
    "public_intake.",
    "seo_api.",
    "website_analytics_public.",
    "website_snapshot_public.",
    "notification_api.",
    "search_api.",
)

_SKIP_ENDPOINTS = {
    "dashboard.health",
    "dashboard.analytics",
    "dashboard.metric_details",
}


def client_ip() -> str | None:
    if not has_request_context():
        return None
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.remote_addr or "")[:64] or None


def _dump(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except Exception:
        return str(value)


class ServerAuditService:
    def log(
        self,
        *,
        action: str,
        module: str = "ServerAuth",
        record_id: int | None = None,
        status: str = STATUS_SUCCESS,
        old_value: Any = None,
        new_value: Any = None,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> None:
        try:
            if has_request_context():
                user_id = user_id if user_id is not None else session.get("user_id")
                user_name = user_name or session.get("user_name") or session.get("server_login_id")
            ip_address = client_ip()
            browser = ""
            if has_request_context():
                browser = (request.headers.get("User-Agent") or "")[:500]
            db.session.execute(
                text(
                    """
                    INSERT INTO dbo.AuditLog
                        (UserID, UserName, ActionName, EntityType, EntityID,
                         OldValue, NewValue, IPAddress, Browser, Module, Status)
                    VALUES
                        (:user_id, :user_name, :action_name, :entity_type, :entity_id,
                         :old_value, :new_value, :ip_address, :browser, :module, :status)
                    """
                ),
                {
                    "user_id": user_id,
                    "user_name": (user_name or "")[:150] or None,
                    "action_name": (action or "Action")[:100],
                    "entity_type": (module or "ServerAuth")[:50],
                    "entity_id": record_id,
                    "old_value": _dump(old_value),
                    "new_value": _dump(new_value),
                    "ip_address": ip_address,
                    "browser": browser or None,
                    "module": (module or "ServerAuth")[:100],
                    "status": (status or STATUS_SUCCESS)[:30],
                },
            )
            db.session.commit()
        except Exception:
            logger.exception("Server audit log failed for action=%s", action)
            try:
                db.session.rollback()
            except Exception:
                pass

    def log_request(self, response):
        """Record Create / Edit / Delete / important POSTs after server auth."""
        if not has_request_context():
            return
        if not session.get("server_user_id"):
            return
        method = (request.method or "").upper()
        if method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        endpoint = request.endpoint or ""
        if endpoint in _SKIP_ENDPOINTS:
            return
        if any(endpoint.startswith(prefix) for prefix in _SKIP_ENDPOINT_PREFIXES):
            return
        if request.path.startswith("/static"):
            return

        action = "Delete" if method == "DELETE" else "Edit" if method in {"PUT", "PATCH"} else "Create"
        path_l = (request.path or "").lower()
        if "delete" in path_l:
            action = "Delete"
        elif any(token in path_l for token in ("update", "edit", "save", "change")):
            action = "Edit"

        record_id = None
        for value in (request.view_args or {}).values():
            if isinstance(value, int) and value > 0:
                record_id = value
                break

        module = (endpoint.split(".", 1)[0] if endpoint else "app")[:100]
        status_code = getattr(response, "status_code", 200) or 200
        status = STATUS_SUCCESS if 200 <= status_code < 400 else STATUS_FAILED
        self.log(
            action=action,
            module=module,
            record_id=record_id,
            status=status,
            new_value={"method": method, "path": request.path, "http_status": status_code},
        )
