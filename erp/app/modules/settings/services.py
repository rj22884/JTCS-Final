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
    mask_access_token,
    mask_secret,
    MASK_PLACEHOLDER,
)
from app.modules.settings.models import PROVIDER_FIELDS, PROVIDERS, get_providers_catalog, is_secret_key
from app.modules.settings.repositories import IntegrationSettingsRepository

logger = logging.getLogger(__name__)

STATUS_CONNECTED = "Connected"
STATUS_PARTIAL = "Partial Configuration"
STATUS_NOT_CONFIGURED = "Not Configured"
STATUS_TOKEN_EXPIRED = "Token Expired"
STATUS_INVALID_TOKEN = "Invalid Token"
STATUS_WEBHOOK_FAILED = "Webhook Failed"
STATUS_DISCONNECTED = "Disconnected"
STATUS_PERMISSION_MISSING = "Permission Missing"


class IntegrationSettingsService:
    def __init__(self, repository: IntegrationSettingsRepository | None = None):
        self.repository = repository or IntegrationSettingsRepository()
        self.audit = IntegrationSettingsAuditService(self.repository)

    def providers_catalog(self) -> list[dict]:
        return get_providers_catalog()

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
        extras: dict[str, Any] = {}
        if provider == "whatsapp_meta":
            plain_cfg = self.get_provider_config_decrypted(provider)
            missing = self.whatsapp_missing_fields(plain_cfg)
            # Access token shown as EAAG***XYZ hint (input still fully masked)
            extras["access_token_display"] = mask_access_token(plain_cfg.get("access_token"))
            extras["token_expires_at"] = (plain_cfg.get("token_expires_at") or "").strip()
            extras["localhost_warning"] = self._localhost_warning(plain_cfg.get("webhook_url") or "")
            # Keep password input fully masked; never put partial token in the input value
            if values.get("access_token"):
                values["access_token"] = MASK_PLACEHOLDER
            if values.get("app_secret"):
                values["app_secret"] = MASK_PLACEHOLDER
            if values.get("webhook_verify_token"):
                values["webhook_verify_token"] = MASK_PLACEHOLDER
        return {
            "provider": provider,
            "fields": fields,
            "field_values": values,
            "values": values,
            "missing": missing,
            "missing_labels": self._missing_labels(missing),
            "status_code": self._status_code(values.get("connection_status") or ""),
            **extras,
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
        readonly_keys = {
            f["key"] for f in PROVIDER_FIELDS[provider] if f.get("input") == "readonly"
        }

        if provider == "whatsapp_meta":
            errors = self.validate_whatsapp_payload(payload, allowed_keys=allowed_keys)
            if errors:
                raise ValueError("; ".join(errors))

        for key, raw_value in (payload or {}).items():
            if key not in allowed_keys:
                continue
            if key in readonly_keys or key == "connection_status":
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
        result = self.get_provider_settings_masked(provider)

        # WhatsApp: after App ID + App Secret are saved, start Meta OAuth so the
        # admin enters Facebook password / OTP on Facebook's page (never in ERP).
        if provider == "whatsapp_meta":
            result.update(self._whatsapp_auto_connect_payload())
        return result

    def _whatsapp_auto_connect_payload(self) -> dict[str, Any]:
        """Return authorize_url when credentials exist but Meta is not connected yet."""
        cfg = self.get_provider_config_decrypted("whatsapp_meta")
        app_id = (cfg.get("app_id") or "").strip()
        app_secret = (cfg.get("app_secret") or "").strip()
        access_token = (cfg.get("access_token") or "").strip()
        phone_id = (cfg.get("phone_number_id") or "").strip()
        status = (cfg.get("connection_status") or "").strip().lower()

        if not app_id or not app_secret:
            return {
                "auto_connect": False,
                "message": "App ID aur App Secret save karein, phir Connect Meta.",
            }
        # Already fully connected — do not force another OAuth redirect on every Save.
        if access_token and phone_id and status.startswith("connected"):
            return {
                "auto_connect": False,
                "message": "Settings saved. WhatsApp already connected.",
            }
        try:
            from app.modules.settings.whatsapp_oauth_service import WhatsAppOAuthService

            oauth = WhatsAppOAuthService(self, self.repository).start_connect()
            return {
                "auto_connect": True,
                "authorize_url": oauth.get("authorize_url"),
                "redirect_uri": oauth.get("redirect_uri"),
                "message": (
                    "Credentials saved. Facebook login page open ho rahi hai — "
                    "password aur OTP Facebook par enter karein. ERP Facebook password store nahi karta."
                ),
            }
        except ValueError as exc:
            return {"auto_connect": False, "message": str(exc)}
        except Exception as exc:
            logger.exception("Auto Connect Meta after save failed")
            return {
                "auto_connect": False,
                "message": f"Saved, but Connect Meta could not start: {exc}",
            }

    def validate_whatsapp_payload(
        self,
        payload: dict[str, Any],
        *,
        allowed_keys: set[str] | None = None,
    ) -> list[str]:
        """Validate WhatsApp fields on Save (respects masked secrets).

        Progressive setup: App ID + App Secret alone is allowed before Connect Meta.
        Once discovery/token fields exist, full required set is enforced.
        """
        cfg = self.get_provider_config_decrypted("whatsapp_meta")
        merged = dict(cfg)
        for key, raw in (payload or {}).items():
            if allowed_keys and key not in allowed_keys:
                continue
            value = "" if raw is None else str(raw)
            if is_secret_key(key) and is_masked_or_unchanged(value):
                continue
            if value.strip():
                merged[key] = value.strip()

        errors = []
        if not (merged.get("app_id") or "").strip():
            errors.append("App ID is required")
        # App secret: required in merged (existing encrypted or newly posted)
        secret_posted = payload.get("app_secret") if payload else None
        if not (merged.get("app_secret") or "").strip():
            if not (secret_posted and not is_masked_or_unchanged(str(secret_posted))):
                errors.append("App Secret is required")

        advanced = any(
            (merged.get(k) or "").strip()
            for k in ("business_id", "waba_id", "phone_number_id", "access_token")
        )
        if advanced:
            for key, label in (
                ("business_id", "Business ID"),
                ("waba_id", "WhatsApp Business Account ID"),
                ("phone_number_id", "Phone Number ID"),
                ("access_token", "Access Token"),
                ("webhook_verify_token", "Webhook Verify Token"),
                ("webhook_url", "Webhook URL"),
            ):
                if not (merged.get(key) or "").strip():
                    errors.append(f"{label} is required")
        return errors

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
        # >= 64 characters for Meta webhook verify token
        token = secrets.token_urlsafe(48)
        if len(token) < 64:
            token = secrets.token_hex(32)  # 64 hex chars
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
            "webhook_verify_token_plain": token,  # one-time copy for admin UI only
            "webhook_verify_token": mask_secret(token),
            "token_length": len(token),
            "message": "Verify token generated and saved (encrypted). Copy it now for Meta Dashboard.",
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
            "webhook_verify_token",
            "webhook_url",
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
            "webhook_verify_token": "Webhook Verify Token",
            "webhook_url": "Webhook URL",
        }
        return [labels.get(k, k) for k in keys]

    @staticmethod
    def _status_code(status: str) -> str:
        s = (status or "").strip().lower()
        if s == "connected":
            return "connected"
        if "expired" in s:
            return "token_expired"
        if "invalid" in s:
            return "invalid_token"
        if "webhook" in s and "fail" in s:
            return "webhook_failed"
        if "permission" in s:
            return "permission_missing"
        if "disconnect" in s:
            return "disconnected"
        if "partial" in s:
            return "partial"
        return "not_configured"

    @staticmethod
    def _localhost_warning(webhook_url: str) -> str | None:
        url = (webhook_url or "").lower()
        if "localhost" in url or "127.0.0.1" in url:
            return (
                "Meta cannot access localhost. "
                "Set APP_BASE_URL to a public domain or use ngrok for webhooks."
            )
        return None

    def check_token_on_login(self) -> dict[str, Any] | None:
        """Called after admin login — returns alert payload if token unhealthy."""
        try:
            cfg = self.get_provider_config_decrypted("whatsapp_meta")
            if not (cfg.get("access_token") or "").strip():
                return None
            from app.modules.settings.whatsapp_health_service import WhatsAppHealthService

            health = WhatsAppHealthService(self, self.repository).token_health()
            if health.get("ok"):
                return None
            return {
                "type": "whatsapp_token",
                "status": health.get("status"),
                "message": health.get("message") or "WhatsApp Access Token needs attention.",
                "link": "/admin/integrations",
            }
        except Exception:
            logger.exception("WhatsApp token check on login failed")
            return None

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
