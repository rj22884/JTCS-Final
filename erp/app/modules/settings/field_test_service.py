"""Per-field live tests for Integration Settings.

Does not persist settings, does not change connection_status, and never
returns or logs secret/token values. Existing Test Connection flows are unchanged.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import re
import socket
import ssl
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.modules.settings.crypto import is_masked_or_unchanged
from app.modules.settings.models import PROVIDER_FIELDS, is_secret_key
from app.modules.settings.services import IntegrationSettingsService
from app.modules.settings.whatsapp_meta_client import (
    DEFAULT_GRAPH_VERSION,
    GRAPH_BASE,
    MetaGraphError,
    WhatsAppMetaClient,
)
from app.utils.smtp_health import check_smtp_connection, mask_email, open_smtp_connection

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_META_ID_RE = re.compile(r"^\d{5,30}$")
_TOKEN_RE = re.compile(r"(EAA[A-Za-z0-9]+|(?:ya29|sk-|sk-ant-|AIza)[A-Za-z0-9_\-]+)")
_SECRET_QS_RE = re.compile(
    r"(?i)(access_token|client_secret|api[_-]?key|password|auth(?:key|token)?|secret)=[^&\s]+"
)

# Fields that can be live-tested. Notes / status-only values are omitted.
_TESTABLE: dict[str, frozenset[str]] = {
    "whatsapp_meta": frozenset(
        {
            "business_name",
            "business_id",
            "app_id",
            "app_secret",
            "phone_number",
            "phone_number_id",
            "waba_id",
            "display_name",
            "quality_rating",
            "messaging_limit",
            "account_status",
            "profile_photo_url",
            "access_token",
            "token_expires_at",
            "graph_api_version",
            "webhook_verify_token",
            "webhook_url",
            "oauth_redirect_uri",
            "webhook_subscribed_fields",
        }
    ),
    "smtp": frozenset(
        {
            "host",
            "port",
            "username",
            "smtp_password",
            "from_email",
            "use_tls",
            "use_ssl",
        }
    ),
    "google": frozenset({"client_id", "client_secret", "api_key"}),
    "openai": frozenset({"api_key", "organization", "default_model"}),
    "gemini": frozenset({"api_key", "default_model"}),
    "claude": frozenset({"api_key", "default_model"}),
    "sms": frozenset({"api_key", "api_secret", "sender_id"}),
    "payment": frozenset({"merchant_id", "api_key", "api_secret"}),
    "cloud_storage": frozenset({"bucket_name", "access_key", "secret_key", "region"}),
    "google_drive": frozenset({"api_key", "api_secret", "endpoint_url"}),
    "google_calendar": frozenset({"api_key", "api_secret", "endpoint_url"}),
}

_GENERIC_TESTABLE = frozenset({"api_key", "api_secret", "endpoint_url", "client_secret"})

_AWS_REGIONS = frozenset(
    {
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "ap-south-1",
        "ap-south-2",
        "ap-southeast-1",
        "ap-southeast-2",
        "ap-northeast-1",
        "eu-west-1",
        "eu-west-2",
        "eu-central-1",
        "ap-east-1",
        "me-south-1",
        "sa-east-1",
        "ca-central-1",
    }
)


def testable_fields_map() -> dict[str, list[str]]:
    """provider -> sorted testable field keys (for the settings template)."""
    out: dict[str, list[str]] = {}
    for code, fields in PROVIDER_FIELDS.items():
        allowed = _TESTABLE.get(code) or _GENERIC_TESTABLE
        keys = [f["key"] for f in fields if f["key"] in allowed]
        if keys:
            out[code] = keys
    return out


def _ok(message: str) -> dict[str, Any]:
    return {"ok": True, "message": message, "error": ""}


def _fail(message: str) -> dict[str, Any]:
    return {"ok": False, "message": message, "error": message}


def _safe_error(message: str | None) -> str:
    text = str(message or "Validation failed").strip()
    text = _TOKEN_RE.sub("[redacted]", text)
    text = _SECRET_QS_RE.sub(r"\1=[redacted]", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*", "Bearer [redacted]", text)
    text = re.sub(r"\d{5,20}\|[A-Za-z0-9]+", "[redacted]", text)
    if len(text) > 240:
        text = text[:237] + "..."
    return text or "Validation failed"


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "y"}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


class IntegrationFieldTestService:
    def __init__(self, settings: IntegrationSettingsService | None = None):
        self.settings = settings or IntegrationSettingsService()

    def test_field(self, provider: str, field: str, posted: dict[str, Any] | None = None) -> dict[str, Any]:
        provider = (provider or "").strip()
        field = (field or "").strip()
        if provider not in PROVIDER_FIELDS:
            return _fail("Unknown integration provider.")
        allowed = set(testable_fields_map().get(provider) or [])
        if field not in allowed:
            return _fail("This field cannot be live-tested.")

        cfg = self._merge_cfg(provider, posted or {})
        logger.info("Integration field test provider=%s field=%s", provider, field)
        try:
            if provider == "whatsapp_meta":
                result = self._test_whatsapp(field, cfg)
            elif provider == "smtp":
                result = self._test_smtp(field, cfg)
            elif provider == "google":
                result = self._test_google(field, cfg)
            elif provider == "openai":
                result = self._test_openai(field, cfg)
            elif provider == "gemini":
                result = self._test_gemini(field, cfg)
            elif provider == "claude":
                result = self._test_claude(field, cfg)
            elif provider == "sms":
                result = self._test_sms(field, cfg)
            elif provider == "payment":
                result = self._test_payment(field, cfg)
            elif provider == "cloud_storage":
                result = self._test_cloud_storage(field, cfg)
            else:
                result = self._test_generic(provider, field, cfg)
        except MetaGraphError as exc:
            result = _fail(_safe_error(str(exc)))
        except Exception as exc:
            logger.exception("Field test failed provider=%s field=%s", provider, field)
            result = _fail(_safe_error(f"Unable to test this field ({exc.__class__.__name__})."))

        result["provider"] = provider
        result["field"] = field
        result["message"] = _safe_error(result.get("message"))
        result["error"] = "" if result.get("ok") else result["message"]
        return result

    def _merge_cfg(self, provider: str, posted: dict[str, Any]) -> dict[str, str]:
        stored = self.settings.get_provider_config_decrypted(provider)
        merged = {k: (v if v is not None else "") for k, v in stored.items()}
        allowed = {f["key"] for f in PROVIDER_FIELDS.get(provider) or []}
        for key, raw in posted.items():
            if key not in allowed:
                continue
            value = "" if raw is None else str(raw)
            if is_secret_key(key) and is_masked_or_unchanged(value):
                continue
            if is_secret_key(key):
                merged[key] = value.strip()
            else:
                merged[key] = value.strip()
        return merged

    # ------------------------------------------------------------------
    # WhatsApp / Meta
    # ------------------------------------------------------------------

    def _test_whatsapp(self, field: str, cfg: dict[str, str]) -> dict[str, Any]:
        handlers = {
            "app_id": self._wa_app_id,
            "app_secret": self._wa_app_secret,
            "access_token": self._wa_access_token,
            "business_id": self._wa_business_id,
            "business_name": self._wa_business_name,
            "waba_id": self._wa_waba_id,
            "phone_number_id": self._wa_phone_number_id,
            "phone_number": self._wa_phone_number,
            "display_name": self._wa_display_name,
            "quality_rating": self._wa_quality,
            "messaging_limit": self._wa_messaging_limit,
            "account_status": self._wa_account_status,
            "profile_photo_url": self._wa_profile_photo,
            "token_expires_at": self._wa_token_expires,
            "graph_api_version": self._wa_graph_version,
            "webhook_verify_token": self._wa_verify_token,
            "webhook_url": self._wa_webhook_url,
            "oauth_redirect_uri": self._wa_oauth_redirect,
            "webhook_subscribed_fields": self._wa_subscribed,
        }
        fn = handlers.get(field)
        if not fn:
            return _fail("This WhatsApp field cannot be live-tested.")
        return fn(cfg)

    def _wa_user_client(self, cfg: dict[str, str]) -> WhatsAppMetaClient | None:
        token = (cfg.get("access_token") or "").strip()
        if not token:
            return None
        return WhatsAppMetaClient(
            access_token=token,
            graph_api_version=cfg.get("graph_api_version") or DEFAULT_GRAPH_VERSION,
        )

    def _wa_require_id(self, value: str, label: str) -> str | None:
        text = (value or "").strip()
        if not text:
            return f"{label} is empty."
        if not _META_ID_RE.match(text):
            return f"{label} must be a Meta numeric object ID."
        return None

    def _wa_app_graph(self, cfg: dict[str, str], app_id: str) -> dict[str, Any]:
        secret = (cfg.get("app_secret") or "").strip()
        if not secret:
            raise MetaGraphError("App Secret is required to verify App ID with Meta.")
        ver = (cfg.get("graph_api_version") or DEFAULT_GRAPH_VERSION).strip() or DEFAULT_GRAPH_VERSION
        if not ver.startswith("v"):
            ver = f"v{ver}"
        app_token = f"{app_id}|{secret}"
        url = f"{GRAPH_BASE}/{ver}/{app_id}?{urlencode({'access_token': app_token, 'fields': 'id,name'})}"
        return WhatsAppMetaClient._http_get_json(url)

    def _wa_debug(self, cfg: dict[str, str]) -> dict[str, Any]:
        app_id = (cfg.get("app_id") or "").strip()
        secret = (cfg.get("app_secret") or "").strip()
        token = (cfg.get("access_token") or "").strip()
        if not app_id or not secret:
            raise MetaGraphError("App ID and App Secret are required for token debug.")
        if not token:
            raise MetaGraphError("Access Token is not configured.")
        client = WhatsAppMetaClient(
            access_token=token,
            graph_api_version=cfg.get("graph_api_version"),
        )
        data = client.debug_token(app_id, secret, token)
        return data.get("data") or {}

    def _wa_app_id(self, cfg: dict[str, str]) -> dict[str, Any]:
        err = self._wa_require_id(cfg.get("app_id") or "", "App ID")
        if err:
            return _fail(err)
        app = self._wa_app_graph(cfg, cfg["app_id"].strip())
        name = app.get("name") or app.get("id")
        if str(app.get("id") or "") != cfg["app_id"].strip():
            return _fail("Meta returned a different App ID — check the configured value.")
        return _ok(f"App ID is valid in Meta Graph ({name}).")

    def _wa_app_secret(self, cfg: dict[str, str]) -> dict[str, Any]:
        app_id = (cfg.get("app_id") or "").strip()
        secret = (cfg.get("app_secret") or "").strip()
        if not app_id:
            return _fail("App ID is required to verify App Secret.")
        if not secret:
            return _fail("App Secret is not configured.")
        app = self._wa_app_graph(cfg, app_id)
        return _ok(f"App Secret is valid for {app.get('name') or app_id}.")

    def _wa_access_token(self, cfg: dict[str, str]) -> dict[str, Any]:
        client = self._wa_user_client(cfg)
        if client is None:
            return _fail("Access Token is not configured.")
        me = client.get("/me", {"fields": "id,name"})
        info = {}
        try:
            info = self._wa_debug(cfg)
        except MetaGraphError:
            info = {}
        if info.get("is_valid") is False:
            return _fail("Access Token is invalid or expired (debug_token).")
        scopes = info.get("scopes") or []
        needed = {"whatsapp_business_management", "whatsapp_business_messaging", "business_management"}
        have = {s.lower() for s in scopes if isinstance(s, str)}
        missing = sorted(s for s in needed if s not in have)
        who = me.get("name") or me.get("id") or "token owner"
        if missing and have:
            return _fail(f"Token works as {who}, but missing permissions: {', '.join(missing)}.")
        if have:
            return _ok(f"Token valid for {who}. Permissions: {', '.join(sorted(have))}.")
        return _ok(f"Token is accepted by Graph API as {who}.")

    def _wa_business_id(self, cfg: dict[str, str]) -> dict[str, Any]:
        err = self._wa_require_id(cfg.get("business_id") or "", "Business ID")
        if err:
            return _fail(err)
        client = self._wa_user_client(cfg)
        if client is None:
            return _fail("Access Token is required to verify Business ID with Meta.")
        biz = client.get_business(cfg["business_id"].strip())
        return _ok(f"Business ID is valid: {biz.get('name') or biz.get('id')}.")

    def _wa_business_name(self, cfg: dict[str, str]) -> dict[str, Any]:
        name = (cfg.get("business_name") or "").strip()
        if not name:
            return _fail("Business Name is empty.")
        bid = (cfg.get("business_id") or "").strip()
        client = self._wa_user_client(cfg)
        if not bid or client is None:
            return _fail("Business ID and Access Token are required to verify Business Name.")
        biz = client.get_business(bid)
        remote = (biz.get("name") or "").strip()
        if remote.lower() != name.lower():
            return _fail(f"Does not match Meta business name ({remote or 'unknown'}).")
        return _ok(f"Business Name matches Meta ({remote}).")

    def _wa_waba_id(self, cfg: dict[str, str]) -> dict[str, Any]:
        err = self._wa_require_id(cfg.get("waba_id") or "", "WABA ID")
        if err:
            return _fail(err)
        client = self._wa_user_client(cfg)
        if client is None:
            return _fail("Access Token is required to verify WABA ID with Meta.")
        waba_id = cfg["waba_id"].strip()
        waba = client.get_waba(waba_id)
        bid = (cfg.get("business_id") or "").strip()
        if bid:
            owned = {str(x.get("id") or "") for x in client.list_owned_wabas(bid)}
            if waba_id not in owned:
                return _fail("WABA ID is valid but is not owned by the configured Business ID.")
        return _ok(
            f"WABA ID is valid: {waba.get('name') or waba_id}"
            f" ({waba.get('account_review_status') or 'status n/a'})."
        )

    def _wa_phone_number_id(self, cfg: dict[str, str]) -> dict[str, Any]:
        err = self._wa_require_id(cfg.get("phone_number_id") or "", "Phone Number ID")
        if err:
            return _fail(err)
        client = self._wa_user_client(cfg)
        if client is None:
            return _fail("Access Token is required to verify Phone Number ID with Meta.")
        phone_id = cfg["phone_number_id"].strip()
        phone = client.get_phone(phone_id)
        waba_id = (cfg.get("waba_id") or "").strip()
        if waba_id:
            phones = {str(x.get("id") or "") for x in client.list_phone_numbers(waba_id)}
            if phone_id not in phones:
                return _fail("Phone Number ID is valid but is not linked to the configured WABA.")
        return _ok(
            f"Phone Number ID is valid: {phone.get('display_phone_number') or phone_id}"
            f" ({phone.get('verified_name') or 'no verified name'})."
        )

    def _wa_phone_number(self, cfg: dict[str, str]) -> dict[str, Any]:
        number = (cfg.get("phone_number") or "").strip()
        if not number:
            return _fail("Phone Number is empty.")
        client = self._wa_user_client(cfg)
        phone_id = (cfg.get("phone_number_id") or "").strip()
        if client is None or not phone_id:
            return _fail("Phone Number ID and Access Token are required to verify this number.")
        phone = client.get_phone(phone_id)
        remote = phone.get("display_phone_number") or ""
        if _digits(remote) != _digits(number):
            return _fail(f"Does not match Meta number on this Phone Number ID ({remote or 'unknown'}).")
        return _ok(f"Phone Number matches Meta ({remote}).")

    def _wa_display_name(self, cfg: dict[str, str]) -> dict[str, Any]:
        name = (cfg.get("display_name") or "").strip()
        if not name:
            return _fail("Display Name is empty.")
        client = self._wa_user_client(cfg)
        phone_id = (cfg.get("phone_number_id") or "").strip()
        if client is None or not phone_id:
            return _fail("Phone Number ID and Access Token are required to verify Display Name.")
        phone = client.get_phone(phone_id)
        remote = (phone.get("verified_name") or "").strip()
        if remote.lower() != name.lower():
            return _fail(f"Does not match Meta verified name ({remote or 'unknown'}).")
        return _ok(f"Display Name matches Meta ({remote}).")

    def _wa_quality(self, cfg: dict[str, str]) -> dict[str, Any]:
        value = (cfg.get("quality_rating") or "").strip()
        if not value:
            return _fail("Quality Rating is empty.")
        client = self._wa_user_client(cfg)
        phone_id = (cfg.get("phone_number_id") or "").strip()
        if client is None or not phone_id:
            return _fail("Phone Number ID and Access Token are required to verify Quality Rating.")
        phone = client.get_phone(phone_id)
        remote = str(phone.get("quality_rating") or "").strip()
        if remote.lower() != value.lower():
            return _fail(f"Meta quality rating is {remote or 'unknown'}, not {value}.")
        return _ok(f"Quality Rating matches Meta ({remote}).")

    def _wa_messaging_limit(self, cfg: dict[str, str]) -> dict[str, Any]:
        value = (cfg.get("messaging_limit") or "").strip()
        if not value:
            return _fail("Messaging Limit is empty.")
        client = self._wa_user_client(cfg)
        phone_id = (cfg.get("phone_number_id") or "").strip()
        if client is None or not phone_id:
            return _fail("Phone Number ID and Access Token are required to verify Messaging Limit.")
        phone = client.get_phone(phone_id)
        remote = str(phone.get("messaging_limit_tier") or phone.get("throughput") or "").strip()
        if isinstance(phone.get("throughput"), dict):
            remote = str(phone["throughput"].get("level") or remote)
        if remote.lower() != value.lower() and value.lower() not in remote.lower():
            return _fail(f"Meta messaging limit is {remote or 'unknown'}, not {value}.")
        return _ok(f"Messaging Limit matches Meta ({remote}).")

    def _wa_account_status(self, cfg: dict[str, str]) -> dict[str, Any]:
        value = (cfg.get("account_status") or "").strip()
        if not value:
            return _fail("Account Status is empty.")
        client = self._wa_user_client(cfg)
        waba_id = (cfg.get("waba_id") or "").strip()
        if client is None or not waba_id:
            return _fail("WABA ID and Access Token are required to verify Account Status.")
        waba = client.get_waba(waba_id)
        remote = str(waba.get("account_review_status") or "").strip()
        if remote.lower() != value.lower() and value.lower() not in remote.lower():
            return _fail(f"Meta account status is {remote or 'unknown'}, not {value}.")
        return _ok(f"Account Status matches Meta ({remote}).")

    def _wa_profile_photo(self, cfg: dict[str, str]) -> dict[str, Any]:
        url = (cfg.get("profile_photo_url") or "").strip()
        if not url:
            return _fail("Profile Photo URL is empty.")
        return self._probe_url(url, label="Profile photo")

    def _wa_token_expires(self, cfg: dict[str, str]) -> dict[str, Any]:
        stored = (cfg.get("token_expires_at") or "").strip()
        info = self._wa_debug(cfg)
        if info.get("is_valid") is False:
            return _fail("Access Token is invalid or expired.")
        exp_ts = info.get("expires_at") or 0
        if not exp_ts or int(exp_ts) <= 0:
            if stored:
                return _ok("Token has no expiry (likely a permanent system-user token).")
            return _ok("Token is valid and has no expiry timestamp.")
        remote = datetime.fromtimestamp(int(exp_ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if stored and stored[:16] != remote[:16]:
            return _fail(f"Stored expiry {stored} does not match Meta ({remote} UTC).")
        if int(exp_ts) <= int(datetime.now(tz=timezone.utc).timestamp()):
            return _fail(f"Token already expired at {remote} UTC.")
        return _ok(f"Token expiry confirmed: {remote} UTC.")

    def _wa_graph_version(self, cfg: dict[str, str]) -> dict[str, Any]:
        ver = (cfg.get("graph_api_version") or "").strip()
        if not ver:
            return _fail("Graph API Version is empty.")
        if not ver.startswith("v"):
            ver = f"v{ver}"
        if not re.match(r"^v\d{1,2}\.\d{1,2}$", ver):
            return _fail("Graph API Version must look like v21.0.")
        url = f"{GRAPH_BASE}/{ver}/me?{urlencode({'access_token': 'invalid', 'fields': 'id'})}"
        try:
            WhatsAppMetaClient._http_get_json(url)
        except MetaGraphError as exc:
            msg = str(exc).lower()
            if "invalid api version" in msg or "unsupported get request" in msg and "version" in msg:
                return _fail(f"{ver} is not a valid Graph API version.")
            if "access token" in msg or "oauth" in msg or "session" in msg:
                client = self._wa_user_client(cfg)
                if client is not None:
                    live = WhatsAppMetaClient(
                        access_token=client.access_token,
                        graph_api_version=ver,
                    )
                    me = live.get("/me", {"fields": "id"})
                    return _ok(f"{ver} is accepted by Graph (id {me.get('id') or 'ok'}).")
                return _ok(f"{ver} is a recognized Graph API version.")
            return _fail(_safe_error(str(exc)))
        return _ok(f"{ver} responded successfully.")

    def _wa_verify_token(self, cfg: dict[str, str]) -> dict[str, Any]:
        token = (cfg.get("webhook_verify_token") or "").strip()
        if not token:
            return _fail("Webhook Verify Token is not configured. Use Generate Verify Token.")
        if len(token) < 16:
            return _fail("Verify token is too short for Meta webhook verification.")
        url = (cfg.get("webhook_url") or "").strip()
        if url and "/admin/integrations/api/whatsapp/webhook" in url:
            return _ok("Stored verify token is present and would match Meta hub.verify_token.")
        return _ok("Stored verify token is present and long enough for Meta verification.")

    def _wa_webhook_url(self, cfg: dict[str, str]) -> dict[str, Any]:
        url = (cfg.get("webhook_url") or "").strip()
        if not url:
            return _fail("Webhook URL is empty.")
        lowered = url.lower()
        if "localhost" in lowered or "127.0.0.1" in lowered:
            return _fail("Meta cannot reach localhost. Use a public HTTPS URL or ngrok.")
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return _fail("Webhook URL must use https so Meta can subscribe.")
        probe = self._probe_url(url, label="Webhook")
        if not probe["ok"]:
            return probe
        return _ok("Webhook host is reachable over HTTPS.")

    def _wa_oauth_redirect(self, cfg: dict[str, str]) -> dict[str, Any]:
        url = (cfg.get("oauth_redirect_uri") or "").strip()
        if not url:
            return _fail("OAuth Redirect URI is empty.")
        parsed = urlparse(url)
        if parsed.scheme not in {"https", "http"}:
            return _fail("OAuth Redirect URI must be http or https.")
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
            return _fail("OAuth Redirect URI must use https in production.")
        if "oauth/callback" not in (parsed.path or ""):
            return _fail("URI path should be the ERP WhatsApp OAuth callback.")
        if parsed.hostname in {"localhost", "127.0.0.1"}:
            return _ok("Redirect URI format is valid (localhost — Meta app must allow it).")
        probe = self._probe_url(url, label="OAuth redirect")
        if probe["ok"]:
            return _ok("OAuth Redirect host is reachable. Confirm the same URI is listed in Meta App settings.")
        hint = probe.get("message") or "Host is not reachable."
        return _fail(f"{hint} Confirm this URI is added in Meta App → Valid OAuth Redirect URIs.")

    def _wa_subscribed(self, cfg: dict[str, str]) -> dict[str, Any]:
        client = self._wa_user_client(cfg)
        waba_id = (cfg.get("waba_id") or "").strip()
        if client is None or not waba_id:
            return _fail("WABA ID and Access Token are required to verify webhook subscriptions.")
        apps = client.list_subscribed_apps(waba_id)
        if not apps:
            return _fail("No apps are subscribed on this WABA. Use Resubscribe.")
        stored = [x.strip() for x in (cfg.get("webhook_subscribed_fields") or "").split(",") if x.strip()]
        labels = [str(a.get("whatsapp_business_api_data", {}).get("id") or a.get("id") or "app") for a in apps[:4]]
        extra = f" Stored events: {', '.join(stored)}." if stored else ""
        return _ok(f"{len(apps)} app(s) subscribed on WABA ({', '.join(labels)}).{extra}")

    # ------------------------------------------------------------------
    # SMTP
    # ------------------------------------------------------------------

    def _test_smtp(self, field: str, cfg: dict[str, str]) -> dict[str, Any]:
        host = (cfg.get("host") or "").strip()
        port_raw = (cfg.get("port") or "").strip()
        username = (cfg.get("username") or "").strip()
        password = (cfg.get("smtp_password") or "").strip()
        from_email = (cfg.get("from_email") or "").strip()
        use_tls = _as_bool(cfg.get("use_tls"))
        use_ssl = _as_bool(cfg.get("use_ssl"))
        if not use_tls and not use_ssl:
            use_ssl = True
        port = 0
        if port_raw:
            try:
                port = int(float(port_raw))
            except ValueError:
                port = 0

        if field == "host":
            if not host:
                return _fail("SMTP Host is empty.")
            return self._tcp_connect(host, port or 465, label="SMTP host")
        if field == "port":
            if port < 1 or port > 65535:
                return _fail("Port must be between 1 and 65535.")
            if not host:
                return _fail("SMTP Host is required to test this port.")
            return self._tcp_connect(host, port, label=f"SMTP port {port}")
        if field == "username":
            if not username:
                return _fail("Username is empty.")
            if not _EMAIL_RE.match(username):
                return _fail("Username must be a mailbox email (e.g. admin@jtcsxpert.com).")
            if not password:
                return _fail("Password is required to verify Username with the SMTP server.")
            ok, detail = check_smtp_connection(
                server=host, port=port or 465, username=username, password=password,
                use_ssl=use_ssl, use_tls=use_tls, timeout=18, prefer_vps=True,
            )
            if ok:
                return _ok(f"SMTP accepted username {mask_email(username)}.")
            return _fail(_safe_error(detail))
        if field == "smtp_password":
            if not password:
                return _fail("Password is not configured.")
            if not host or not username:
                return _fail("Host and Username are required to verify the password.")
            ok, detail = check_smtp_connection(
                server=host, port=port or 465, username=username, password=password,
                use_ssl=use_ssl, use_tls=use_tls, timeout=18, prefer_vps=True,
            )
            if ok:
                return _ok("SMTP authentication succeeded.")
            return _fail(_safe_error(detail))
        if field == "from_email":
            if not from_email:
                return _fail("From Email is empty.")
            if not _EMAIL_RE.match(from_email):
                return _fail("From Email must be a real address (not a display name).")
            if not password or not host or not username:
                return _fail("Host, Username, and Password are required to verify From Email with SMTP.")
            try:
                with open_smtp_connection(
                    server=host, port=port or 465, username=username, password=password,
                    use_ssl=use_ssl, use_tls=use_tls, timeout=18, prefer_vps=True,
                ) as client:
                    code, _resp = client.mail(from_email)
                if int(code) >= 400:
                    return _fail(f"SMTP rejected From Email (code {code}).")
                return _ok(f"SMTP accepted From Email {mask_email(from_email)}.")
            except Exception as exc:
                return _fail(_safe_error(f"From Email probe failed: {exc}"))
        if field in {"use_tls", "use_ssl"}:
            if not host:
                return _fail("SMTP Host is required to test encryption.")
            want_ssl = field == "use_ssl" and use_ssl
            want_tls = field == "use_tls" and use_tls
            if field == "use_ssl" and not use_ssl:
                return _ok("SSL is off — skipped live SSL handshake.")
            if field == "use_tls" and not use_tls:
                return _ok("TLS is off — skipped STARTTLS handshake.")
            if want_ssl:
                return self._tls_handshake(host, port or 465, label="SMTP SSL")
            return self._smtp_starttls(host, port or 587)
        return _fail("This SMTP field cannot be live-tested.")

    # ------------------------------------------------------------------
    # Google / AI / payment / storage / generic
    # ------------------------------------------------------------------

    def _test_google(self, field: str, cfg: dict[str, str]) -> dict[str, Any]:
        client_id = (cfg.get("client_id") or "").strip()
        secret = (cfg.get("client_secret") or "").strip()
        api_key = (cfg.get("api_key") or "").strip()
        if field == "client_id":
            if not client_id:
                return _fail("Client ID is empty.")
            if "apps.googleusercontent.com" not in client_id:
                return _fail("Client ID should look like a Google OAuth client (*.apps.googleusercontent.com).")
            if not secret:
                return _fail("Client Secret is required to verify Client ID with Google.")
            return self._google_oauth_client(client_id, secret)
        if field == "client_secret":
            if not secret:
                return _fail("Client Secret is not configured.")
            if not client_id:
                return _fail("Client ID is required to verify Client Secret.")
            return self._google_oauth_client(client_id, secret)
        if field == "api_key":
            if not api_key:
                return _fail("API Key is not configured.")
            return self._google_api_key(api_key)
        return _fail("This Google field cannot be live-tested.")

    def _google_oauth_client(self, client_id: str, client_secret: str) -> dict[str, Any]:
        body = urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "code": "jtcs-field-test-invalid-code",
                "grant_type": "authorization_code",
                "redirect_uri": "https://127.0.0.1/oauth/callback",
            }
        ).encode("utf-8")
        status, payload, raw_err = self._http_json(
            "https://oauth2.googleapis.com/token",
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            data=body,
        )
        err = str((payload or {}).get("error") or raw_err or "")
        # invalid_grant / redirect_uri_mismatch => client_id+secret accepted
        if err in {"invalid_grant", "redirect_uri_mismatch", "invalid_request"}:
            return _ok("Google accepted Client ID and Client Secret.")
        if err in {"invalid_client", "unauthorized_client"}:
            return _fail("Google rejected Client ID / Client Secret.")
        if status == 200:
            return _ok("Google OAuth token endpoint accepted the client.")
        return _fail(_safe_error(err or f"Google OAuth probe failed (HTTP {status})."))

    def _google_api_key(self, api_key: str) -> dict[str, Any]:
        status, payload, raw_err = self._http_json(
            "https://www.googleapis.com/drive/v3/about?fields=kind&key=" + api_key,
            headers={"Accept": "application/json"},
        )
        err = ((payload or {}).get("error") or {})
        reason = ""
        if isinstance(err, dict):
            errors = err.get("errors") or []
            if errors and isinstance(errors[0], dict):
                reason = str(errors[0].get("reason") or "")
            reason = reason or str(err.get("status") or err.get("message") or "")
        if reason in {"keyInvalid", "API_KEY_INVALID", "invalid"} or "key invalid" in (raw_err or "").lower():
            return _fail("Google rejected this API Key.")
        if status in {200, 401, 403}:
            return _ok("Google API Key is recognized (Drive API responded).")
        return _fail(_safe_error(raw_err or reason or f"Google API Key probe failed (HTTP {status})."))

    def _test_openai(self, field: str, cfg: dict[str, str]) -> dict[str, Any]:
        key = (cfg.get("api_key") or "").strip()
        if not key:
            return _fail("OpenAI API Key is not configured.")
        headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
        org = (cfg.get("organization") or "").strip()
        if field == "organization":
            if not org:
                return _fail("Organization is empty.")
            headers["OpenAI-Organization"] = org
        if field == "default_model":
            model = (cfg.get("default_model") or "").strip()
            if not model:
                return _fail("Default Model is empty.")
            status, payload, raw_err = self._http_json(
                f"https://api.openai.com/v1/models/{model}",
                headers=headers,
            )
            if status == 200:
                return _ok(f"OpenAI model '{model}' is available.")
            if status == 401:
                return _fail("OpenAI API Key was rejected.")
            if status == 404:
                return _fail(f"OpenAI does not have model '{model}' for this key.")
            return _fail(_safe_error(raw_err or f"OpenAI model probe failed (HTTP {status})."))
        status, payload, raw_err = self._http_json("https://api.openai.com/v1/models", headers=headers)
        if status == 200:
            count = len((payload or {}).get("data") or [])
            if field == "organization":
                return _ok(f"OpenAI accepted organization {org} ({count} models).")
            return _ok(f"OpenAI API Key is valid ({count} models visible).")
        if status == 401:
            return _fail("OpenAI rejected the API Key" + (" or Organization." if field == "organization" else "."))
        return _fail(_safe_error(raw_err or f"OpenAI probe failed (HTTP {status})."))

    def _test_gemini(self, field: str, cfg: dict[str, str]) -> dict[str, Any]:
        key = (cfg.get("api_key") or "").strip()
        if not key:
            return _fail("Gemini API Key is not configured.")
        status, payload, raw_err = self._http_json(
            "https://generativelanguage.googleapis.com/v1beta/models?key=" + key,
            headers={"Accept": "application/json"},
        )
        if status == 200:
            models = [str(m.get("name") or "") for m in (payload or {}).get("models") or []]
            if field == "default_model":
                model = (cfg.get("default_model") or "").strip()
                if not model:
                    return _fail("Default Model is empty.")
                needle = model if model.startswith("models/") else f"models/{model}"
                if any(needle == m or m.endswith("/" + model) or model in m for m in models):
                    return _ok(f"Gemini model '{model}' is available.")
                return _fail(f"Gemini key works, but model '{model}' was not listed.")
            return _ok(f"Gemini API Key is valid ({len(models)} models).")
        if status in {400, 401, 403}:
            return _fail("Gemini rejected this API Key.")
        return _fail(_safe_error(raw_err or f"Gemini probe failed (HTTP {status})."))

    def _test_claude(self, field: str, cfg: dict[str, str]) -> dict[str, Any]:
        key = (cfg.get("api_key") or "").strip()
        if not key:
            return _fail("Claude API Key is not configured.")
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Accept": "application/json",
        }
        status, payload, raw_err = self._http_json("https://api.anthropic.com/v1/models", headers=headers)
        if status == 200:
            models = [str(m.get("id") or "") for m in (payload or {}).get("data") or []]
            if field == "default_model":
                model = (cfg.get("default_model") or "").strip()
                if not model:
                    return _fail("Default Model is empty.")
                if model in models or any(model in m for m in models):
                    return _ok(f"Claude model '{model}' is available.")
                return _fail(f"Claude key works, but model '{model}' was not listed.")
            return _ok(f"Claude API Key is valid ({len(models)} models).")
        if status in {401, 403}:
            return _fail("Claude rejected this API Key.")
        return _fail(_safe_error(raw_err or f"Claude probe failed (HTTP {status})."))

    def _test_sms(self, field: str, cfg: dict[str, str]) -> dict[str, Any]:
        provider_name = (cfg.get("provider_name") or "").strip().lower()
        key = (cfg.get("api_key") or "").strip()
        secret = (cfg.get("api_secret") or "").strip()
        sender = (cfg.get("sender_id") or "").strip()
        if field == "sender_id":
            if not sender:
                return _fail("Sender ID is empty.")
            if not re.match(r"^[A-Za-z0-9]{3,11}$", sender):
                return _fail("Sender ID should be 3–11 alphanumeric characters.")
            if not key:
                return _fail("API Key is required to verify Sender ID with the SMS gateway.")
        if "msg91" in provider_name and key:
            status, payload, raw_err = self._http_json(
                "https://control.msg91.com/api/v5/wallet/credits",
                headers={"Accept": "application/json", "authkey": key},
            )
            if status == 200 and (payload or {}).get("type") != "error":
                if field == "sender_id":
                    return _ok("MSG91 accepted the API Key; Sender ID format is valid.")
                return _ok("MSG91 accepted the API Key.")
            return _fail(_safe_error(raw_err or "MSG91 rejected these credentials."))
        if "fast2sms" in provider_name and key:
            status, payload, raw_err = self._http_json(
                "https://www.fast2sms.com/dev/wallet",
                headers={"Accept": "application/json", "authorization": key},
            )
            if status == 200 and str((payload or {}).get("return")).lower() in {"true", "1"}:
                return _ok("Fast2SMS accepted the API Key.")
            return _fail(_safe_error(raw_err or "Fast2SMS rejected these credentials."))
        if field == "sender_id":
            return _fail("Live Sender ID check needs a known provider name (MSG91 / Fast2SMS).")
        if not key:
            return _fail("API Key is not configured.")
        return _fail(
            "Live SMS verification needs a known provider name (MSG91 / Fast2SMS) "
            "or an endpoint URL. Credentials were not sent to an unknown gateway."
        )

    def _test_payment(self, field: str, cfg: dict[str, str]) -> dict[str, Any]:
        gateway = (cfg.get("gateway_name") or "").strip().lower()
        key = (cfg.get("api_key") or "").strip()
        secret = (cfg.get("api_secret") or "").strip()
        merchant = (cfg.get("merchant_id") or "").strip()
        if field == "webhook_secret":
            if not (cfg.get("webhook_secret") or "").strip():
                return _fail("Webhook Secret is not configured.")
            return _ok("Webhook Secret is stored. It is verified when the gateway posts a signed webhook.")
        if key.startswith("rzp_") or "razorpay" in gateway:
            if field == "merchant_id" and not merchant:
                return _fail("Merchant ID is empty.")
            if not key or not secret:
                return _fail("Razorpay Key and Secret are required for a live check.")
            token = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
            status, payload, raw_err = self._http_json(
                "https://api.razorpay.com/v1/payments?count=1",
                headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
            )
            if status == 200:
                if field == "merchant_id":
                    return _ok("Razorpay credentials are valid. Merchant ID is stored with this key.")
                return _ok("Razorpay API credentials are valid.")
            return _fail(_safe_error(raw_err or "Razorpay rejected these credentials."))
        if key.startswith("sk_") or "stripe" in gateway:
            if not key:
                return _fail("Stripe secret key is not configured.")
            status, payload, raw_err = self._http_json(
                "https://api.stripe.com/v1/balance",
                headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            )
            if status == 200:
                return _ok("Stripe API key is valid.")
            return _fail(_safe_error(raw_err or "Stripe rejected this API key."))
        if field == "merchant_id":
            if not merchant:
                return _fail("Merchant ID is empty.")
            return _fail("Live merchant check needs a known gateway (Razorpay / Stripe).")
        return _fail("Live payment check needs gateway name Razorpay or Stripe (or rzp_/sk_ keys).")

    def _test_cloud_storage(self, field: str, cfg: dict[str, str]) -> dict[str, Any]:
        bucket = (cfg.get("bucket_name") or "").strip()
        access_key = (cfg.get("access_key") or "").strip()
        secret = (cfg.get("secret_key") or "").strip()
        region = (cfg.get("region") or "").strip() or "us-east-1"
        provider_name = (cfg.get("provider_name") or "").strip().lower()

        if field == "region":
            if not region:
                return _fail("Region is empty.")
            if access_key and secret and access_key.startswith("AKIA"):
                return self._aws_sts(access_key, secret, region)
            if region in _AWS_REGIONS:
                return _ok(f"Region '{region}' is a valid AWS region.")
            if region.startswith(("us-", "ap-", "eu-", "sa-", "ca-", "me-")):
                return _fail(f"'{region}' is not a recognized AWS region.")
            return _ok(f"Region '{region}' is stored. Add AWS keys to verify it live.")

        if field == "bucket_name":
            if not bucket:
                return _fail("Bucket / Container is empty.")
            if not re.match(r"^[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]$", bucket):
                return _fail("Bucket name is not a valid S3-style name.")
            host = f"{bucket}.s3.{region}.amazonaws.com" if region != "us-east-1" else f"{bucket}.s3.amazonaws.com"
            status, _payload, raw_err = self._http_json(
                f"https://{host}/",
                method="HEAD",
                timeout=10,
            )
            if status in {200, 204, 301, 307, 403}:
                return _ok(f"S3 responded for bucket '{bucket}' (HTTP {status}).")
            if status == 404:
                return _fail(f"S3 has no bucket named '{bucket}' in {region}.")
            return _fail(_safe_error(raw_err or f"S3 bucket probe failed (HTTP {status})."))

        if field in {"access_key", "secret_key"}:
            if not access_key:
                return _fail("Access Key is not configured.")
            if not secret:
                return _fail("Secret Key is required to verify Access Key with AWS STS.")
            if not access_key.startswith("AKIA") and "aws" not in provider_name:
                return _fail("Live key check is implemented for AWS (AKIA…).")
            return self._aws_sts(access_key, secret, region)
        return _fail("This storage field cannot be live-tested.")

    def _aws_sts(self, access_key: str, secret_key: str, region: str) -> dict[str, Any]:
        host = "sts.amazonaws.com" if region == "us-east-1" else f"sts.{region}.amazonaws.com"
        amz_date, datestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ"), datetime.now(tz=timezone.utc).strftime("%Y%m%d")
        canonical_query = "Action=GetCallerIdentity&Version=2011-06-15"
        canonical_headers = f"host:{host}\nx-amz-date:{amz_date}\n"
        signed_headers = "host;x-amz-date"
        payload_hash = hashlib.sha256(b"").hexdigest()
        canonical_request = f"GET\n/\n{canonical_query}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        scope = f"{datestamp}/{region}/sts/aws4_request"
        string_to_sign = (
            "AWS4-HMAC-SHA256\n"
            f"{amz_date}\n{scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        k_date = hmac.new(("AWS4" + secret_key).encode("utf-8"), datestamp.encode("utf-8"), hashlib.sha256).digest()
        k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
        k_service = hmac.new(k_region, b"sts", hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        auth = (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        status, _payload, raw_err = self._http_json(
            f"https://{host}/?{canonical_query}",
            headers={"Accept": "application/xml", "Authorization": auth, "x-amz-date": amz_date},
        )
        if status == 200:
            return _ok("AWS STS accepted the Access Key and Secret Key.")
        if status in {401, 403}:
            return _fail("AWS STS rejected these keys.")
        return _fail(_safe_error(raw_err or f"AWS STS probe failed (HTTP {status})."))

    def _test_generic(self, provider: str, field: str, cfg: dict[str, str]) -> dict[str, Any]:
        endpoint = (cfg.get("endpoint_url") or "").strip()
        api_key = (cfg.get("api_key") or "").strip()
        secret = (cfg.get("api_secret") or cfg.get("client_secret") or "").strip()
        if provider in {"google_drive", "google_calendar"} and field == "api_key" and api_key:
            return self._google_api_key(api_key)
        if field == "endpoint_url":
            if not endpoint:
                return _fail("Endpoint URL is empty.")
            return self._probe_url(endpoint, label="Endpoint")
        if field in {"api_key", "api_secret", "client_secret"}:
            if field == "api_key" and not api_key:
                return _fail("API Key is not configured.")
            if field in {"api_secret", "client_secret"} and not secret:
                return _fail("Secret is not configured.")
            if not endpoint:
                return _fail("Endpoint URL is required to live-test this credential.")
            headers = {"Accept": "application/json"}
            if api_key:
                if "zoho" in endpoint.lower() or provider == "zoho_books":
                    headers["Authorization"] = f"Zoho-oauthtoken {api_key}"
                else:
                    headers["Authorization"] = f"Bearer {api_key}"
            status, _payload, raw_err = self._http_json(endpoint, headers=headers)
            if status in {200, 201, 204}:
                return _ok("Endpoint accepted the credential.")
            if status in {401, 403}:
                return _fail("Endpoint rejected the credential (HTTP %s)." % status)
            if 200 <= status < 500:
                return _ok(f"Endpoint is reachable (HTTP {status}). Check credential mapping if calls fail.")
            return _fail(_safe_error(raw_err or f"Endpoint probe failed (HTTP {status})."))
        return _fail("This field cannot be live-tested.")

    # ------------------------------------------------------------------
    # Network helpers
    # ------------------------------------------------------------------

    def _tcp_connect(self, host: str, port: int, *, label: str) -> dict[str, Any]:
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror:
            return _fail(f"{label}: DNS lookup failed for {host}.")
        last_err = "connection failed"
        for info in infos[:4]:
            af, socktype, proto, _canon, sockaddr = info
            try:
                sock = socket.socket(af, socktype, proto)
                sock.settimeout(8)
                sock.connect(sockaddr)
                sock.close()
                return _ok(f"{label} is reachable ({host}:{port}).")
            except OSError as exc:
                last_err = str(exc)
        return _fail(f"{label} is not reachable on {host}:{port} ({last_err}).")

    def _tls_handshake(self, host: str, port: int, *, label: str) -> dict[str, Any]:
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, port), timeout=8) as sock:
                with ctx.wrap_socket(sock, server_hostname=host):
                    return _ok(f"{label} handshake succeeded on {host}:{port}.")
        except ssl.SSLError as exc:
            # Titan/GoDaddy often fail hostname checks — try unverified as reachability
            try:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with socket.create_connection((host, port), timeout=8) as sock:
                    with ctx.wrap_socket(sock, server_hostname=host):
                        return _ok(f"{label} connected (certificate hostname not verified).")
            except Exception:
                return _fail(_safe_error(f"{label} TLS failed: {exc}"))
        except OSError as exc:
            return _fail(f"{label} is not reachable on {host}:{port} ({exc}).")

    def _smtp_starttls(self, host: str, port: int) -> dict[str, Any]:
        try:
            import smtplib

            client = smtplib.SMTP(host, port, timeout=12)
            try:
                client.starttls()
            finally:
                try:
                    client.close()
                except Exception:
                    pass
            return _ok(f"SMTP STARTTLS succeeded on {host}:{port}.")
        except Exception as exc:
            return _fail(_safe_error(f"STARTTLS failed on {host}:{port}: {exc}"))

    def _probe_url(self, url: str, *, label: str) -> dict[str, Any]:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return _fail(f"{label} URL must be http or https.")
        host = parsed.hostname
        if not host:
            return _fail(f"{label} URL has no host.")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror:
            return _fail(f"{label}: DNS lookup failed for {host}.")
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return _fail(f"{label}: refusing to probe a private/internal address.")
        status, _payload, raw_err = self._http_json(url, method="GET", timeout=10)
        if status == 0:
            return _fail(_safe_error(raw_err or f"{label} is not reachable."))
        if 200 <= status < 400 or status in {401, 403, 404, 405}:
            return _ok(f"{label} is reachable (HTTP {status}).")
        return _fail(_safe_error(raw_err or f"{label} returned HTTP {status}."))

    def _http_json(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        data: bytes | None = None,
        timeout: int = 12,
    ) -> tuple[int, dict[str, Any] | None, str]:
        hdrs = dict(headers or {"Accept": "application/json"})
        hdrs.setdefault("User-Agent", "JTCS-Integration-Field-Test/1.0")
        req = Request(url, data=data, method=method.upper(), headers=hdrs)
        try:
            opener = build_opener(_NoRedirect())
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                status = int(getattr(resp, "status", 200) or 200)
                if not raw:
                    return status, {}, ""
                try:
                    parsed = json.loads(raw.decode("utf-8", errors="replace"))
                    return status, parsed if isinstance(parsed, dict) else {"data": parsed}, ""
                except json.JSONDecodeError:
                    return status, {}, ""
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            payload: dict[str, Any] | None = None
            try:
                loaded = json.loads(body) if body else {}
                payload = loaded if isinstance(loaded, dict) else {"data": loaded}
            except json.JSONDecodeError:
                payload = {}
            msg = ""
            if payload:
                err = payload.get("error")
                if isinstance(err, dict):
                    msg = str(err.get("message") or err.get("description") or "")
                elif isinstance(err, str):
                    msg = err
                msg = msg or str(payload.get("message") or payload.get("error_description") or "")
            return int(exc.code or 0), payload, _safe_error(msg or body or str(exc))
        except URLError as exc:
            return 0, None, _safe_error(getattr(exc, "reason", None) or str(exc))
        except Exception as exc:
            return 0, None, _safe_error(str(exc))
