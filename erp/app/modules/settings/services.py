"""Integration Settings service — store/load/mask + WhatsApp orchestration hooks."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from app.modules.settings.audit_service import IntegrationSettingsAuditService
from app.modules.settings.crypto import (
    UNCHANGED_SENTINEL,
    decrypt_value,
    encrypt_value,
    is_masked_or_unchanged,
    mask_secret,
    MASK_PLACEHOLDER,
)
from app.modules.settings.models import PROVIDER_FIELDS, PROVIDERS, is_secret_key
from app.modules.settings.repositories import IntegrationSettingsRepository

logger = logging.getLogger(__name__)

STATUS_CONNECTED = "Connected"
STATUS_PARTIAL = "Partial Configuration"
STATUS_NOT_CONFIGURED = "Not Configured"


class IntegrationSettingsService:
    def __init__(self, repository: IntegrationSettingsRepository | None = None):
        self.repository = repository or IntegrationSettingsRepository()
        self.audit = IntegrationSettingsAuditService(self.repository)

    def providers_catalog(self) -> list[dict]:
        return [dict(p) for p in PROVIDERS]

    def get_provider_settings_masked(self, provider: str) -> dict[str, Any]:
        if provider == "whatsapp_meta":
            # Repair previously mis-mapped token values sitting in ID fields.
            try:
                from app.modules.settings.whatsapp_oauth_service import WhatsAppOAuthService

                WhatsAppOAuthService(self, self.repository).sanitize_stored_ids()
            except Exception:
                logger.exception("WhatsApp ID sanitize skipped")

        fields = PROVIDER_FIELDS.get(provider) or []
        stored = {
            row["SettingKey"]: row.get("SettingValueEncrypted")
            for row in self.repository.list_by_provider(provider)
        }
        values: dict[str, Any] = {}
        for field in fields:
            key = field["key"]
            cipher = stored.get(key)
            plain = decrypt_value(cipher) if cipher not in (None, "") else ""
            if is_secret_key(key):
                # Full mask in forms — never echo password tails into inputs.
                values[key] = MASK_PLACEHOLDER if plain else ""
            else:
                # Never surface token-like values in non-secret ID fields.
                if key in {"business_id", "waba_id", "phone_number_id"} and self._looks_like_token(plain):
                    values[key] = ""
                else:
                    values[key] = plain or ""
        missing = []
        if provider == "whatsapp_meta":
            missing = self.whatsapp_missing_fields(self.get_provider_config_decrypted(provider))
        return {
            "provider": provider,
            "fields": fields,
            "field_values": values,
            "values": values,
            "missing": missing,
            "missing_labels": self._missing_labels(missing),
            "status_code": self._status_code(values.get("connection_status") or ""),
        }

    def get_all_masked(self) -> dict[str, Any]:
        tabs = []
        for item in PROVIDERS:
            code = item["code"]
            tabs.append(
                {
                    "code": code,
                    "label": item["label"],
                    **self.get_provider_settings_masked(code),
                }
            )
        return {"providers": tabs}

    def get_provider_config_decrypted(self, provider: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for row in self.repository.list_by_provider(provider):
            key = row["SettingKey"]
            plain = decrypt_value(row.get("SettingValueEncrypted"))
            result[key] = plain if plain is not None else ""
        return result

    def save_provider_settings(self, provider: str, payload: dict[str, Any]) -> dict[str, Any]:
        if provider not in PROVIDER_FIELDS:
            raise ValueError("Unknown integration provider.")

        allowed_keys = {f["key"] for f in PROVIDER_FIELDS[provider]}

        for key, raw_value in (payload or {}).items():
            if key not in allowed_keys:
                continue
            if key == "connection_status":
                continue

            value = "" if raw_value is None else str(raw_value)

            if is_secret_key(key):
                if is_masked_or_unchanged(value) or value == UNCHANGED_SENTINEL:
                    continue
                stored = encrypt_value(value)
            else:
                stored = encrypt_value(value)

            old = self.repository.get_encrypted_value(provider, key)
            self.repository.upsert(
                provider=provider,
                setting_key=key,
                value_encrypted=stored,
                description=f"{provider}.{key}",
            )
            try:
                self.audit.log_change(
                    provider=provider,
                    setting_key=key,
                    old_cipher=old,
                    new_cipher=stored,
                )
            except Exception:
                logger.exception("Audit failed for %s.%s", provider, key)

        if provider == "whatsapp_meta":
            self.refresh_whatsapp_status_from_fields()
        elif provider == "smtp":
            self.refresh_smtp_status_from_fields()

        logger.info("Integration settings saved for provider=%s", provider)
        return self.get_provider_settings_masked(provider)

    def refresh_smtp_status_from_fields(self) -> str:
        cfg = self.get_provider_config_decrypted("smtp")
        required = ["host", "port", "username", "from_email", "smtp_password"]
        missing = [k for k in required if not (cfg.get(k) or "").strip()]
        status = STATUS_PARTIAL if not missing else STATUS_NOT_CONFIGURED
        self.repository.upsert(
            provider="smtp",
            setting_key="connection_status",
            value_encrypted=encrypt_value(status),
            description="smtp.connection_status",
        )
        return status

    def generate_whatsapp_verify_token(self) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        old = self.repository.get_encrypted_value("whatsapp_meta", "webhook_verify_token")
        stored = encrypt_value(token)
        self.repository.upsert(
            provider="whatsapp_meta",
            setting_key="webhook_verify_token",
            value_encrypted=stored,
            description="whatsapp_meta.webhook_verify_token",
        )
        try:
            self.audit.log_change(
                provider="whatsapp_meta",
                setting_key="webhook_verify_token",
                old_cipher=old,
                new_cipher=stored,
            )
        except Exception:
            logger.exception("Audit failed for webhook_verify_token")
        self.refresh_whatsapp_status_from_fields()
        return {
            "ok": True,
            "webhook_verify_token": mask_secret(token),
            "message": "Verify token generated and saved (encrypted).",
            "field_values": self.get_provider_settings_masked("whatsapp_meta")["field_values"],
        }

    def test_whatsapp_connection(
        self,
        *,
        send_test_message: bool = False,
        test_to_number: str | None = None,
    ) -> dict[str, Any]:
        from app.modules.settings.whatsapp_test_service import WhatsAppTestService

        return WhatsAppTestService(self, self.repository).run(
            send_test_message=send_test_message,
            test_to_number=test_to_number,
        )

    def refresh_whatsapp_status_from_fields(self) -> str:
        cfg = self.get_provider_config_decrypted("whatsapp_meta")
        missing = self.whatsapp_missing_fields(cfg)
        if missing:
            status = STATUS_NOT_CONFIGURED
        elif (cfg.get("connection_status") or "") == STATUS_CONNECTED:
            status = STATUS_CONNECTED
        else:
            status = STATUS_PARTIAL
        self.repository.upsert(
            provider="whatsapp_meta",
            setting_key="connection_status",
            value_encrypted=encrypt_value(status),
            description="whatsapp_meta.connection_status",
        )
        return status

    @staticmethod
    def whatsapp_missing_fields(cfg: dict[str, str]) -> list[str]:
        required = [
            "app_id",
            "app_secret",
            "access_token",
            "business_id",
            "waba_id",
            "phone_number_id",
            "graph_api_version",
        ]
        return [k for k in required if not (cfg.get(k) or "").strip()]

    @staticmethod
    def _missing_labels(keys: list[str]) -> list[str]:
        labels = {
            "app_id": "App ID",
            "app_secret": "App Secret",
            "access_token": "Access Token",
            "business_id": "Business ID",
            "waba_id": "WhatsApp Business Account ID",
            "phone_number_id": "Phone Number ID",
            "graph_api_version": "Graph API Version",
        }
        return [labels.get(k, k) for k in keys]

    @staticmethod
    def _status_code(status: str) -> str:
        s = (status or "").strip().lower()
        if s == "connected":
            return "connected"
        if "partial" in s:
            return "partial"
        return "not_configured"

    @staticmethod
    def _looks_like_token(value: str | None) -> bool:
        text = (value or "").strip()
        if not text:
            return False
        if text.startswith("EAA") or text.startswith("YA") or text.startswith("IG"):
            return True
        if len(text) >= 80 and any(c.isalpha() for c in text) and any(c.isdigit() for c in text):
            return True
        return False

    def status_summary(self) -> dict[str, Any]:
        items = []
        for p in PROVIDERS:
            code = p["code"]
            cfg = self.get_provider_config_decrypted(code)
            status = (cfg.get("connection_status") or "").strip() or STATUS_NOT_CONFIGURED
            configured = any(
                (v or "").strip()
                for k, v in cfg.items()
                if k != "connection_status"
            )
            items.append(
                {
                    "provider": code,
                    "label": p["label"],
                    "connection_status": status if configured else STATUS_NOT_CONFIGURED,
                    "configured": configured,
                    "status_code": self._status_code(status if configured else STATUS_NOT_CONFIGURED),
                }
            )
        return {"ok": True, "providers": items}
