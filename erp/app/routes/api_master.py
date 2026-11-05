"""API Master — one screen for cloud email, WhatsApp, and other API credentials."""

from __future__ import annotations

from flask import Blueprint, flash, jsonify, render_template, request, session, url_for
from sqlalchemy import text

from app.decorators import admin_required, login_required
from app.extensions import db
from app.modules.settings.models import (
    PROVIDER_FIELDS,
    WHATSAPP_PUBLIC_WEBHOOK_URL,
    is_secret_key,
)
from app.modules.settings.provider_catalog import providers_list
from app.modules.settings.services import IntegrationSettingsService
from app.services.menu_service import MenuService

bp = Blueprint("api_master", __name__, url_prefix="/masters/api-master")

MENU_PATH = "/masters/api-master"

_PLACEHOLDERS = {
    ("smtp", "host"): "smtpout.secureserver.net",
    ("smtp", "port"): "465",
    ("smtp", "username"): "admin@yourdomain.com",
    ("smtp", "from_email"): "admin@yourdomain.com",
    ("imap", "server"): "imap.secureserver.net",
    ("imap", "port"): "993",
    ("imap", "username"): "admin@yourdomain.com",
    ("imap", "folder"): "INBOX",
    ("whatsapp_meta", "phone_number"): "+91 98765 43210",
}

_CATEGORY_ORDER = (
    "Messaging",
    "Google",
    "AI",
    "Finance",
    "Compliance",
    "KYC",
    "Accounting",
    "Storage",
    "Future",
    "Other",
)


def ensure_api_master_menu() -> None:
    db.session.execute(
        text(
            """
            DECLARE @MastersID INT;
            SELECT TOP 1 @MastersID = MenuID
            FROM dbo.MenuMaster
            WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
            ORDER BY MenuID;

            IF @MastersID IS NOT NULL
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM dbo.MenuMaster
                    WHERE MenuURL = N'/masters/api-master' OR MenuName = N'API Master'
                )
                    UPDATE dbo.MenuMaster
                    SET ParentMenuID = @MastersID,
                        MenuName = N'API Master',
                        MenuURL = N'/masters/api-master',
                        MenuIcon = N'bi-plugin',
                        DisplayOrder = 4,
                        Description = N'Cloud email, WhatsApp, SMS and other API credentials',
                        IsActive = 1,
                        RoleName = N'Administrator,Admin'
                    WHERE MenuURL = N'/masters/api-master' OR MenuName = N'API Master';
                ELSE
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @MastersID,
                        N'API Master',
                        N'bi-plugin',
                        N'/masters/api-master',
                        4,
                        N'Cloud email, WhatsApp, SMS and other API credentials',
                        1,
                        N'Administrator,Admin'
                    );
            END
            """
        )
    )
    db.session.commit()


def _status_class(status: str) -> str:
    text_status = (status or "").lower()
    if "fail" in text_status or "invalid" in text_status or "expired" in text_status:
        return "text-bg-danger"
    if "partial" in text_status:
        return "text-bg-warning"
    if "connect" in text_status and "not" not in text_status and "disconnect" not in text_status:
        return "text-bg-success"
    return "text-bg-secondary"


def _is_checked(field_key: str, value: str) -> bool:
    text_value = (value or "").strip().lower()
    if text_value in {"1", "true", "yes", "on", "y"}:
        return True
    if text_value in {"0", "false", "no", "off", "n"}:
        return False
    return field_key == "use_ssl"


def _section(code: str, title: str, hint: str, by_code: dict) -> dict:
    masked = by_code.get(code) or {}
    values = masked.get("field_values") or {}
    secrets = masked.get("secret_configured") or {}
    fields = []
    for field in PROVIDER_FIELDS.get(code) or []:
        if str(field.get("hidden") or "") == "1":
            continue
        key = field["key"]
        if key == "connection_status":
            continue
        raw = values.get(key)
        value = "" if raw is None else str(raw)
        input_type = field.get("input") or "text"
        fields.append(
            {
                "key": key,
                "label": field.get("label") or key,
                "input": input_type,
                "value": value,
                "placeholder": _PLACEHOLDERS.get((code, key), ""),
                "secret": is_secret_key(key) or input_type == "password",
                "configured": bool(secrets.get(key)),
                "checked": _is_checked(key, value) if input_type == "checkbox" else False,
            }
        )
    status = (values.get("connection_status") or "").strip() or "Not Configured"
    return {
        "code": code,
        "title": title,
        "hint": hint,
        "status": status,
        "status_class": _status_class(status),
        "fields": fields,
        "can_test": code in {"smtp", "imap", "whatsapp_meta"},
        "can_generate_token": code == "whatsapp_meta",
    }


