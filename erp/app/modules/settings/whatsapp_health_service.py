"""WhatsApp connection health, metadata refresh, webhook subscribe, token expiry."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from app.modules.settings.crypto import encrypt_value, mask_access_token
from app.modules.settings.repositories import IntegrationSettingsRepository
from app.modules.settings.services import IntegrationSettingsService
from app.modules.settings.whatsapp_meta_client import MetaGraphError, WhatsAppMetaClient
from app.modules.settings.whatsapp_oauth_service import is_test_phone_display

logger = logging.getLogger(__name__)

PROVIDER = "whatsapp_meta"

DEFAULT_EVENTS = (
    "messages",
    "message_deliveries",
    "message_reads",
    "message_template_status_update",
)


class WhatsAppHealthService:
    def __init__(
        self,
        settings: IntegrationSettingsService | None = None,
        repository: IntegrationSettingsRepository | None = None,
    ):
        self.settings = settings or IntegrationSettingsService()
        self.repository = repository or IntegrationSettingsRepository()

    def _cfg(self) -> dict[str, str]:
        return self.settings.get_provider_config_decrypted(PROVIDER)

    def _client(self, cfg: dict[str, str] | None = None) -> WhatsAppMetaClient:
        cfg = cfg or self._cfg()
        token = (cfg.get("access_token") or "").strip()
        if not token:
            raise ValueError("Access Token is missing.")
        return WhatsAppMetaClient(
            access_token=token,
            graph_api_version=cfg.get("graph_api_version"),
        )

    def _upsert(self, key: str, value: str) -> None:
        from app.modules.settings.audit_service import IntegrationSettingsAuditService

        old = self.repository.get_encrypted_value(PROVIDER, key)
        stored = encrypt_value(value or "")
        self.repository.upsert(
            provider=PROVIDER,
            setting_key=key,
            value_encrypted=stored,
            description=f"{PROVIDER}.{key}",
        )
        try:
            IntegrationSettingsAuditService(self.repository).log_change(
                provider=PROVIDER,
                setting_key=key,
                old_cipher=old,
                new_cipher=stored,
            )
        except Exception:
            logger.exception("Audit failed for %s", key)

    def token_health(self) -> dict[str, Any]:
        """Validate access token via debug_token; update status / expiry."""
        cfg = self._cfg()
        token = (cfg.get("access_token") or "").strip()
        app_id = (cfg.get("app_id") or "").strip()
        app_secret = (cfg.get("app_secret") or "").strip()
        if not token:
            return {
                "ok": False,
                "status": "Disconnected",
                "status_code": "disconnected",
                "token_display": "",
                "expired": False,
                "message": "No Access Token configured.",
            }

        result: dict[str, Any] = {
            "ok": True,
            "status": cfg.get("connection_status") or "Partial Configuration",
            "status_code": "partial",
            "token_display": mask_access_token(token),
            "expired": False,
            "expires_at": (cfg.get("token_expires_at") or "").strip(),
            "scopes": [],
            "message": "",
        }

        # Local expiry check first
        exp_raw = (cfg.get("token_expires_at") or "").strip()
        if exp_raw:
            try:
                exp_dt = datetime.strptime(exp_raw[:19], "%Y-%m-%d %H:%M:%S")
                if exp_dt < datetime.utcnow():
                    result["ok"] = False
                    result["expired"] = True
                    result["status"] = "Token Expired"
                    result["status_code"] = "token_expired"
                    result["message"] = "Access Token has expired. Reconnect Meta or paste a new token."
                    self._upsert("connection_status", "Token Expired")
                    return result
            except ValueError:
                pass

        if not app_id or not app_secret:
            result["message"] = "App ID / App Secret required for live token validation."
            return result

        try:
            client = self._client(cfg)
            dbg = client.debug_token(app_id, app_secret, token)
            data = dbg.get("data") or {}
            is_valid = bool(data.get("is_valid"))
            scopes = data.get("scopes") or data.get("granular_scopes") or []
            if isinstance(scopes, list) and scopes and isinstance(scopes[0], dict):
                scopes = [s.get("scope") for s in scopes if s.get("scope")]
            result["scopes"] = scopes
            exp_ts = data.get("expires_at") or 0
            if exp_ts and int(exp_ts) > 0:
                exp_dt = datetime.utcfromtimestamp(int(exp_ts))
                result["expires_at"] = exp_dt.strftime("%Y-%m-%d %H:%M:%S")
                self._upsert("token_expires_at", result["expires_at"])
                if exp_dt < datetime.utcnow():
                    is_valid = False
                    result["expired"] = True

            if not is_valid:
                result["ok"] = False
                result["status"] = "Token Expired" if result["expired"] else "Invalid Token"
                result["status_code"] = "token_expired" if result["expired"] else "invalid_token"
                result["message"] = "Meta reports this Access Token is not valid."
                self._upsert("connection_status", result["status"])
            else:
                result["status"] = "Connected"
                result["status_code"] = "connected"
                result["message"] = "Access Token is valid."
                self._upsert("connection_status", "Connected")
        except MetaGraphError as exc:
            result["ok"] = False
            result["status"] = "Invalid Token"
            result["status_code"] = "invalid_token"
            result["message"] = str(exc)
            self._upsert("connection_status", "Invalid Token")
        except Exception as exc:
            result["ok"] = False
            result["status"] = "Disconnected"
            result["status_code"] = "disconnected"
            result["message"] = str(exc)

        return result

    def refresh_metadata(self) -> dict[str, Any]:
        """Re-fetch Business / WABA / Phone details from Graph and persist."""
        cfg = self._cfg()
        client = self._client(cfg)
        updated: dict[str, str] = {}

        business_id = (cfg.get("business_id") or "").strip()
        waba_id = (cfg.get("waba_id") or "").strip()
        phone_id = (cfg.get("phone_number_id") or "").strip()

        if business_id:
            try:
                biz = client.get_business(business_id)
                name = (biz.get("name") or "").strip()
                if name:
                    self._upsert("business_name", name)
                    updated["business_name"] = name
            except MetaGraphError as exc:
                logger.warning("refresh business failed: %s", exc)

        if waba_id:
            try:
                waba = client.get_waba(waba_id)
                status = (waba.get("account_review_status") or "").strip()
                if status:
                    self._upsert("account_status", status)
                    updated["account_status"] = status
            except MetaGraphError as exc:
                logger.warning("refresh waba failed: %s", exc)

        if phone_id:
            try:
                phone = client.get_phone(phone_id)
                remote_display = (phone.get("display_phone_number") or "").strip()
                if is_test_phone_display(remote_display):
                    logger.warning(
                        "refresh_metadata refusing to persist test phone %s for phone_number_id=%s",
                        remote_display,
                        phone_id,
                    )
                else:
                    mapping = {
                        "phone_number": remote_display,
                        "display_name": (phone.get("verified_name") or "").strip(),
                        "quality_rating": (phone.get("quality_rating") or "").strip(),
                        "messaging_limit": (
                            (phone.get("messaging_limit_tier") or "").strip()
                            or str((phone.get("throughput") or {}).get("level") or "").strip()
                        ),
                        "account_status": (phone.get("code_verification_status") or "").strip(),
                    }
                    for key, val in mapping.items():
                        if val:
                            self._upsert(key, val)
                            updated[key] = val
            except MetaGraphError as exc:
                logger.warning("refresh phone failed: %s", exc)

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self._upsert("last_sync_at", now)
        updated["last_sync_at"] = now

        health = self.token_health()
        masked = self.settings.get_provider_settings_masked(PROVIDER)
        return {
            "ok": True,
            "updated": updated,
            "token_health": health,
            "field_values": masked.get("field_values"),
            "status_code": masked.get("status_code"),
            "message": "Metadata refreshed from Meta Graph API.",
        }

    def webhook_info(self) -> dict[str, Any]:
        cfg = self._cfg()
        url = (cfg.get("webhook_url") or "").strip()
        host = ""
        try:
            host = urlparse(url).hostname or ""
        except Exception:
            pass
        localhost = host in {"localhost", "127.0.0.1"} or host.endswith(".local")
        subscribed = [
            s.strip()
            for s in (cfg.get("webhook_subscribed_fields") or "").split(",")
            if s.strip()
        ]
        return {
            "ok": True,
            "webhook_url": url,
            "verify_token_configured": bool((cfg.get("webhook_verify_token") or "").strip()),
            "localhost_warning": (
                "Meta cannot access localhost. Use ngrok or a public domain."
                if localhost
                else None
            ),
            "subscribed_fields": subscribed or list(DEFAULT_EVENTS),
            "available_fields": list(DEFAULT_EVENTS),
            "waba_id": (cfg.get("waba_id") or "").strip(),
        }

    def subscribe_webhooks(self) -> dict[str, Any]:
        cfg = self._cfg()
        waba_id = (cfg.get("waba_id") or "").strip()
        if not waba_id:
            raise ValueError("WABA ID is required to subscribe webhooks.")
        client = self._client(cfg)
        try:
            raw = client.subscribe_app_to_waba(waba_id)
        except MetaGraphError as exc:
            self._upsert("connection_status", "Webhook Failed")
            raise ValueError(f"Webhook subscribe failed: {exc}") from exc
        fields = ", ".join(DEFAULT_EVENTS)
        self._upsert("webhook_subscribed_fields", fields)
        return {
            "ok": True,
            "message": "App subscribed to WABA webhooks.",
            "subscribed_fields": list(DEFAULT_EVENTS),
            "raw": raw,
        }

    def unsubscribe_webhooks(self) -> dict[str, Any]:
        cfg = self._cfg()
        waba_id = (cfg.get("waba_id") or "").strip()
        if not waba_id:
            raise ValueError("WABA ID is required.")
        client = self._client(cfg)
        try:
            raw = client.unsubscribe_app_from_waba(waba_id)
        except MetaGraphError as exc:
            raise ValueError(f"Webhook unsubscribe failed: {exc}") from exc
        self._upsert("webhook_subscribed_fields", "")
        return {"ok": True, "message": "App unsubscribed from WABA webhooks.", "raw": raw}

    def list_subscribed_apps(self) -> dict[str, Any]:
        cfg = self._cfg()
        waba_id = (cfg.get("waba_id") or "").strip()
        if not waba_id:
            raise ValueError("WABA ID is required.")
        apps = self._client(cfg).list_subscribed_apps(waba_id)
        return {"ok": True, "apps": apps, "count": len(apps)}

    def account_card(self) -> dict[str, Any]:
        cfg = self._cfg()
        health = self.token_health()
        webhook = self.webhook_info()
        return {
            "ok": True,
            "business_name": cfg.get("business_name") or "",
            "business_id": cfg.get("business_id") or "",
            "phone_number": cfg.get("phone_number") or "",
            "display_name": cfg.get("display_name") or "",
            "quality_rating": cfg.get("quality_rating") or "",
            "messaging_limit": cfg.get("messaging_limit") or "",
            "account_status": cfg.get("account_status") or "",
            "profile_photo_url": cfg.get("profile_photo_url") or "",
            "connection_status": health.get("status") or cfg.get("connection_status") or "",
            "status_code": health.get("status_code") or "not_configured",
            "token_display": health.get("token_display") or "",
            "token_expires_at": health.get("expires_at") or cfg.get("token_expires_at") or "",
            "token_expired": bool(health.get("expired")),
            "last_sync_at": cfg.get("last_sync_at") or "",
            "webhook": webhook,
        }
