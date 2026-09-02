"""Integration Settings service — store/load/mask + WhatsApp orchestration hooks."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from flask import current_app, has_app_context

from app.modules.settings.audit_service import IntegrationSettingsAuditService
from app.modules.settings.crypto import (
    UNCHANGED_SENTINEL,
    decrypt_value,
    encrypt_value,
    is_masked_or_unchanged,
    mask_access_token,
    mask_secret,
    MASK_PLACEHOLDER,
    SECRET_INPUT_MASK,
)
from app.modules.settings.models import (
    PROVIDER_FIELDS,
    PROVIDERS,
    WHATSAPP_SEND_REQUIRED_KEYS,
    get_providers_catalog,
    is_secret_key,
)
from app.modules.settings.repositories import IntegrationSettingsRepository
from app.modules.shared.audit_service import AuditService
from app.utils.smtp_health import check_smtp_connection, mask_email

logger = logging.getLogger(__name__)

STATUS_CONNECTED = "Connected"
STATUS_PARTIAL = "Partial Configuration"
STATUS_NOT_CONFIGURED = "Not Configured"
STATUS_TOKEN_EXPIRED = "Token Expired"
STATUS_INVALID_TOKEN = "Invalid Token"
STATUS_WEBHOOK_FAILED = "Webhook Failed"
STATUS_DISCONNECTED = "Disconnected"
STATUS_PERMISSION_MISSING = "Permission Missing"
STATUS_FAILED = "Connection Failed"


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
        secret_configured: dict[str, bool] = {}
        for field in fields:
            key = field["key"]
            cipher = stored.get(key)
            plain = decrypt_value(cipher) if cipher not in (None, "") else ""
            if is_secret_key(key):
                # Never send the real secret. Show a fixed mask so the admin
                # can see the value is saved. Save treats this mask as unchanged.
                configured = bool((plain or "").strip())
                values[key] = SECRET_INPUT_MASK if configured else ""
                secret_configured[key] = configured
            else:
                # Never surface token-like values in non-secret ID fields.
                if key in {"business_id", "waba_id", "phone_number_id"} and self._looks_like_token(plain):
                    values[key] = ""
                else:
                    values[key] = plain or ""
        missing = []
        extras: dict[str, Any] = {"secret_configured": secret_configured}
        if provider == "whatsapp_meta":
            plain_cfg = self.get_provider_config_decrypted(provider)
            missing = self.whatsapp_missing_fields(plain_cfg)
            # Display hint only (never put into the password input value)
            extras["access_token_display"] = mask_access_token(plain_cfg.get("access_token"))
            extras["token_expires_at"] = (plain_cfg.get("token_expires_at") or "").strip()
            extras["localhost_warning"] = self._localhost_warning(plain_cfg.get("webhook_url") or "")
        elif provider == "smtp":
            missing = self.smtp_missing_fields(self.get_provider_config_decrypted(provider))
            extras["missing_labels"] = self._smtp_missing_labels(missing)
        return {
            "provider": provider,
            "fields": fields,
            "field_values": values,
            "values": values,
            "missing": missing,
            "missing_labels": extras.get("missing_labels") or self._missing_labels(missing),
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
        field_inputs = {f["key"]: f.get("input") for f in PROVIDER_FIELDS[provider]}

        if provider == "whatsapp_meta":
            errors = self.validate_whatsapp_payload(payload, allowed_keys=allowed_keys)
            if errors:
                raise ValueError("; ".join(errors))
        elif provider == "smtp":
            errors = self.validate_smtp_payload(payload)
            if errors:
                raise ValueError("; ".join(errors))

        password_updated = False
        # Iterate catalog keys so SMTP checkboxes are always persisted.
        keys_to_save = [f["key"] for f in PROVIDER_FIELDS[provider] if f["key"] in allowed_keys]
        for key in keys_to_save:
            if key in readonly_keys or key == "connection_status":
                continue
            if key not in (payload or {}) and field_inputs.get(key) != "checkbox":
                continue

            raw_value = (payload or {}).get(key)
            if field_inputs.get(key) == "checkbox":
                value = "true" if self._as_bool(raw_value) else "false"
            else:
                value = "" if raw_value is None else str(raw_value)

            if is_secret_key(key):
                text = value.strip()
                # Blank / placeholder → keep existing encrypted secret (never clear it).
                if not text or text in {MASK_PLACEHOLDER, SECRET_INPUT_MASK, UNCHANGED_SENTINEL}:
                    continue
                if set(text) <= {"*"}:
                    # Browser/UI mask autofill — do not overwrite the real secret.
                    logger.info("Secret %s.%s skipped (mask autofill)", provider, key)
                    continue
                stored = encrypt_value(text)
                logger.info("Secret %s.%s updated (encrypted)", provider, key)
                if key == "smtp_password":
                    password_updated = True
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
            self._log_smtp_audit(
                "Updated SMTP Settings",
                detail={
                    "password_updated": password_updated,
                    "host": (payload or {}).get("host"),
                    "username": mask_email((payload or {}).get("username")),
                },
            )

        logger.info(
            "Integration settings saved for provider=%s password_updated=%s",
            provider,
            password_updated,
        )
        result = self.get_provider_settings_masked(provider)
        if provider == "smtp":
            if password_updated:
                result["message"] = (
                    "Settings saved successfully. Password encrypted and stored "
                    "(field cleared for security)."
                )
            else:
                result["message"] = (
                    "Settings saved successfully. Existing password kept "
                    "(enter a new password only to replace it)."
                )
            result["clear_secrets"] = True
            result["password_updated"] = password_updated

        if provider == "whatsapp_meta":
            missing = result.get("missing_labels") or []
            if missing:
                result["message"] = (
                    "Settings saved. WhatsApp send ke liye * wale fields complete karein, "
                    "phir Connect Facebook."
                )
            else:
                result["message"] = "Settings saved successfully."
        return result

    def validate_whatsapp_payload(
        self,
        payload: dict[str, Any],
        *,
        allowed_keys: set[str] | None = None,
    ) -> list[str]:
        """Validate WhatsApp fields on Save (respects masked secrets).

        Save only requires App ID + App Secret. Send-required token/WABA/phone
        fields are optional here so Connect Facebook can fill them later.
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
        secret_posted = payload.get("app_secret") if payload else None
        if not (merged.get("app_secret") or "").strip():
            if not (secret_posted and not is_masked_or_unchanged(str(secret_posted))):
                errors.append("App Secret is required")
        return errors

    def validate_smtp_payload(self, payload: dict[str, Any]) -> list[str]:
        """Validate SMTP form fields (password may be blank to keep existing)."""
        cfg = self.get_provider_config_decrypted("smtp")
        merged = dict(cfg)
        for key in ("host", "port", "username", "from_email", "use_tls", "use_ssl", "smtp_password"):
            raw = (payload or {}).get(key)
            if key == "smtp_password":
                # Only blank / exact mask means "keep existing". Do not treat other
                # asterisk strings as masked — that blocked real password saves.
                if raw is None:
                    continue
                text = str(raw).strip()
                if text and text not in {MASK_PLACEHOLDER, UNCHANGED_SENTINEL}:
                    merged[key] = text
                continue
            if raw is None:
                continue
            if key in {"use_tls", "use_ssl"}:
                merged[key] = "true" if self._as_bool(raw) else "false"
            else:
                text = str(raw).strip()
                if text:
                    merged[key] = text

        errors: list[str] = []
        if not (merged.get("host") or "").strip():
            errors.append("SMTP Host is required")
        port_raw = (merged.get("port") or "").strip()
        if not port_raw:
            errors.append("Port is required")
        else:
            try:
                port = int(port_raw)
                if port < 1 or port > 65535:
                    errors.append("Port must be between 1 and 65535")
            except ValueError:
                errors.append("Port must be a valid number")
        username = (merged.get("username") or "").strip()
        if not username:
            errors.append("Username is required")
        elif "@" not in username:
            errors.append("Username must be the full mailbox email (e.g. admin@jtcsxpert.com)")
        from_email = (merged.get("from_email") or "").strip()
        if not from_email:
            errors.append("From Email is required")
        elif "@" not in from_email or " " in from_email:
            errors.append(
                "From Email must be a real email like admin@jtcsxpert.com "
                "(not the company display name)"
            )
        if not (merged.get("smtp_password") or "").strip():
            errors.append("Password is required (enter a new password — none is stored yet)")
        return errors

    @staticmethod
    def smtp_missing_fields(cfg: dict[str, str]) -> list[str]:
        required = ["host", "port", "username", "from_email", "smtp_password"]
        return [k for k in required if not (cfg.get(k) or "").strip()]

    @staticmethod
    def _smtp_missing_labels(keys: list[str]) -> list[str]:
        labels = {
            "host": "SMTP Host",
            "port": "Port",
            "username": "Username",
            "from_email": "From Email",
            "smtp_password": "Password",
        }
        return [labels.get(k, k) for k in keys]

    def _set_smtp_connection_status(self, status: str) -> None:
        self.repository.upsert(
            provider="smtp",
            setting_key="connection_status",
            value_encrypted=encrypt_value(status),
            description="smtp.connection_status",
        )

    def refresh_smtp_status_from_fields(self) -> str:
        cfg = self.get_provider_config_decrypted("smtp")
        missing = self.smtp_missing_fields(cfg)
        current = (cfg.get("connection_status") or "").strip()
        if missing:
            status = STATUS_NOT_CONFIGURED
        elif current == STATUS_CONNECTED:
            status = STATUS_CONNECTED
        else:
            status = STATUS_PARTIAL
        self._set_smtp_connection_status(status)
        return status

    def smtp_runtime_config(self) -> dict[str, Any] | None:
        """Return Flask-style MAIL_* mapping from Integration Settings when complete.

        Used by EmailService so Admin → Integration Settings SMTP can drive outbound mail
        without putting the password in the frontend or requiring a process restart.
        """
        cfg = self.get_provider_config_decrypted("smtp")
        if self.smtp_missing_fields(cfg):
            return None
        try:
            port = int((cfg.get("port") or "465").strip())
        except ValueError:
            port = 465
        use_tls = self._as_bool(cfg.get("use_tls"))
        use_ssl = self._as_bool(cfg.get("use_ssl"))
        if not use_tls and not use_ssl:
            use_ssl = True
        return {
            "MAIL_SERVER": (cfg.get("host") or "").strip(),
            "MAIL_PORT": port,
            "MAIL_USERNAME": (cfg.get("username") or "").strip(),
            "MAIL_PASSWORD": (cfg.get("smtp_password") or "").strip(),
            "MAIL_DEFAULT_SENDER": (cfg.get("from_email") or "").strip(),
            "MAIL_USE_TLS": use_tls,
            "MAIL_USE_SSL": use_ssl,
            "MAIL_TIMEOUT": float(current_app.config.get("MAIL_TIMEOUT", 30))
            if has_app_context()
            else 30.0,
        }

    def test_smtp_connection(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """Live SMTP probe using form overrides + stored encrypted password when blank."""
        try:
            return self._test_smtp_connection_inner(overrides or {})
        except Exception as exc:
            logger.exception("SMTP test connection failed: %s", exc.__class__.__name__)
            try:
                masked = self.get_provider_settings_masked("smtp")
            except Exception:
                masked = {"provider": "smtp", "field_values": {}, "values": {}, "secret_configured": {}}
            return {
                "ok": False,
                "message": (
                    "Unable to test SMTP connection. "
                    "Confirm Host/Port/SSL, enter the Titan mailbox password, "
                    "and set From Email to admin@jtcsxpert.com (not the company name)."
                ),
                "clear_secrets": True,
                **masked,
            }

    def _test_smtp_connection_inner(self, payload: dict[str, Any]) -> dict[str, Any]:
        cfg = self.get_provider_config_decrypted("smtp")

        host = (str(payload.get("host") if payload.get("host") is not None else cfg.get("host") or "")).strip()
        port_raw = (str(payload.get("port") if payload.get("port") is not None else cfg.get("port") or "")).strip()
        username = (
            str(payload.get("username") if payload.get("username") is not None else cfg.get("username") or "")
        ).strip()
        from_email = (
            str(payload.get("from_email") if payload.get("from_email") is not None else cfg.get("from_email") or "")
        ).strip()

        posted_password = payload.get("smtp_password")
        posted_text = "" if posted_password is None else str(posted_password).strip()
        if posted_text and posted_text not in {MASK_PLACEHOLDER, UNCHANGED_SENTINEL} and not (
            set(posted_text) <= {"*"}
        ):
            password = posted_text
        else:
            password = (cfg.get("smtp_password") or "").strip()

        use_tls = self._as_bool(payload["use_tls"]) if "use_tls" in payload else self._as_bool(cfg.get("use_tls"))
        use_ssl = self._as_bool(payload["use_ssl"]) if "use_ssl" in payload else self._as_bool(cfg.get("use_ssl"))
        if not use_tls and not use_ssl:
            # Titan/GoDaddy default
            use_ssl = True

        errors: list[str] = []
        if not host:
            errors.append("SMTP Host is required")
        if not port_raw:
            errors.append("Port is required")
        if not username:
            errors.append("Username is required")
        if not password:
            errors.append(
                "Password is required to test — type the Titan mailbox password "
                "(or Save it first, then test with a blank password field)"
            )
        port = 0
        if port_raw:
            try:
                port = int(float(str(port_raw).strip()))
                if port < 1 or port > 65535:
                    errors.append("Port must be between 1 and 65535")
            except ValueError:
                errors.append("Port must be a valid number")
        if errors:
            return {
                "ok": False,
                "message": "; ".join(errors),
                "clear_secrets": True,
                **self.get_provider_settings_masked("smtp"),
            }

        try:
            ok, detail = check_smtp_connection(
                server=host,
                port=port,
                username=username,
                password=password,
                use_ssl=use_ssl,
                use_tls=use_tls,
                timeout=20,
                prefer_vps=True,
            )
        except Exception as exc:
            logger.exception("check_smtp_connection raised")
            ok, detail = False, f"SMTP probe error: {exc.__class__.__name__}"

        if ok:
            message = "Connection Successful"
            try:
                self._set_smtp_connection_status(STATUS_CONNECTED)
            except Exception:
                logger.exception("Failed to persist SMTP Connected status")
        else:
            message = self._safe_smtp_error(detail)
            try:
                self._set_smtp_connection_status(STATUS_FAILED)
            except Exception:
                logger.exception("Failed to persist SMTP Failed status")

        try:
            self._log_smtp_audit(
                "Tested SMTP Connection",
                detail={
                    "ok": ok,
                    "host": host,
                    "port": port,
                    "username": mask_email(username),
                    "from_email": mask_email(from_email) if from_email and "@" in from_email else None,
                },
            )
        except Exception:
            logger.exception("SMTP test audit failed")

        result = self.get_provider_settings_masked("smtp")
        result.update({"ok": ok, "message": message, "clear_secrets": True})
        return result

    def _log_smtp_audit(self, action: str, *, detail: dict[str, Any] | None = None) -> None:
        try:
            AuditService().log(
                action_name=action[:100],
                entity_type="IntegrationSettings",
                entity_id=None,
                old_value=None,
                new_value=detail,
            )
        except Exception:
            logger.exception("AuditLog write failed for SMTP action=%s", action)

    @staticmethod
    def _safe_smtp_error(detail: str | None) -> str:
        text = (detail or "Connection failed").strip()
        # Strip any accidental credential fragments from library messages.
        lowered = text.lower()
        for needle in ("password", "passwd", "secret"):
            if needle in lowered and "@" not in text:
                return "Connection failed. Check host, port, username, and password."
        if len(text) > 220:
            text = text[:217] + "..."
        return text or "Connection failed"

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "on", "y"}

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
        return [k for k in WHATSAPP_SEND_REQUIRED_KEYS if not (cfg.get(k) or "").strip()]

    @staticmethod
    def _missing_labels(keys: list[str]) -> list[str]:
        labels = {
            "app_id": "Facebook App ID",
            "app_secret": "Facebook App Secret",
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
        if "fail" in s:
            return "failed"
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
