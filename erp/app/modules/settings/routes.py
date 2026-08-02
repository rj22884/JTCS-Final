"""Integration Settings blueprint — Admin only."""

from __future__ import annotations

from flask import Blueprint, Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError

from app.decorators import admin_required, login_required
from app.extensions import csrf
from app.modules.settings.controllers import IntegrationSettingsController
from app.modules.settings.repositories import IntegrationSettingsRepository
from app.modules.settings.whatsapp_oauth_service import WhatsAppOAuthService
from app.services.menu_service import MenuService

bp = Blueprint("integration_settings", __name__, url_prefix="/admin/integrations")
MENU_PATH = "/admin/integrations"


def ensure_integration_settings_bootstrap() -> None:
    repo = IntegrationSettingsRepository()
    repo.ensure_schema()
    repo.ensure_audit_schema()
    repo.ensure_menu()


def register_integration_csrf_json_handler(app: Flask) -> None:
    """Return JSON for CSRF failures on Integration Settings API (and other JSON clients)."""

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error: CSRFError):
        wants_json = (
            request.path.startswith("/admin/integrations/api/")
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in (request.headers.get("Accept") or "")
            or bool(request.is_json)
        )
        if wants_json:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "CSRF validation failed. Refresh the page (Ctrl+F5) and try again.",
                    }
                ),
                400,
            )
        return (
            f"<!doctype html><title>400 Bad Request</title>"
            f"<h1>Bad Request</h1><p>{error.description}</p>",
            400,
            {"Content-Type": "text/html; charset=utf-8"},
        )


@bp.route("", strict_slashes=False)
@bp.route("/", strict_slashes=False)
@login_required
@admin_required
def index():
    ctrl = IntegrationSettingsController()
    ctx = ctrl.page_context()
    return render_template(
        "settings/integration_settings.html",
        page_title="Integration Settings",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        providers=ctx["providers"],
        catalog=ctx["catalog"],
    )


@bp.route("/api/settings", methods=["GET"])
@login_required
@admin_required
def api_get_settings():
    return jsonify({"ok": True, **IntegrationSettingsController().load_all()})


@bp.route("/api/settings", methods=["POST"])
@login_required
@admin_required
def api_save_settings():
    payload = request.get_json(silent=True) or {}
    provider = (payload.get("provider") or "").strip()
    values = payload.get("values") or {}
    if not provider:
        return jsonify({"ok": False, "error": "provider is required"}), 400
    try:
        result = IntegrationSettingsController().save(provider, values)
        return jsonify({"ok": True, "provider": provider, **result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"ok": False, "error": "Unable to save integration settings."}), 500


@bp.route("/api/whatsapp/generate-verify-token", methods=["POST"])
@login_required
@admin_required
def api_generate_verify_token():
    try:
        return jsonify(IntegrationSettingsController().generate_verify_token())
    except Exception:
        return jsonify({"ok": False, "error": "Unable to generate verify token."}), 500


@bp.route("/api/whatsapp/test-connection", methods=["POST"])
@login_required
@admin_required
def api_test_whatsapp_connection():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(
            IntegrationSettingsController().test_whatsapp(
                send_test_message=bool(payload.get("send_test_message")),
                test_to_number=payload.get("test_to_number"),
            )
        )
    except Exception:
        return jsonify({"ok": False, "error": "Unable to run connection check."}), 500


@bp.route("/api/status", methods=["GET"])
@login_required
@admin_required
def api_status():
    return jsonify(IntegrationSettingsController().status())


