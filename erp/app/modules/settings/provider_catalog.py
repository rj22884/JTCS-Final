"""Dynamic integration catalog — new providers appear automatically on Health dashboard."""

from __future__ import annotations

# code, label, bootstrap icon, category
PROVIDER_CATALOG: tuple[dict[str, str], ...] = (
    {"code": "whatsapp_meta", "label": "Meta WhatsApp Cloud API", "icon": "bi-whatsapp", "category": "Messaging"},
    {"code": "smtp", "label": "SMTP Email", "icon": "bi-envelope", "category": "Messaging"},
    {"code": "google", "label": "Google OAuth", "icon": "bi-google", "category": "Google"},
    {"code": "google_drive", "label": "Google Drive", "icon": "bi-google", "category": "Google"},
    {"code": "google_calendar", "label": "Google Calendar", "icon": "bi-calendar3", "category": "Google"},
    {"code": "openai", "label": "OpenAI", "icon": "bi-robot", "category": "AI"},
    {"code": "gemini", "label": "Gemini", "icon": "bi-stars", "category": "AI"},
    {"code": "claude", "label": "Claude", "icon": "bi-chat-square-text", "category": "AI"},
    {"code": "sms", "label": "SMS Gateway", "icon": "bi-chat-dots", "category": "Messaging"},
    {"code": "payment", "label": "Payment Gateway", "icon": "bi-credit-card", "category": "Finance"},
    {"code": "cloud_storage", "label": "Cloud Storage", "icon": "bi-cloud", "category": "Storage"},
    {"code": "fyers", "label": "Fyers API", "icon": "bi-graph-up", "category": "Finance"},
    {"code": "income_tax", "label": "Income Tax API", "icon": "bi-file-earmark-text", "category": "Compliance"},
    {"code": "gst_api", "label": "GST API", "icon": "bi-receipt", "category": "Compliance"},
    {"code": "mca_api", "label": "MCA API", "icon": "bi-building", "category": "Compliance"},
    {"code": "pan_verify", "label": "PAN Verification API", "icon": "bi-person-vcard", "category": "KYC"},
    {"code": "aadhaar_ekyc", "label": "Aadhaar eKYC", "icon": "bi-fingerprint", "category": "KYC"},
    {"code": "digilocker", "label": "DigiLocker", "icon": "bi-safe", "category": "KYC"},
    {"code": "tally", "label": "Tally Prime Connector", "icon": "bi-calculator", "category": "Accounting"},
    {"code": "zoho_books", "label": "Zoho Books", "icon": "bi-journal-bookmark", "category": "Accounting"},
    {"code": "future", "label": "Future APIs", "icon": "bi-puzzle", "category": "Future"},
)

GENERIC_FIELDS: list[dict[str, str]] = [
    {"key": "api_key", "label": "API Key", "input": "password"},
    {"key": "api_secret", "label": "API Secret", "input": "password"},
    {"key": "endpoint_url", "label": "Endpoint URL", "input": "text"},
    {"key": "notes", "label": "Notes", "input": "textarea"},
    {"key": "connection_status", "label": "Connection Status", "input": "readonly"},
]


def providers_list() -> list[dict[str, str]]:
    return [dict(p) for p in PROVIDER_CATALOG]


def provider_meta(code: str) -> dict[str, str]:
    for p in PROVIDER_CATALOG:
        if p["code"] == code:
            return dict(p)
    return {
        "code": code,
        "label": code.replace("_", " ").title(),
        "icon": "bi-plugin",
        "category": "Other",
    }
