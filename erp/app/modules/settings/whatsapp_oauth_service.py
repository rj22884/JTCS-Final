"""Connect Meta OAuth + discovery/auto-fill for WhatsApp settings."""

from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urljoin

from flask import current_app, session, url_for

from app.modules.settings.crypto import encrypt_value
from app.modules.settings.repositories import IntegrationSettingsRepository
from app.modules.settings.services import IntegrationSettingsService
from app.modules.settings.whatsapp_meta_client import (
    DEFAULT_GRAPH_VERSION,
    MetaGraphError,
    WhatsAppMetaClient,
)

logger = logging.getLogger(__name__)

PROVIDER = "whatsapp_meta"
SESSION_OAUTH_STATE = "wa_meta_oauth_state"
SESSION_OAUTH_TOKEN = "wa_meta_oauth_token"
SESSION_OAUTH_VERSION = "wa_meta_oauth_version"

# Meta Graph object IDs are numeric strings. Access tokens are long opaque strings (often EAA...).
_META_OBJECT_ID_RE = re.compile(r"^\d{5,30}$")


class WhatsAppOAuthService:
    def __init__(
        self,
        settings: IntegrationSettingsService | None = None,
        repository: IntegrationSettingsRepository | None = None,
    ):
        self.settings = settings or IntegrationSettingsService()
        self.repository = repository or IntegrationSettingsRepository()

    def _cfg(self) -> dict[str, str]:
        return self.settings.get_provider_config_decrypted(PROVIDER)

    def default_webhook_url(self) -> str:
        base = (current_app.config.get("APP_BASE_URL") or "").rstrip("/") + "/"
        return urljoin(base, "admin/integrations/api/whatsapp/webhook")

    def default_oauth_redirect_uri(self) -> str:
        return url_for("integration_settings.api_whatsapp_oauth_callback", _external=True)

    def start_connect(self) -> dict[str, Any]:
        cfg = self._cfg()
        app_id = (cfg.get("app_id") or "").strip()
        app_secret = (cfg.get("app_secret") or "").strip()
        if not app_id or not app_secret:
            raise ValueError("Save App ID and App Secret before clicking Connect Facebook.")

        version = (cfg.get("graph_api_version") or DEFAULT_GRAPH_VERSION).strip() or DEFAULT_GRAPH_VERSION
        redirect_uri = (cfg.get("oauth_redirect_uri") or "").strip() or self.default_oauth_redirect_uri()
        state = secrets.token_urlsafe(24)
        session[SESSION_OAUTH_STATE] = state
        session[SESSION_OAUTH_VERSION] = version

        # Persist redirect URI + default graph version / webhook if empty (non-secrets only)
        self._upsert_plain("graph_api_version", version)
        self._upsert_plain("oauth_redirect_uri", redirect_uri)
        if not (cfg.get("webhook_url") or "").strip():
            self._upsert_plain("webhook_url", self.default_webhook_url())

        url = WhatsAppMetaClient.oauth_authorize_url(
            app_id=app_id,
            redirect_uri=redirect_uri,
            state=state,
        )
        return {"ok": True, "authorize_url": url, "redirect_uri": redirect_uri}

    def handle_callback(self, *, code: str | None, state: str | None, error: str | None) -> dict[str, Any]:
        if error:
            raise ValueError(f"Meta OAuth error: {error}")
        if not code:
            raise ValueError("Missing OAuth authorization code.")
        expected = session.get(SESSION_OAUTH_STATE)
        if not expected or state != expected:
            raise ValueError("Invalid OAuth state. Please try Connect Meta again.")

        cfg = self._cfg()
        app_id = (cfg.get("app_id") or "").strip()
        app_secret = (cfg.get("app_secret") or "").strip()
        redirect_uri = (cfg.get("oauth_redirect_uri") or "").strip() or self.default_oauth_redirect_uri()
        version = session.get(SESSION_OAUTH_VERSION) or cfg.get("graph_api_version") or DEFAULT_GRAPH_VERSION

        token_payload = WhatsAppMetaClient.exchange_code(
            app_id=app_id,
            app_secret=app_secret,
            redirect_uri=redirect_uri,
            code=code,
            graph_api_version=version,
        )
        access_token = (token_payload.get("access_token") or "").strip()
        if not access_token:
            raise ValueError("Meta did not return an access token.")
        if not self._looks_like_access_token(access_token):
            raise ValueError("Meta returned an unexpected token payload.")

        # Temporary OAuth token for discovery only in session.
        # Never write this token into Business ID, Phone Number ID, or Access Token fields.
        session[SESSION_OAUTH_TOKEN] = access_token
        session.pop(SESSION_OAUTH_STATE, None)

        client = WhatsAppMetaClient(access_token=access_token, graph_api_version=version)
        businesses = [
            {"id": bid, "name": (b.get("name") or "").strip()}
            for b in client.list_businesses()
            if (bid := self._as_meta_object_id(b.get("id")))
        ]
        self._set_status("Partial Configuration")
        return {
            "ok": True,
            "step": "select_business",
            "businesses": businesses,
            "message": "Meta authentication successful. Select a Business Account.",
        }

    def _oauth_client(self) -> WhatsAppMetaClient:
        token = (session.get(SESSION_OAUTH_TOKEN) or "").strip()
        cfg = self._cfg()
        # Prefer temporary OAuth token; fall back to saved permanent token for listing
        if not token:
            token = (cfg.get("access_token") or "").strip()
        if not token:
            raise ValueError("No Meta session token. Click Connect Meta again or save Access Token.")
        version = cfg.get("graph_api_version") or session.get(SESSION_OAUTH_VERSION) or DEFAULT_GRAPH_VERSION
        return WhatsAppMetaClient(access_token=token, graph_api_version=version)

    def list_businesses(self) -> dict[str, Any]:
        businesses = [
            {"id": bid, "name": (b.get("name") or "").strip()}
            for b in self._oauth_client().list_businesses()
            if (bid := self._as_meta_object_id(b.get("id")))
        ]
        return {"ok": True, "businesses": businesses}

    def select_business(self, business_id: str) -> dict[str, Any]:
        requested_id = self._as_meta_object_id(business_id)
        if not requested_id:
            raise ValueError("business_id must be a Meta Business ID (numeric Graph id).")

        client = self._oauth_client()
        try:
            biz = client.get_business(requested_id)
        except MetaGraphError as exc:
            raise ValueError(f"Unable to load Business from Meta: {exc}") from exc

        # Only persist the Graph Business `id` — never token / name / other fields.
        resolved_business_id = self._as_meta_object_id(biz.get("id"))
        if not resolved_business_id:
            # Leave blank — do not guess from request or token.
            logger.warning("Meta business response missing valid id for request=%s", requested_id)
            self._clear_plain("business_id")
            self._clear_plain("business_name")
            raise ValueError("Meta did not return a valid Business ID.")

        business_name = (biz.get("name") or "").strip()
        self._upsert_plain("business_id", resolved_business_id)
        if business_name:
            self._upsert_plain("business_name", business_name)
        else:
            self._clear_plain("business_name")

        wabas = [
            {
                "id": wid,
                "name": (w.get("name") or "").strip(),
                "account_status": (w.get("account_review_status") or "").strip(),
            }
            for w in client.list_owned_wabas(resolved_business_id)
            if (wid := self._as_meta_object_id(w.get("id")))
        ]
        self._set_status("Partial Configuration")
        return {
            "ok": True,
            "step": "select_waba",
            "business": {"id": resolved_business_id, "name": business_name},
            "wabas": wabas,
        }

    def list_wabas(self, business_id: str | None = None) -> dict[str, Any]:
        cfg = self._cfg()
        bid = self._as_meta_object_id(business_id) or self._as_meta_object_id(cfg.get("business_id"))
        if not bid:
            raise ValueError("business_id must be a Meta Business ID (numeric Graph id).")
        wabas = [
            {
                "id": wid,
                "name": (w.get("name") or "").strip(),
                "account_status": (w.get("account_review_status") or "").strip(),
            }
            for w in self._oauth_client().list_owned_wabas(bid)
            if (wid := self._as_meta_object_id(w.get("id")))
        ]
        return {"ok": True, "wabas": wabas}

    def select_waba(self, waba_id: str) -> dict[str, Any]:
        requested_id = self._as_meta_object_id(waba_id)
        if not requested_id:
            raise ValueError("waba_id must be a Meta WhatsApp Business Account ID (numeric Graph id).")

        client = self._oauth_client()
        try:
            waba = client.get_waba(requested_id)
        except MetaGraphError as exc:
            raise ValueError(f"Unable to load WABA from Meta: {exc}") from exc

        resolved_waba_id = self._as_meta_object_id(waba.get("id"))
        if not resolved_waba_id:
            self._clear_plain("waba_id")
            raise ValueError("Meta did not return a valid WhatsApp Business Account ID.")

        account_status = (waba.get("account_review_status") or "").strip()
        self._upsert_plain("waba_id", resolved_waba_id)
        if account_status:
            self._upsert_plain("account_status", account_status)

        phones = [
            {
                "id": pid,
                "display_phone_number": (p.get("display_phone_number") or "").strip(),
                "display_name": (p.get("verified_name") or "").strip(),
                "quality_rating": (p.get("quality_rating") or "").strip(),
                "account_status": (p.get("code_verification_status") or "").strip(),
            }
            for p in client.list_phone_numbers(resolved_waba_id)
            if (pid := self._as_meta_object_id(p.get("id")))
        ]
        self._set_status("Partial Configuration")
        return {
            "ok": True,
            "step": "select_phone",
            "waba": {
                "id": resolved_waba_id,
                "name": (waba.get("name") or "").strip(),
                "account_status": account_status,
            },
            "phones": phones,
        }

    def list_phones(self, waba_id: str | None = None) -> dict[str, Any]:
        cfg = self._cfg()
        wid = self._as_meta_object_id(waba_id) or self._as_meta_object_id(cfg.get("waba_id"))
        if not wid:
            raise ValueError("waba_id must be a Meta WhatsApp Business Account ID (numeric Graph id).")
        phones = [
            {
                "id": pid,
                "display_phone_number": (p.get("display_phone_number") or "").strip(),
                "display_name": (p.get("verified_name") or "").strip(),
                "quality_rating": (p.get("quality_rating") or "").strip(),
                "account_status": (p.get("code_verification_status") or "").strip(),
            }
            for p in self._oauth_client().list_phone_numbers(wid)
            if (pid := self._as_meta_object_id(p.get("id")))
        ]
        return {"ok": True, "phones": phones}

    def select_phone(self, phone_number_id: str) -> dict[str, Any]:
        requested_id = self._as_meta_object_id(phone_number_id)
        if not requested_id:
            raise ValueError("phone_number_id must be a Meta Phone Number ID (numeric Graph id).")

        client = self._oauth_client()
        try:
            phone = client.get_phone(requested_id)
        except MetaGraphError as exc:
            raise ValueError(f"Unable to load Phone Number from Meta: {exc}") from exc

        # Only Graph phone `id` may populate Phone Number ID — never access token or display number.
        resolved_phone_id = self._as_meta_object_id(phone.get("id"))
        if not resolved_phone_id:
            self._clear_plain("phone_number_id")
            raise ValueError("Meta did not return a valid Phone Number ID.")

        cfg = self._cfg()
        version = (cfg.get("graph_api_version") or DEFAULT_GRAPH_VERSION).strip() or DEFAULT_GRAPH_VERSION
        webhook = (cfg.get("webhook_url") or "").strip() or self.default_webhook_url()

        self._upsert_plain("phone_number_id", resolved_phone_id)

        display_phone = (phone.get("display_phone_number") or "").strip()
        display_name = (phone.get("verified_name") or "").strip()
        quality = (phone.get("quality_rating") or "").strip()
        phone_status = (phone.get("code_verification_status") or "").strip()
        messaging_limit = (
            (phone.get("messaging_limit_tier") or "").strip()
            or str((phone.get("throughput") or {}).get("level") or "").strip()
        )

        if display_phone:
            self._upsert_plain("phone_number", display_phone)
        if display_name:
            self._upsert_plain("display_name", display_name)
        else:
            self._clear_plain("display_name")
        if quality:
            self._upsert_plain("quality_rating", quality)
        else:
            self._clear_plain("quality_rating")
        if messaging_limit:
            self._upsert_plain("messaging_limit", messaging_limit)
        if phone_status:
            self._upsert_plain("account_status", phone_status)

        self._upsert_plain("graph_api_version", version)
        self._upsert_plain("webhook_url", webhook)
        self._upsert_plain("last_sync_at", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

        # Exchange short-lived OAuth token → long-lived (~60 days) and store encrypted.
        token_note = self._persist_long_lived_token(cfg=cfg, version=version)

        # Best-effort: subscribe app to WABA webhooks so inbound messages flow.
        subscribe_note = ""
        waba_id = self._as_meta_object_id(cfg.get("waba_id"))
        if waba_id:
            try:
                # Re-read after token may have been upgraded
                live_cfg = self._cfg()
                live_token = (live_cfg.get("access_token") or session.get(SESSION_OAUTH_TOKEN) or "").strip()
                if live_token:
                    live_client = WhatsAppMetaClient(access_token=live_token, graph_api_version=version)
                    live_client.subscribe_app_to_waba(waba_id)
                    self._upsert_plain(
                        "webhook_subscribed_fields",
                        "messages, message_deliveries, message_reads, message_template_status_update",
                    )
                    subscribe_note = " Webhook app subscription requested on WABA."
            except Exception as exc:
                logger.warning("WABA subscribed_apps failed: %s", exc)
                subscribe_note = " (Webhook subscribe in Meta Dashboard if inbound fails.)"

        # Auto-generate verify token if empty
        if not (cfg.get("webhook_verify_token") or "").strip():
            try:
                self.settings.generate_whatsapp_verify_token()
            except Exception:
                logger.exception("Auto verify-token generation failed")

        has_token = bool((self._cfg().get("access_token") or "").strip())
        self._set_status("Connected" if has_token else "Partial Configuration")

        masked = self.settings.get_provider_settings_masked(PROVIDER)
        fv = dict(masked.get("field_values") or {})
        for id_key in ("business_id", "phone_number_id", "waba_id"):
            if self._looks_like_access_token(fv.get(id_key)):
                fv[id_key] = ""

        return {
            "ok": True,
            "step": "done",
            "message": (
                "WhatsApp account discovered and saved from Meta Graph."
                + token_note
                + subscribe_note
                + " Run Test Connection to verify."
            ),
            "field_values": fv,
            "missing": masked.get("missing") or [],
            "missing_labels": masked.get("missing_labels") or [],
            "status_code": masked.get("status_code"),
            "localhost_warning": self._localhost_warning(webhook),
        }

    def _persist_long_lived_token(self, *, cfg: dict[str, str], version: str) -> str:
        """Exchange session OAuth token for long-lived token and encrypt at rest."""
        short = (session.get(SESSION_OAUTH_TOKEN) or "").strip()
        if not short:
            return " Access Token was not auto-saved (session expired) — paste a System User token and Save."

        app_id = (cfg.get("app_id") or "").strip()
        app_secret = (cfg.get("app_secret") or "").strip()
        token_to_store = short
        expires_at = ""
        note = " Short-lived OAuth token stored."

        if app_id and app_secret:
            try:
                client = WhatsAppMetaClient(access_token=short, graph_api_version=version)
                exchanged = client.exchange_for_long_lived_token(
                    app_id=app_id,
                    app_secret=app_secret,
                    short_lived_token=short,
                    graph_api_version=version,
                )
                long_token = (exchanged.get("access_token") or "").strip()
                if long_token and self._looks_like_access_token(long_token):
                    token_to_store = long_token
                    note = " Long-lived Access Token saved (encrypted)."
                expires_in = exchanged.get("expires_in")
                if expires_in:
                    try:
                        exp = datetime.utcnow() + timedelta(seconds=int(expires_in))
                        expires_at = exp.strftime("%Y-%m-%d %H:%M:%S")
                    except (TypeError, ValueError):
                        expires_at = ""
            except MetaGraphError as exc:
                logger.warning("Long-lived token exchange failed: %s", exc)
                note = f" Using OAuth token (long-lived exchange failed: {exc})."
            except Exception as exc:
                logger.warning("Long-lived token exchange error: %s", exc)

        self._upsert_secret("access_token", token_to_store)
        if expires_at:
            self._upsert_plain("token_expires_at", expires_at)
        else:
            # Long-lived typically ~60 days when expires_in missing after failure
            self._upsert_plain(
                "token_expires_at",
                (datetime.utcnow() + timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S"),
            )

        # Persist debug_token expiry when possible
        try:
            client = WhatsAppMetaClient(access_token=token_to_store, graph_api_version=version)
            dbg = client.debug_token(app_id, app_secret, token_to_store)
            data = (dbg.get("data") or {}) if isinstance(dbg, dict) else {}
            exp_ts = data.get("expires_at") or data.get("data_access_expires_at")
            if exp_ts and int(exp_ts) > 0:
                self._upsert_plain(
                    "token_expires_at",
                    datetime.utcfromtimestamp(int(exp_ts)).strftime("%Y-%m-%d %H:%M:%S"),
                )
            if data.get("is_valid") is False:
                self._set_status("Invalid Token")
        except Exception:
            logger.debug("debug_token after OAuth skipped", exc_info=True)

        session.pop(SESSION_OAUTH_TOKEN, None)
        return note

    @staticmethod
    def _localhost_warning(webhook_url: str) -> str | None:
        url = (webhook_url or "").lower()
        if "localhost" in url or "127.0.0.1" in url:
            return (
                "Meta cannot reach localhost webhooks. "
                "Use ngrok or a public domain (APP_BASE_URL) for inbound messages."
            )
        return None

    def token_guide(self) -> dict[str, Any]:
        cfg = self._cfg()
        return {
            "ok": True,
            "title": "Generate Permanent Access Token",
            "steps": [
                "Open Meta Business Suite → Business Settings → Users → System Users.",
                "Create or select a System User, then click Generate New Token.",
                "Select your WhatsApp app and grant whatsapp_business_management and whatsapp_business_messaging.",
                "Copy the permanent token and paste it into Access Token on this page, then Save.",
                "App Secret stays in Meta Developer → App Settings → Basic (never share publicly).",
                f"Register OAuth Redirect URI in Meta App: {cfg.get('oauth_redirect_uri') or self.default_oauth_redirect_uri()}",
                f"Optional Webhook URL: {cfg.get('webhook_url') or self.default_webhook_url()}",
            ],
            "notes": [
                "Connect Meta exchanges a long-lived Access Token and saves it encrypted.",
                "For never-expiring production use, prefer a Meta System User permanent token (paste + Save).",
                "App Secret stays manual and is never displayed in clear text.",
                "Credentials are encrypted at rest and masked on screen.",
            ],
        }

    @classmethod
    def _as_meta_object_id(cls, value: Any) -> str | None:
        """Return Meta Graph object id or None. Never accepts access tokens."""
        if value is None:
            return None
        text = str(value).strip()
        if not text or cls._looks_like_access_token(text):
            return None
        if not _META_OBJECT_ID_RE.match(text):
            return None
        return text

    @staticmethod
    def _looks_like_access_token(value: Any) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        if text.startswith("EAA") or text.startswith("YA") or text.startswith("IG"):
            return True
        if len(text) >= 80 and re.search(r"[A-Za-z]", text) and re.search(r"\d", text):
            return True
        return False

    def _upsert_plain(self, key: str, value: str) -> None:
        from app.modules.settings.audit_service import IntegrationSettingsAuditService

        # Hard guard: never persist access tokens into ID / name settings keys.
        if key in {
            "business_id",
            "waba_id",
            "phone_number_id",
            "business_name",
            "display_name",
            "phone_number",
        }:
            if self._looks_like_access_token(value):
                logger.error("Refused to store token-like value into %s", key)
                return
        if key in {"business_id", "waba_id", "phone_number_id"}:
            if not self._as_meta_object_id(value):
                logger.error("Refused to store non-Meta-id value into %s", key)
                return
        if key == "access_token":
            # Use _upsert_secret for tokens after long-lived exchange.
            logger.error("Refused plain upsert for access_token — use _upsert_secret")
            return

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
            logger.exception("Integration audit log failed for %s", key)

    def _upsert_secret(self, key: str, value: str) -> None:
        """Encrypt and store secrets (access_token) with audit — used after OAuth exchange."""
        from app.modules.settings.audit_service import IntegrationSettingsAuditService

        if key not in {"access_token", "webhook_verify_token"}:
            raise ValueError(f"Unsupported secret key: {key}")
        if key == "access_token" and not self._looks_like_access_token(value):
            logger.error("Refused to store non-token value as access_token")
            return
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
            logger.exception("Integration audit log failed for secret %s", key)

    def _clear_plain(self, key: str) -> None:
        """Leave field blank when Graph value is unavailable — never guess."""
        from app.modules.settings.audit_service import IntegrationSettingsAuditService

        old = self.repository.get_encrypted_value(PROVIDER, key)
        stored = encrypt_value("")
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
            logger.exception("Integration audit clear failed for %s", key)

    def _set_status(self, status: str) -> None:
        from app.modules.settings.audit_service import IntegrationSettingsAuditService

        old = self.repository.get_encrypted_value(PROVIDER, "connection_status")
        stored = encrypt_value(status or "")
        self.repository.upsert(
            provider=PROVIDER,
            setting_key="connection_status",
            value_encrypted=stored,
            description=f"{PROVIDER}.connection_status",
        )
        try:
            IntegrationSettingsAuditService(self.repository).log_change(
                provider=PROVIDER,
                setting_key="connection_status",
                old_cipher=old,
                new_cipher=stored,
            )
        except Exception:
            logger.exception("Integration audit log failed for connection_status")

    def sanitize_stored_ids(self) -> None:
        """Clear ID fields that incorrectly contain token-like values."""
        cfg = self._cfg()
        for key in ("business_id", "waba_id", "phone_number_id"):
            raw = (cfg.get(key) or "").strip()
            if not raw:
                continue
            if self._looks_like_access_token(raw) or not self._as_meta_object_id(raw):
                logger.warning("Clearing invalid value from %s", key)
                self._clear_plain(key)
