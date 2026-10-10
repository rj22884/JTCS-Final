"""Host policy for whatsapp.jtcsxpert.com.

The focused site is the same Flask app, the same inbox template, and the same
CRM tables as app.jtcsxpert.com. It does not open a second message store.
"""

from __future__ import annotations

CANONICAL_HOST = "whatsapp.jtcsxpert.com"
DEV_HOSTS = frozenset({"whatsapp.localhost", "whatsapp.jtcsxpert.local"})

# One source of truth. Both domains render and call these.
SHARED_UI = (
    "erp/app/templates/crm/inbox.html",
    "erp/app/static/js/crm/inbox.js",
    "erp/app/static/css/crm/inbox_whatsapp.css",
)
SHARED_API = (
    "/crm/inbox",
    "/api/crm/conversations",
    "/api/crm/templates",
    "/api/crm/conversations/0/reply",
)
SHARED_WEBHOOKS = (
    "/webhooks/whatsapp",
    "/admin/integrations/api/whatsapp/webhook",
)
SHARED_TABLES = (
    "dbo.CrmConversation",
    "dbo.CrmMessage",
    "dbo.CrmWebhookEvent",
)
INBOX_PATH = "/crm/inbox?channel=WhatsApp"

_EXACT = frozenset(
    {
        "/login",
        "/logout",
        "/register",
        "/verify-email",
        "/verify-email/confirm",
        "/forgot-password",
        "/forgot-user-id",
        "/reset-password",
        "/server-auth",
        "/boot",
        "/health",
        "/manifest.webmanifest",
        "/favicon.ico",
        "/crm/inbox",
        "/crm/whatsapp-templates",
        "/webhooks/whatsapp",
        "/admin/integrations/api/whatsapp/webhook",
        "/api/search",
        "/api/runtime",
    }
)
_PREFIXES = (
    "/static/",
    "/verify/",
    "/reset-password/",
    "/server-auth/",
    "/api/crm/",
    "/api/notifications",
)


def hostname(host: str | None) -> str:
    return (host or "").split(":")[0].strip().lower()


def is_whatsapp_host(host: str | None) -> bool:
    name = hostname(host)
    return name == CANONICAL_HOST or name in DEV_HOSTS


def home_path(host: str | None) -> str:
    if is_whatsapp_host(host):
        return INBOX_PATH
    return "/dashboard"


def normalize_path(path: str | None) -> str:
    value = (path or "/").split("?", 1)[0]
    if len(value) > 1 and value.endswith("/"):
        value = value.rstrip("/")
    return value or "/"


def path_allowed(path: str | None) -> bool:
    value = normalize_path(path)
    if value in _EXACT:
        return True
    return any(value.startswith(prefix) for prefix in _PREFIXES)


def gate_decision(host: str | None, path: str | None) -> str | None:
    """None means the request stays on the normal ERP.

    A path means redirect there. 'deny' means a JSON 403 for blocked APIs.
    """
    if not is_whatsapp_host(host):
        return None
    if path_allowed(path):
        return None
    if normalize_path(path).startswith("/api/"):
        return "deny"
    return INBOX_PATH
