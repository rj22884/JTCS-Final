"""Customer Portal routes and JSON APIs (local JTCS ERP)."""

from __future__ import annotations

from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.decorators import customer_login_required, customer_password_changed_required
from app.services.customer_portal_service import CustomerPortalService

bp = Blueprint("customer_portal", __name__, url_prefix="/customer")


def _client_meta() -> tuple[str | None, str | None]:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip and "," in ip:
        ip = ip.split(",", 1)[0].strip()
    ua = request.headers.get("User-Agent")
    return ip, ua


def _wants_json() -> bool:
    if request.is_json:
        return True
    accept = request.headers.get("Accept") or ""
    return "application/json" in accept or request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _start_portal_session(result: dict) -> None:
    # Keep staff session keys untouched; portal uses separate keys.
    session["portal_customer_id"] = result["customer_id"]
    session["portal_customer_name"] = result.get("customer_name") or ""
    session["portal_password_changed"] = bool(result.get("password_changed"))
    session.permanent = True


@bp.route("/login", methods=["GET"], strict_slashes=False)
def login_page():
    if session.get("portal_customer_id"):
        if session.get("portal_password_changed"):
            return redirect(url_for("customer_portal.dashboard"))
        return redirect(url_for("customer_portal.change_password_page"))
    return render_template(
        "customer_portal/login.html",
        page_title="Client / Customer Login",
    )


@bp.route("/change-password", methods=["GET"], strict_slashes=False)
@customer_login_required
def change_password_page():
    if session.get("portal_password_changed"):
        return redirect(url_for("customer_portal.dashboard"))
    return render_template(
        "customer_portal/change_password.html",
        page_title="Change Password",
        customer_name=session.get("portal_customer_name") or "",
        force_change=True,
    )


@bp.route("/dashboard", methods=["GET"], strict_slashes=False)
@customer_password_changed_required
def dashboard():
    return render_template(
        "customer_portal/dashboard.html",
        page_title="Customer Dashboard",
        customer_name=session.get("portal_customer_name") or "",
    )


@bp.route("/logout", methods=["GET", "POST"], strict_slashes=False)
def logout():
    for key in (
        "portal_customer_id",
        "portal_customer_name",
        "portal_password_changed",
    ):
        session.pop(key, None)
    return redirect(url_for("customer_portal.login_page"))


# ---------------------------------------------------------------------------
# JSON APIs
# ---------------------------------------------------------------------------


@bp.route("/login", methods=["POST"], strict_slashes=False)
def login_api():
    """POST /customer/login"""
    payload = request.get_json(silent=True) or request.form.to_dict()
    user_id = (payload.get("user_id") or payload.get("userid") or "").strip()
    password = payload.get("password") or ""
    ip, ua = _client_meta()
    result = CustomerPortalService().login(
        user_id,
        password,
        ip_address=ip,
        user_agent=ua,
    )
    if not result.get("ok"):
        body = {
            "ok": False,
            "error": result.get("error"),
            "error_code": result.get("error_code"),
            "duplicates": result.get("duplicates"),
            "detected_type": result.get("detected_type"),
        }
        return jsonify(body), int(result.get("status_code") or 400)

    _start_portal_session(result)
    return jsonify(
        {
            "ok": True,
            "customer_id": result["customer_id"],
            "customer_name": result.get("customer_name"),
            "must_change_password": result.get("must_change_password"),
            "redirect": result.get("redirect"),
            "detected_type": result.get("detected_type"),
        }
    )


@bp.route("/reset-password", methods=["POST"], strict_slashes=False)
def reset_password_api():
    """POST /customer/reset-password"""
    payload = request.get_json(silent=True) or request.form.to_dict()
    user_id = (payload.get("user_id") or payload.get("userid") or "").strip()
    ip, ua = _client_meta()
    result = CustomerPortalService().reset_password(
        user_id,
        ip_address=ip,
        user_agent=ua,
    )
    if not result.get("ok"):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": result.get("error"),
                    "error_code": result.get("error_code"),
                    "duplicates": result.get("duplicates"),
                    "detected_type": result.get("detected_type"),
                }
            ),
            int(result.get("status_code") or 400),
        )
    return jsonify(
        {
            "ok": True,
            "message": result.get("message"),
            "temporary_password": result.get("temporary_password"),
            "detected_type": result.get("detected_type"),
        }
    )


@bp.route("/change-password", methods=["POST"], strict_slashes=False)
@customer_login_required
def change_password_api():
    """POST /customer/change-password"""
    payload = request.get_json(silent=True) or request.form.to_dict()
    result = CustomerPortalService().change_password(
        int(session["portal_customer_id"]),
        payload.get("old_password") or "",
        payload.get("new_password") or "",
        payload.get("confirm_password") or "",
    )
    if not result.get("ok"):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": result.get("error"),
                    "error_code": result.get("error_code"),
                }
            ),
            int(result.get("status_code") or 400),
        )
    session["portal_password_changed"] = True
    return jsonify(
        {
            "ok": True,
            "message": result.get("message"),
            "redirect": result.get("redirect") or url_for("customer_portal.dashboard"),
        }
    )


@bp.route("/profile", methods=["GET"], strict_slashes=False)
@customer_login_required
def profile_api():
    """GET /customer/profile"""
    result = CustomerPortalService().get_profile(int(session["portal_customer_id"]))
    if not result.get("ok"):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": result.get("error"),
                    "error_code": result.get("error_code"),
                }
            ),
            int(result.get("status_code") or 404),
        )
    return jsonify(result)
