"""Admin screen for Meta WhatsApp Cloud API credentials."""

from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import text

from app.decorators import admin_required, login_required
from app.extensions import db
from app.modules.settings.models import (
    WHATSAPP_PREFERRED_APP_ID,
    WHATSAPP_PREFERRED_BUSINESS_ID,
    WHATSAPP_PREFERRED_PHONE_NUMBER,
    WHATSAPP_PREFERRED_WABA_ID,
    WHATSAPP_PUBLIC_WEBHOOK_URL,
)
from app.modules.settings.services import IntegrationSettingsService
from app.services.menu_service import MenuService

bp = Blueprint("whatsapp_cloud", __name__, url_prefix="/admin/whatsapp")

MENU_PATH = "/admin/whatsapp"
PROVIDER = "whatsapp_meta"


def _ensure_menu() -> None:
    db.session.execute(
        text(
            """
            DECLARE @ParentID INT;
            SELECT TOP 1 @ParentID = MenuID
            FROM dbo.MenuMaster
            WHERE ParentMenuID IS NULL
              AND MenuName IN (N'CRM', N'Communication', N'Settings')
            ORDER BY CASE MenuName
                WHEN N'CRM' THEN 1
                WHEN N'Communication' THEN 2
                ELSE 3
            END;

            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE MenuURL = N'/admin/whatsapp' OR MenuName = N'WhatsApp Cloud API'
            )
                UPDATE dbo.MenuMaster
                SET MenuURL = N'/admin/whatsapp',
                    MenuIcon = N'bi-whatsapp',
                    Description = N'Meta WhatsApp credentials, webhook, and connection test',
                    IsActive = 1,
                    RoleName = N'Administrator,Admin',
                    ParentMenuID = COALESCE(@ParentID, ParentMenuID)
                WHERE MenuURL = N'/admin/whatsapp' OR MenuName = N'WhatsApp Cloud API';
            ELSE
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID, N'WhatsApp Cloud API', N'bi-whatsapp', N'/admin/whatsapp',
                    5, N'Meta WhatsApp credentials, webhook, and connection test',
                    1, N'Administrator,Admin'
                );
            """
        )
    )
    db.session.commit()


def _load() -> dict:
    try:
        data = IntegrationSettingsService().get_provider_settings_masked(PROVIDER)
    except Exception:
        db.session.rollback()
        data = {
            "field_values": {},
            "secret_configured": {},
            "missing_labels": [],
            "connection_status": "",
        }
    values = data.get("field_values") or {}
    secrets = data.get("secret_configured") or {}
    has_saved = bool(
        (values.get("app_id") or "").strip()
        or (values.get("phone_number_id") or "").strip()
        or (values.get("waba_id") or "").strip()
        or secrets.get("access_token")
        or secrets.get("app_secret")
        or secrets.get("webhook_verify_token")
    )
    return {
        "values": values,
        "secrets": secrets,
        "missing_labels": data.get("missing_labels") or [],
        "status": (values.get("connection_status") or "").strip() or "Not Configured",
        "has_saved": has_saved,
    }


@bp.route("", strict_slashes=False)
@bp.route("/", strict_slashes=False)
@login_required
@admin_required
def index():
    try:
        _ensure_menu()
    except Exception:
        db.session.rollback()
    state = _load()
    return render_template(
        "settings/whatsapp_cloud.html",
        page_title="WhatsApp Cloud API",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        webhook_url=WHATSAPP_PUBLIC_WEBHOOK_URL,
        preferred_app_id=WHATSAPP_PREFERRED_APP_ID,
        preferred_phone=WHATSAPP_PREFERRED_PHONE_NUMBER,
        preferred_waba=WHATSAPP_PREFERRED_WABA_ID,
        preferred_business=WHATSAPP_PREFERRED_BUSINESS_ID,
        inbox_url=url_for("crm.inbox_page"),
        state=state,
    )


def _posted_values() -> dict:
    payload = request.get_json(silent=True) or {}
    if isinstance(payload.get("values"), dict):
        return payload["values"]
    keys = (
        "app_id",
        "app_secret",
        "phone_number",
        "phone_number_id",
        "waba_id",
        "business_id",
        "graph_api_version",
        "access_token",
        "webhook_verify_token",
    )
    return {key: request.form.get(key, "") for key in keys}


def _wants_json() -> bool:
    return bool(request.is_json) or request.headers.get("X-Requested-With") == "XMLHttpRequest"


@bp.route("/api/save", methods=["POST"])
@login_required
@admin_required
def save():
    values = _posted_values()
    try:
        result = IntegrationSettingsService().save_provider_settings(PROVIDER, values)
    except ValueError as exc:
        if _wants_json():
            return jsonify({"ok": False, "error": str(exc)}), 400
        flash(str(exc), "danger")
        return redirect(url_for("whatsapp_cloud.index"))
    except Exception:
        db.session.rollback()
        if _wants_json():
            return jsonify({"ok": False, "error": "Unable to save WhatsApp credentials."}), 500
        flash("Unable to save WhatsApp credentials.", "danger")
        return redirect(url_for("whatsapp_cloud.index"))
    message = result.get("message") or "Credentials saved."
    if _wants_json():
        return jsonify({"ok": True, **result, "webhook_url": WHATSAPP_PUBLIC_WEBHOOK_URL, "message": message})
    flash(message, "success")
    return redirect(url_for("whatsapp_cloud.index"))


@bp.route("/api/delete", methods=["POST"])
@login_required
@admin_required
def delete():
    try:
        result = IntegrationSettingsService().clear_whatsapp_credentials()
        return jsonify({"ok": True, **result, "webhook_url": WHATSAPP_PUBLIC_WEBHOOK_URL})
    except Exception:
        db.session.rollback()
        return jsonify({"ok": False, "error": "Unable to delete WhatsApp credentials."}), 500