def _panels(by_code: dict) -> list[dict]:
    email = {
        "id": "email",
        "label": "Cloud Email",
        "icon": "bi-envelope",
        "category": "Messaging",
        "hint": "Outgoing mail (SMTP) sends replies and system emails. Incoming mail (IMAP) fills the Email tab in the inbox.",
        "webhook_url": "",
        "sections": [
            _section(
                "smtp",
                "Outgoing mail (SMTP)",
                "Inbox replies and password / OTP emails use this mailbox. Titan / GoDaddy usually uses port 465 with SSL.",
                by_code,
            ),
            _section(
                "imap",
                "Incoming mail (IMAP)",
                "The Email tab reads this mailbox. Save server, username, and password, then Test.",
                by_code,
            ),
        ],
    }
    panels = [email]
    for item in providers_list():
        code = item["code"]
        if code in {"smtp", "imap"}:
            continue
        hint = "Save the keys this provider needs. Passwords stay encrypted and are not shown again."
        if code == "whatsapp_meta":
            hint = "Meta Cloud API credentials. Paste the webhook URL into the Meta app, then save and test."
        panels.append(
            {
                "id": code,
                "label": item["label"],
                "icon": item.get("icon") or "bi-plugin",
                "category": item.get("category") or "Other",
                "hint": hint,
                "webhook_url": WHATSAPP_PUBLIC_WEBHOOK_URL if code == "whatsapp_meta" else "",
                "sections": [_section(code, item["label"], hint, by_code)],
            }
        )
    return panels


def _nav_groups(panels: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for panel in panels:
        grouped.setdefault(panel["category"], []).append(panel)
    ordered = [name for name in _CATEGORY_ORDER if name in grouped]
    ordered.extend(name for name in grouped if name not in ordered)
    return [{"category": name, "items": grouped[name]} for name in ordered]


def _load_saved() -> dict:
    try:
        data = IntegrationSettingsService().get_all_masked()
        return {item["code"]: item for item in data.get("providers") or []}
    except Exception:
        db.session.rollback()
        flash("Saved API settings could not be loaded. You can still enter new values.", "warning")
        return {}


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def index():
    try:
        ensure_api_master_menu()
    except Exception:
        db.session.rollback()
    panels = _panels(_load_saved())
    return render_template(
        "masters/api_master.html",
        page_title="API Master",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        panels=panels,
        nav_groups=_nav_groups(panels),
        inbox_url=url_for("crm.inbox_page"),
        save_url=url_for("api_master.save"),
        test_url=url_for("api_master.test"),
        token_url=url_for("api_master.generate_verify_token"),
    )


@bp.route("/api/save", methods=["POST"])
@login_required
@admin_required
def save():
    payload = request.get_json(silent=True) or {}
    provider = (payload.get("provider") or "").strip()
    values = payload.get("values") if isinstance(payload.get("values"), dict) else {}
    if not provider:
        return jsonify({"ok": False, "error": "provider is required"}), 400
    try:
        result = IntegrationSettingsService().save_provider_settings(provider, values)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        return jsonify({"ok": False, "error": "Unable to save these settings."}), 500
    status = ((result.get("field_values") or {}).get("connection_status") or "").strip() or "Not Configured"
    return jsonify(
        {
            "ok": True,
            "provider": provider,
            "message": result.get("message") or "Settings saved.",
            "status": status,
            "status_class": _status_class(status),
            "field_values": result.get("field_values") or {},
            "secret_configured": result.get("secret_configured") or {},
        }
    )


@bp.route("/api/test", methods=["POST"])
@login_required
@admin_required
def test():
    payload = request.get_json(silent=True) or {}
    provider = (payload.get("provider") or "").strip()
    values = payload.get("values") if isinstance(payload.get("values"), dict) else {}
    service = IntegrationSettingsService()
    try:
        if provider == "smtp":
            result = service.test_smtp_connection(values)
        elif provider == "imap":
            result = service.test_imap_connection(values)
        elif provider == "whatsapp_meta":
            result = service.test_whatsapp_connection()
            if not result.get("message"):
                result["message"] = "WhatsApp connection checked."
        else:
            return jsonify({"ok": False, "error": "This provider has no connection test."}), 400
    except Exception:
        db.session.rollback()
        return jsonify({"ok": False, "error": "Connection test failed."}), 500
    status = ((result.get("field_values") or {}).get("connection_status") or "").strip()
    return jsonify(
        {
            "ok": bool(result.get("ok")),
            "message": result.get("message") or ("Connected" if result.get("ok") else "Connection failed"),
            "status": status,
            "status_class": _status_class(status) if status else "",
        }
    )


@bp.route("/api/generate-verify-token", methods=["POST"])
@login_required
@admin_required
def generate_verify_token():
    try:
        result = IntegrationSettingsService().generate_whatsapp_verify_token()
    except Exception:
        db.session.rollback()
        return jsonify({"ok": False, "error": "Unable to generate a verify token."}), 500
    return jsonify(
        {
            "ok": True,
            "message": result.get("message") or "Verify token generated.",
            "token": result.get("webhook_verify_token_plain") or "",
        }
    )
