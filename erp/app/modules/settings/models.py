"""Integration Settings providers, field catalogs, and secret keys."""

from __future__ import annotations

PROVIDERS: tuple[dict[str, str], ...] = (
    {"code": "whatsapp_meta", "label": "Meta WhatsApp Cloud API"},
    {"code": "smtp", "label": "Email SMTP"},
    {"code": "google", "label": "Google"},
    {"code": "openai", "label": "OpenAI"},
    {"code": "gemini", "label": "Gemini"},
    {"code": "claude", "label": "Claude"},
    {"code": "sms", "label": "SMS"},
    {"code": "payment", "label": "Payment Gateway"},
    {"code": "cloud_storage", "label": "Cloud Storage"},
    {"code": "future", "label": "Future APIs"},
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
    }
)

PROVIDER_FIELDS: dict[str, list[dict[str, str]]] = {
    "whatsapp_meta": [
        {"key": "business_name", "label": "Business Name", "input": "text"},
        {"key": "business_id", "label": "Business ID", "input": "text"},
        {"key": "app_id", "label": "App ID", "input": "text"},
        {"key": "app_secret", "label": "App Secret", "input": "password"},
        {"key": "phone_number_id", "label": "Phone Number ID", "input": "text"},
        {"key": "waba_id", "label": "WhatsApp Business Account ID", "input": "text"},
        {"key": "display_name", "label": "Display Name", "input": "text"},
        {"key": "quality_rating", "label": "Quality Rating", "input": "text"},
        {"key": "account_status", "label": "Account Status", "input": "text"},
        {"key": "access_token", "label": "Access Token", "input": "password"},
        {"key": "graph_api_version", "label": "Graph API Version", "input": "text"},
        {"key": "webhook_verify_token", "label": "Webhook Verify Token", "input": "password"},
        {"key": "webhook_url", "label": "Webhook URL", "input": "text"},
        {"key": "oauth_redirect_uri", "label": "OAuth Redirect URI", "input": "text"},
        {"key": "connection_status", "label": "Connection Status", "input": "readonly"},
    ],
    "smtp": [
        {"key": "host", "label": "SMTP Host", "input": "text"},
        {"key": "port", "label": "Port", "input": "text"},
        {"key": "username", "label": "Username", "input": "text"},
        {"key": "smtp_password", "label": "Password", "input": "password"},
        {"key": "use_tls", "label": "Use TLS", "input": "text"},
        {"key": "use_ssl", "label": "Use SSL", "input": "text"},
        {"key": "from_email", "label": "From Email", "input": "text"},
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


def is_secret_key(setting_key: str) -> bool:
    return (setting_key or "").strip().lower() in SECRET_KEYS
