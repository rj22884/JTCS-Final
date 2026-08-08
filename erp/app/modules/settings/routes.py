"""Integration Settings blueprint — Admin only."""

from __future__ import annotations

from flask import (
    Blueprint,
    Flask,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
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
    repo.ensure_health_schema()
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
        whatsapp_card=ctx.get("whatsapp_card"),
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


@bp.route("/api/whatsapp/refresh-metadata", methods=["POST"])
@login_required
@admin_required
def api_whatsapp_refresh_metadata():
    try:
        return jsonify(IntegrationSettingsController().refresh_metadata())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/whatsapp/token-health", methods=["GET"])
@login_required
@admin_required
def api_whatsapp_token_health():
    try:
        return jsonify(IntegrationSettingsController().token_health())
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/whatsapp/account-card", methods=["GET"])
@login_required
@admin_required
def api_whatsapp_account_card():
    try:
        return jsonify(IntegrationSettingsController().account_card())
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/whatsapp/webhook-info", methods=["GET"])
@login_required
@admin_required
def api_whatsapp_webhook_info():
    try:
        return jsonify(IntegrationSettingsController().webhook_info())
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/whatsapp/subscribe-webhooks", methods=["POST"])
@login_required
@admin_required
def api_whatsapp_subscribe_webhooks():
    try:
        return jsonify(IntegrationSettingsController().subscribe_webhooks())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/whatsapp/unsubscribe-webhooks", methods=["POST"])
@login_required
@admin_required
def api_whatsapp_unsubscribe_webhooks():
    try:
        return jsonify(IntegrationSettingsController().unsubscribe_webhooks())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/whatsapp/webhook", methods=["GET", "POST"])
@csrf.exempt
def api_whatsapp_webhook():
    """Meta WhatsApp Cloud API webhook — verify (GET) and persist inbound (POST)."""
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

    raw = request.get_data(cache=True, as_text=False) or b""
    try:
        from app.modules.settings.services import IntegrationSettingsService
        from app.modules.settings.whatsapp_meta_client import WhatsAppMetaClient

        cfg = IntegrationSettingsService().get_provider_config_decrypted("whatsapp_meta")
        app_secret = (cfg.get("app_secret") or "").strip()
        sig = request.headers.get("X-Hub-Signature-256")
        # Enforce signature when app_secret is configured
        if app_secret and sig and not WhatsAppMetaClient.verify_signature(app_secret, raw, sig):
            return jsonify({"ok": False, "error": "Invalid signature"}), 403
    except Exception:
        pass

    payload = request.get_json(silent=True) or {}
    try:
        from app.modules.communication.webhook_service import WhatsAppWebhookService

        result = WhatsAppWebhookService().process_payload(payload, raw_body=raw)
        return jsonify(result)
    except Exception as exc:
        # Always ACK to Meta to avoid retry storms; log server-side
        current_app.logger.exception("WhatsApp webhook processing failed: %s", exc)
        return jsonify({"ok": True, "received": True, "error": str(exc)})


# ---------------------------------------------------------------------------
# Integration Health Dashboard (tab inside Integration Settings)
# ---------------------------------------------------------------------------


@bp.route("/api/health/dashboard", methods=["GET"])
@login_required
@admin_required
def api_health_dashboard():
    force = request.args.get("force") in {"1", "true", "yes"}
    try:
        return jsonify(IntegrationSettingsController().health_dashboard(force=force))
    except Exception as exc:
        current_app.logger.exception("Integration health dashboard failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/health/scan", methods=["POST"])
@login_required
@admin_required
def api_health_scan():
    try:
        return jsonify(IntegrationSettingsController().health_scan())
    except Exception as exc:
        current_app.logger.exception("Integration health scan failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/health/<provider>/detail", methods=["GET"])
@login_required
@admin_required
def api_health_detail(provider: str):
    try:
        return jsonify(IntegrationSettingsController().health_detail(provider))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/health/<provider>/refresh", methods=["POST"])
@login_required
@admin_required
def api_health_refresh(provider: str):
    try:
        return jsonify(IntegrationSettingsController().health_refresh(provider))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/health/<provider>/test", methods=["POST"])
@login_required
@admin_required
def api_health_test(provider: str):
    try:
        return jsonify(IntegrationSettingsController().health_test(provider))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/health/alerts", methods=["GET"])
@login_required
@admin_required
def api_health_alerts():
    try:
        return jsonify(IntegrationSettingsController().health_alerts())
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/health/history", methods=["GET"])
@login_required
@admin_required
def api_health_history():
    period = (request.args.get("period") or "daily").strip()
    try:
        return jsonify(IntegrationSettingsController().health_history(period))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/health/export", methods=["GET"])
@login_required
@admin_required
def api_health_export():
    fmt = (request.args.get("format") or "csv").strip().lower()
    try:
        filename, mimetype, body = IntegrationSettingsController().health_export(fmt)
        return Response(
            body,
            mimetype=mimetype,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
