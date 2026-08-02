"""Integration Settings audit — masked old/new values only."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import has_request_context, request, session
from sqlalchemy import text

from app.extensions import db
from app.modules.settings.crypto import decrypt_value, mask_secret
from app.modules.settings.models import is_secret_key
from app.modules.settings.repositories import IntegrationSettingsRepository


class IntegrationSettingsAuditService:
    def __init__(self, repository: IntegrationSettingsRepository | None = None):
        self.repository = repository or IntegrationSettingsRepository()

    def _mask_for_audit(self, setting_key: str, cipher_or_plain: str | None, *, was_encrypted: bool) -> str:
        if cipher_or_plain in (None, ""):
            return ""
        plain = decrypt_value(cipher_or_plain) if was_encrypted else str(cipher_or_plain)
        if plain is None:
            return "********"
        if is_secret_key(setting_key):
            return mask_secret(plain)
        # Non-secret: store truncated plain for audit readability
        text_val = str(plain)
        return text_val if len(text_val) <= 200 else text_val[:200] + "…"

    def log_change(
        self,
        *,
        provider: str,
        setting_key: str,
        old_cipher: str | None,
        new_cipher: str | None,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> None:
        self.repository.ensure_audit_schema()
        if has_request_context():
            user_id = user_id if user_id is not None else session.get("user_id")
            user_name = user_name or session.get("user_name")
            ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "")[:64]
            browser = (request.headers.get("User-Agent") or "")[:500]
        else:
            ip = None
            browser = None

        old_masked = self._mask_for_audit(setting_key, old_cipher, was_encrypted=True)
        new_masked = self._mask_for_audit(setting_key, new_cipher, was_encrypted=True)
        if old_masked == new_masked:
            return

        db.session.execute(
            text(
                """
                INSERT INTO dbo.IntegrationSettingsAudit
                    (Provider, SettingKey, OldValueMasked, NewValueMasked,
                     ChangedByUserID, ChangedByUserName, IPAddress, Browser, CreatedOn)
                VALUES
                    (:provider, :key, :old_v, :new_v, :uid, :uname, :ip, :browser, :now)
                """
            ),
            {
                "provider": provider[:50],
                "key": setting_key[:100],
                "old_v": old_masked or None,
                "new_v": new_masked or None,
                "uid": user_id,
                "uname": (user_name or "")[:150] or None,
                "ip": ip or None,
                "browser": browser or None,
                "now": datetime.utcnow(),
            },
        )
        db.session.commit()

    def list_recent(self, *, provider: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self.repository.ensure_audit_schema()
        limit = min(max(1, limit), 100)
        if provider:
            rows = db.session.execute(
                text(
                    """
                    SELECT TOP (:limit)
                        AuditID, Provider, SettingKey, OldValueMasked, NewValueMasked,
                        ChangedByUserID, ChangedByUserName, IPAddress, Browser, CreatedOn
                    FROM dbo.IntegrationSettingsAudit
                    WHERE Provider = :provider
                    ORDER BY CreatedOn DESC, AuditID DESC
                    """
                ),
                {"limit": limit, "provider": provider},
            ).mappings().all()
        else:
            rows = db.session.execute(
                text(
                    """
                    SELECT TOP (:limit)
                        AuditID, Provider, SettingKey, OldValueMasked, NewValueMasked,
                        ChangedByUserID, ChangedByUserName, IPAddress, Browser, CreatedOn
                    FROM dbo.IntegrationSettingsAudit
                    ORDER BY CreatedOn DESC, AuditID DESC
                    """
                ),
                {"limit": limit},
            ).mappings().all()
        return [dict(r) for r in rows]
