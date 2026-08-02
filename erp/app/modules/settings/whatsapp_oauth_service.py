"""Connect Meta OAuth + discovery/auto-fill for WhatsApp settings."""

from __future__ import annotations

import logging
import re
import secrets
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
            raise ValueError("Save App ID and App Secret before clicking Connect Meta.")

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

        display_name = (phone.get("verified_name") or "").strip()
        quality = (phone.get("quality_rating") or "").strip()
        phone_status = (phone.get("code_verification_status") or "").strip()
        if display_name:
            self._upsert_plain("display_name", display_name)
        else:
            self._clear_plain("display_name")
        if quality:
            self._upsert_plain("quality_rating", quality)
        else:
            self._clear_plain("quality_rating")
        if phone_status:
            self._upsert_plain("account_status", phone_status)

        self._upsert_plain("graph_api_version", version)
        self._upsert_plain("webhook_url", webhook)

        # Never auto-write Access Token or App Secret during Connect Meta.
        self._set_status("Partial Configuration")

        masked = self.settings.get_provider_settings_masked(PROVIDER)
        # Ensure UI cannot show a leaked token in ID fields even if old bad data existed.
        fv = dict(masked.get("field_values") or {})
        if self._looks_like_access_token(fv.get("business_id")):
            fv["business_id"] = ""
        if self._looks_like_access_token(fv.get("phone_number_id")):
            fv["phone_number_id"] = ""
        if self._looks_like_access_token(fv.get("waba_id")):
            fv["waba_id"] = ""

        return {
            "ok": True,
            "step": "done",
            "message": (
                "WhatsApp account details populated from Meta Graph IDs. "
                "Enter Permanent Access Token manually, then Test Connection."
            ),
            "field_values": fv,
            "missing": masked.get("missing") or [],
            "missing_labels": masked.get("missing_labels") or [],
            "status_code": masked.get("status_code"),
        }

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
                "Connect Meta uses a temporary login token for discovery only.",
                "ERP never auto-fills App Secret or Permanent Access Token.",
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
        if key in {"business_id", "waba_id", "phone_number_id", "business_name", "display_name"}:
            if self._looks_like_access_token(value):
                logger.error("Refused to store token-like value into %s", key)
                return
        if key in {"business_id", "waba_id", "phone_number_id"}:
            if not self._as_meta_object_id(value):
                logger.error("Refused to store non-Meta-id value into %s", key)
                return
        if key == "access_token":
            # Connect Meta must not auto-save tokens here; only explicit Save may set this.
            logger.error("Refused automatic write to access_token from Connect Meta flow")
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
