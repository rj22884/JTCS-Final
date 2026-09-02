"""Integration Settings providers, field catalogs, and secret keys."""

from __future__ import annotations

from app.modules.settings.provider_catalog import GENERIC_FIELDS, PROVIDER_CATALOG, providers_list

# Backward-compatible alias — catalog is the single source of truth.
PROVIDERS: tuple[dict[str, str], ...] = tuple(
    {"code": p["code"], "label": p["label"]} for p in PROVIDER_CATALOG
)

# Fields required to send WhatsApp messages (optional profile/status fields are not).
WHATSAPP_SEND_REQUIRED_KEYS: tuple[str, ...] = (
    "app_id",
    "app_secret",
    "phone_number_id",
    "waba_id",
    "access_token",
    "webhook_verify_token",
)

# Keys that must be encrypted at rest and masked on read.
SECRET_KEYS: frozenset[str] = frozenset(
    {
        "app_secret",
        "access_token",
        "webhook_verify_token",
        "api_key",
        "api_secret",
        "client_secret",
        "password",
        "smtp_password",
        "auth_token",
        "private_key",
        "secret_key",
        "webhook_secret",
        "refresh_token",
        "certificate",
        "private_cert",
    }
)

PROVIDER_FIELDS: dict[str, list[dict[str, str]]] = {
    "whatsapp_meta": [
        {
            "key": "app_id",
            "label": "Facebook App ID",
            "input": "text",
            "section": "facebook_login",
            "find_label": "Isi page par daalo. Facebook Login ke baad baaki IDs API se aati hain.",
        },
        {
            "key": "app_secret",
            "label": "Facebook App Secret",
            "input": "password",
            "section": "facebook_login",
            "find_label": "Isi page par daalo, Save credentials, phir Facebook Login. Secret Meta se copy — yahan page nahi khulega.",
        },
        {
            "key": "phone_number",
            "label": "WhatsApp Phone Number",
            "input": "text",
            "section": "whatsapp_account",
            "find_label": "Facebook Login ke baad Graph API se auto (+91, test +1 555 nahi).",
        },
        {
            "key": "phone_number_id",
            "label": "Phone Number ID",
            "input": "text",
            "section": "whatsapp_account",
            "find_label": "Facebook Login ke baad Graph API se auto (real number, test nahi).",
        },
        {
            "key": "waba_id",
            "label": "WhatsApp Business Account ID",
            "input": "text",
            "section": "whatsapp_account",
            "find_label": "Facebook Login ke baad Graph API se auto (Test WABA skip).",
        },
        {
            "key": "business_id",
            "label": "Business ID",
            "input": "text",
            "section": "whatsapp_account",
            "find_label": "Facebook Login ke baad Graph API se auto.",
        },
        {
            "key": "access_token",
            "label": "Access Token",
            "input": "password",
            "section": "whatsapp_account",
            "find_label": "Facebook Login ke baad long-lived token encrypted save. Screen par kabhi nahi dikhta.",
        },
        {
            "key": "webhook_verify_token",
            "label": "Webhook Verify Token",
            "input": "password",
            "section": "webhook",
            "find_label": "ERP Generate Verify Token / Facebook Login se auto. Meta Dashboard mein paste karna ho to yahin se copy.",
        },
        {
            "key": "webhook_url",
            "label": "Webhook URL",
            "input": "readonly",
            "section": "webhook",
            "find_label": "ERP isi URL ko auto set karta hai. Meta Callback field mein paste karna ho to yahin se copy.",
        },
        {
            "key": "oauth_redirect_uri",
            "label": "OAuth Redirect URI",
            "input": "readonly",
            "section": "webhook",
            "find_label": "ERP isi URI ko auto set karta hai. Meta Valid OAuth Redirect URIs mein paste karna ho to yahin se copy.",
        },
        {
            "key": "token_expires_at",
            "label": "Token Expires At (UTC)",
            "input": "readonly",
            "section": "status",
            "help": "Facebook Login / token debug ke baad auto. Manual paste nahi.",
        },
        {
            "key": "connection_status",
            "label": "Connection Status",
            "input": "readonly",
            "section": "status",
        },
        {"key": "business_name", "label": "Business Name", "input": "text", "hidden": "1"},
        {"key": "display_name", "label": "Display Name / Verified Name", "input": "text", "hidden": "1"},
        {"key": "quality_rating", "label": "Quality Rating", "input": "text", "hidden": "1"},
        {"key": "messaging_limit", "label": "Messaging Limit", "input": "text", "hidden": "1"},
        {"key": "account_status", "label": "Account Status", "input": "text", "hidden": "1"},
        {"key": "profile_photo_url", "label": "Profile Photo URL", "input": "text", "hidden": "1"},
        {"key": "graph_api_version", "label": "Graph API Version", "input": "text", "hidden": "1"},
        {"key": "webhook_subscribed_fields", "label": "Subscribed Webhook Events", "input": "readonly", "hidden": "1"},
        {"key": "last_sync_at", "label": "Last Sync Time (UTC)", "input": "readonly", "hidden": "1"},
    ],
    "smtp": [
        {"key": "host", "label": "SMTP Host", "input": "text"},
        {"key": "port", "label": "Port", "input": "number"},
        {"key": "username", "label": "Username", "input": "text"},
        {"key": "smtp_password", "label": "Password", "input": "password"},
        {"key": "from_email", "label": "From Email", "input": "text"},
        {"key": "use_tls", "label": "Use TLS (STARTTLS)", "input": "checkbox"},
        {"key": "use_ssl", "label": "Use SSL", "input": "checkbox"},
        {"key": "connection_status", "label": "Connection Status", "input": "readonly"},
    ],
    "google": [
        {"key": "client_id", "label": "Client ID", "input": "text"},
        {"key": "client_secret", "label": "Client Secret", "input": "password"},
        {"key": "project_id", "label": "Project ID", "input": "text"},
        {"key": "api_key", "label": "API Key", "input": "password"},
        {"key": "connection_status", "label": "Connection Status", "input": "readonly"},
    ],
    "openai": [
        {"key": "api_key", "label": "API Key", "input": "password"},
        {"key": "organization", "label": "Organization", "input": "text"},
        {"key": "default_model", "label": "Default Model", "input": "text"},
        {"key": "connection_status", "label": "Connection Status", "input": "readonly"},
    ],
    "gemini": [
        {"key": "api_key", "label": "API Key", "input": "password"},
        {"key": "default_model", "label": "Default Model", "input": "text"},
        {"key": "connection_status", "label": "Connection Status", "input": "readonly"},
    ],
    "claude": [
        {"key": "api_key", "label": "API Key", "input": "password"},
        {"key": "default_model", "label": "Default Model", "input": "text"},
        {"key": "connection_status", "label": "Connection Status", "input": "readonly"},
    ],
    "sms": [
        {"key": "provider_name", "label": "Provider Name", "input": "text"},
        {"key": "api_key", "label": "API Key", "input": "password"},
        {"key": "api_secret", "label": "API Secret", "input": "password"},
        {"key": "sender_id", "label": "Sender ID", "input": "text"},
        {"key": "connection_status", "label": "Connection Status", "input": "readonly"},
    ],
    "payment": [
        {"key": "gateway_name", "label": "Gateway Name", "input": "text"},
        {"key": "merchant_id", "label": "Merchant ID", "input": "text"},
        {"key": "api_key", "label": "API Key", "input": "password"},
        {"key": "api_secret", "label": "API Secret", "input": "password"},
        {"key": "webhook_secret", "label": "Webhook Secret", "input": "password"},
        {"key": "connection_status", "label": "Connection Status", "input": "readonly"},
    ],
    "cloud_storage": [
        {"key": "provider_name", "label": "Provider Name", "input": "text"},
        {"key": "bucket_name", "label": "Bucket / Container", "input": "text"},
        {"key": "access_key", "label": "Access Key", "input": "text"},
        {"key": "secret_key", "label": "Secret Key", "input": "password"},
        {"key": "region", "label": "Region", "input": "text"},
        {"key": "connection_status", "label": "Connection Status", "input": "readonly"},
    ],
    "future": [
        {"key": "notes", "label": "Notes / Placeholder Config", "input": "textarea"},
        {"key": "connection_status", "label": "Connection Status", "input": "readonly"},
    ],
}

# Ensure every catalog provider has a field definition (future-ready auto UI).
for _p in PROVIDER_CATALOG:
    if _p["code"] not in PROVIDER_FIELDS:
        PROVIDER_FIELDS[_p["code"]] = list(GENERIC_FIELDS)


def is_secret_key(setting_key: str) -> bool:
    return (setting_key or "").strip().lower() in SECRET_KEYS


def get_providers_catalog() -> list[dict[str, str]]:
    return providers_list()