@bp.route("/api/whatsapp/connect", methods=["GET"])
@login_required
@admin_required
def api_whatsapp_connect():
    try:
        result = WhatsAppOAuthService().start_connect()
        # Browser navigation: redirect to Meta; AJAX callers get JSON
        wants_json = "application/json" in (request.headers.get("Accept") or "")
        if wants_json or request.args.get("format") == "json":
            return jsonify(result)
        return redirect(result["authorize_url"])
    except ValueError as exc:
        if request.args.get("format") == "json" or "application/json" in (request.headers.get("Accept") or ""):
            return jsonify({"ok": False, "error": str(exc)}), 400
        flash(str(exc), "danger")
        return redirect(url_for("integration_settings.index"))
    except Exception:
        return jsonify({"ok": False, "error": "Unable to start Meta Connect."}), 500


@bp.route("/api/whatsapp/oauth/callback", methods=["GET"])
@csrf.exempt
@login_required
@admin_required
def api_whatsapp_oauth_callback():
    try:
        result = WhatsAppOAuthService().handle_callback(
            code=request.args.get("code"),
            state=request.args.get("state"),
            error=request.args.get("error_description") or request.args.get("error"),
        )
        flash(result.get("message") or "Meta connected. Continue selection.", "success")
        # Stash selection payload in session for the UI to pick up
        session["wa_meta_pending_step"] = result
        return redirect(url_for("integration_settings.index") + "?wa_connect=1")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("integration_settings.index"))
    except Exception:
        flash("Meta OAuth callback failed.", "danger")
        return redirect(url_for("integration_settings.index"))


@bp.route("/api/whatsapp/pending-step", methods=["GET"])
@login_required
@admin_required
def api_whatsapp_pending_step():
    data = session.pop("wa_meta_pending_step", None)
    return jsonify({"ok": True, "pending": data})


@bp.route("/api/whatsapp/businesses", methods=["GET"])
@login_required
@admin_required
def api_whatsapp_businesses():
    try:
        return jsonify(WhatsAppOAuthService().list_businesses())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/whatsapp/select-business", methods=["POST"])
@login_required
@admin_required
def api_whatsapp_select_business():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(WhatsAppOAuthService().select_business(payload.get("business_id") or ""))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/whatsapp/wabas", methods=["GET"])
@login_required
@admin_required
def api_whatsapp_wabas():
    try:
        return jsonify(WhatsAppOAuthService().list_wabas(request.args.get("business_id")))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/whatsapp/select-waba", methods=["POST"])
@login_required
@admin_required
def api_whatsapp_select_waba():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(WhatsAppOAuthService().select_waba(payload.get("waba_id") or ""))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/whatsapp/phones", methods=["GET"])
@login_required
@admin_required
def api_whatsapp_phones():
    try:
        return jsonify(WhatsAppOAuthService().list_phones(request.args.get("waba_id")))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/whatsapp/select-phone", methods=["POST"])
@login_required
@admin_required
def api_whatsapp_select_phone():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(WhatsAppOAuthService().select_phone(payload.get("phone_number_id") or ""))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/whatsapp/token-guide", methods=["GET"])
@login_required
@admin_required
def api_whatsapp_token_guide():
    return jsonify(IntegrationSettingsController().token_guide())


@bp.route("/api/whatsapp/audit", methods=["GET"])
@login_required
@admin_required
def api_whatsapp_audit():
    limit = int(request.args.get("limit") or 50)
    return jsonify(IntegrationSettingsController().whatsapp_audit(limit=limit))


@bp.route("/api/whatsapp/webhook", methods=["GET", "POST"])
@csrf.exempt
def api_whatsapp_webhook():
    """
    Placeholder webhook endpoint for Meta verification / future inbound events.
    Does not modify CRM. GET supports hub.challenge verification.
    """
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        try:
            from app.modules.settings.services import IntegrationSettingsService

            cfg = IntegrationSettingsService().get_provider_config_decrypted("whatsapp_meta")
            expected = (cfg.get("webhook_verify_token") or "").strip()
            if mode == "subscribe" and expected and token == expected and challenge:
                return challenge, 200, {"Content-Type": "text/plain"}
        except Exception:
            pass
        return jsonify({"ok": False, "error": "Webhook verification failed"}), 403
    return jsonify({"ok": True, "received": True})
