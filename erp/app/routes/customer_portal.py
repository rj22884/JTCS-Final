"""Customer Portal routes and JSON APIs (local JTCS ERP)."""

from __future__ import annotations

from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from app.customer_master.constants import GENDERS, GST_FILING_FREQUENCIES
from app.customer_master.countries import COUNTRIES
from app.customer_portal.constants import PORTAL_MODULES, PORTAL_PROFILE_SECTIONS
from app.decorators import customer_login_required, customer_password_changed_required
from app.services.customer_portal_service import CustomerPortalService

bp = Blueprint("customer_portal", __name__, url_prefix="/customer")


def _client_meta() -> tuple[str | None, str | None]:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip and "," in ip:
        ip = ip.split(",", 1)[0].strip()
    ua = request.headers.get("User-Agent")
    return ip, ua


def _portal_customer_id() -> int | None:
    raw = session.get("portal_customer_id")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _start_portal_session(result: dict) -> None:
    session["portal_customer_id"] = result["customer_id"]
    session["portal_customer_name"] = result.get("customer_name") or ""
    session["portal_password_changed"] = bool(result.get("password_changed"))
    session.permanent = True


_SETUP_SESSION_KEYS = (
    "portal_setup_customer_id",
    "portal_setup_user_id",
    "portal_setup_detected",
    "portal_setup_verify_field",
    "portal_setup_verified",
    "portal_setup_for_reset",
)


def _clear_setup_session() -> None:
    for key in _SETUP_SESSION_KEYS:
        session.pop(key, None)


def _json_error(result: dict):
    payload = {
        "ok": False,
        "error": result.get("error"),
        "error_code": result.get("error_code"),
        "duplicates": result.get("duplicates"),
        "detected_type": result.get("detected_type"),
    }
    for key in (
        "next",
        "verify_field",
        "masked_value",
        "field_label",
        "field_hint",
        "customer_name",
    ):
        if key in result:
            payload[key] = result.get(key)
    return jsonify(payload), int(result.get("status_code") or 400)


def _safe_next(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if value.startswith("/customer/") and "//" not in value and "\\" not in value:
        return value
    return None


@bp.route("/login", methods=["GET"], strict_slashes=False)
def login_page():
    nxt = _safe_next(request.args.get("next"))
    if session.get("portal_customer_id"):
        if session.get("portal_password_changed"):
            return redirect(nxt or url_for("customer_portal.dashboard"))
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
    modules = []
    for key, meta in PORTAL_MODULES.items():
        href = (
            url_for("customer_portal.profile_page")
            if key == "profile"
            else url_for("customer_portal.module_page", module_key=key)
        )
        modules.append({**meta, "key": key, "href": href})
    return render_template(
        "customer_portal/dashboard.html",
        page_title="Customer Dashboard",
        customer_name=session.get("portal_customer_name") or "",
        modules=modules,
    )


@bp.route("/profile", methods=["GET"], strict_slashes=False)
@customer_password_changed_required
def profile_page():
    cid = _portal_customer_id()
    result = CustomerPortalService().get_profile(cid)
    if not result.get("ok"):
        return redirect(url_for("customer_portal.dashboard"))
    return render_template(
        "customer_portal/profile.html",
        page_title="Customer Profile",
        customer_name=session.get("portal_customer_name") or "",
        profile=result["profile"],
        sections=PORTAL_PROFILE_SECTIONS,
        genders=GENDERS,
        countries=COUNTRIES,
        gst_filing_frequencies=GST_FILING_FREQUENCIES,
    )


@bp.route("/module/<module_key>", methods=["GET"], strict_slashes=False)
@customer_password_changed_required
def module_page(module_key: str):
    key = (module_key or "").strip().lower()
    if key == "profile":
        return redirect(url_for("customer_portal.profile_page"))
    if key not in PORTAL_MODULES:
        return redirect(url_for("customer_portal.dashboard"))
    cid = _portal_customer_id()
    result = CustomerPortalService().get_module_data(cid, key)
    if not result.get("ok"):
        return redirect(url_for("customer_portal.dashboard"))
    return render_template(
        "customer_portal/module.html",
        page_title=result.get("title") or "Module",
        customer_name=session.get("portal_customer_name") or "",
        module=result,
    )


@bp.route("/logout", methods=["GET", "POST"], strict_slashes=False)
def logout():
    for key in (
        "portal_customer_id",
        "portal_customer_name",
        "portal_password_changed",
    ):
        session.pop(key, None)
    _clear_setup_session()
    return redirect(url_for("customer_portal.login_page"))


# ---------------------------------------------------------------------------
# JSON APIs
# ---------------------------------------------------------------------------


@bp.route("/login/start", methods=["POST"], strict_slashes=False)
def login_start_api():
    """Step 1 — User ID lookup: password login OR identity verify for first setup."""
    payload = request.get_json(silent=True) or request.form.to_dict()
    user_id = (payload.get("user_id") or payload.get("userid") or "").strip()
    for_reset = bool(payload.get("for_reset"))
    ip, ua = _client_meta()
    result = CustomerPortalService().begin_login(
        user_id, ip_address=ip, user_agent=ua, for_reset=for_reset
    )
    if not result.get("ok"):
        _clear_setup_session()
        return _json_error(result)

    _clear_setup_session()
    if result.get("next") == "verify_identity":
        session["portal_setup_customer_id"] = result["customer_id"]
        session["portal_setup_user_id"] = user_id
        session["portal_setup_detected"] = result.get("detected_type")
        session["portal_setup_verify_field"] = result.get("verify_field")
        session["portal_setup_verified"] = False
        session["portal_setup_for_reset"] = bool(result.get("for_reset"))
        return jsonify(
            {
                "ok": True,
                "next": "verify_identity",
                "customer_name": result.get("customer_name"),
                "detected_type": result.get("detected_type"),
                "verify_field": result.get("verify_field"),
                "masked_value": result.get("masked_value"),
                "field_label": result.get("field_label"),
                "field_hint": result.get("field_hint"),
                "for_reset": bool(result.get("for_reset")),
            }
        )

    return jsonify(
        {
            "ok": True,
            "next": "password",
            "customer_name": result.get("customer_name"),
            "detected_type": result.get("detected_type"),
        }
    )


@bp.route("/login/verify", methods=["POST"], strict_slashes=False)
def login_verify_api():
    """Step 2 — confirm masked Mobile / Email / PAN before first password create / reset."""
    payload = request.get_json(silent=True) or request.form.to_dict()
    user_id = (
        (payload.get("user_id") or payload.get("userid") or "").strip()
        or (session.get("portal_setup_user_id") or "")
    )
    verify_value = (
        payload.get("verify_value")
        or payload.get("pan")
        or payload.get("mobile")
        or payload.get("email")
        or payload.get("aadhaar")
        or ""
    )
    setup_cid = session.get("portal_setup_customer_id")
    ip, ua = _client_meta()
    result = CustomerPortalService().verify_identity(
        user_id,
        str(verify_value),
        customer_id=int(setup_cid) if setup_cid is not None else None,
        ip_address=ip,
        user_agent=ua,
    )
    if not result.get("ok"):
        session["portal_setup_verified"] = False
        return _json_error(result)

    session["portal_setup_customer_id"] = result["customer_id"]
    session["portal_setup_user_id"] = user_id
    session["portal_setup_detected"] = result.get("detected_type")
    session["portal_setup_verify_field"] = result.get("verify_field")
    session["portal_setup_verified"] = True
    return jsonify(
        {
            "ok": True,
            "next": "set_password",
            "customer_name": result.get("customer_name"),
            "detected_type": result.get("detected_type"),
        }
    )


@bp.route("/login/set-password", methods=["POST"], strict_slashes=False)
def login_set_password_api():
    """Step 3 — create password after successful identity verification."""
    if not session.get("portal_setup_verified") or not session.get("portal_setup_customer_id"):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Please verify your identity first.",
                    "error_code": "not_verified",
                }
            ),
            403,
        )
    payload = request.get_json(silent=True) or request.form.to_dict()
    ip, ua = _client_meta()
    result = CustomerPortalService().set_first_password(
        int(session["portal_setup_customer_id"]),
        payload.get("new_password") or "",
        payload.get("confirm_password") or "",
        user_id_input=session.get("portal_setup_user_id"),
        detected_type=session.get("portal_setup_detected"),
        ip_address=ip,
        user_agent=ua,
    )
    if not result.get("ok"):
        return _json_error(result)
    _clear_setup_session()
    _start_portal_session(result)
    return jsonify(
        {
            "ok": True,
            "message": result.get("message"),
            "redirect": result.get("redirect") or url_for("customer_portal.dashboard"),
            "customer_name": result.get("customer_name"),
        }
    )


@bp.route("/login", methods=["POST"], strict_slashes=False)
def login_api():
    payload = request.get_json(silent=True) or request.form.to_dict()
    user_id = (payload.get("user_id") or payload.get("userid") or "").strip()
    password = payload.get("password") or ""
    ip, ua = _client_meta()
    result = CustomerPortalService().login(
        user_id, password, ip_address=ip, user_agent=ua
    )
    if not result.get("ok"):
        if result.get("error_code") == "needs_setup":
            _clear_setup_session()
            session["portal_setup_customer_id"] = result.get("customer_id")
            session["portal_setup_user_id"] = user_id
            session["portal_setup_detected"] = result.get("detected_type")
            session["portal_setup_verify_field"] = result.get("verify_field")
            session["portal_setup_verified"] = False
        return _json_error(result)
    _clear_setup_session()
    _start_portal_session(result)
    return jsonify(
        {
            "ok": True,
            "customer_id": result["customer_id"],
            "customer_name": result.get("customer_name"),
            "must_change_password": False,
            "redirect": result.get("redirect"),
            "detected_type": result.get("detected_type"),
        }
    )


@bp.route("/reset-password", methods=["POST"], strict_slashes=False)
def reset_password_api():
    """Starts identity-verify + create-password flow (no Admin@123)."""
    payload = request.get_json(silent=True) or request.form.to_dict()
    user_id = (payload.get("user_id") or payload.get("userid") or "").strip()
    ip, ua = _client_meta()
    result = CustomerPortalService().reset_password(
        user_id, ip_address=ip, user_agent=ua
    )
    if not result.get("ok"):
        _clear_setup_session()
        return _json_error(result)

    _clear_setup_session()
    session["portal_setup_customer_id"] = result["customer_id"]
    session["portal_setup_user_id"] = user_id
    session["portal_setup_detected"] = result.get("detected_type")
    session["portal_setup_verify_field"] = result.get("verify_field")
    session["portal_setup_verified"] = False
    session["portal_setup_for_reset"] = True
    return jsonify(
        {
            "ok": True,
            "next": "verify_identity",
            "message": "Verify your identity to create a new password.",
            "customer_name": result.get("customer_name"),
            "detected_type": result.get("detected_type"),
            "verify_field": result.get("verify_field"),
            "masked_value": result.get("masked_value"),
            "field_label": result.get("field_label"),
            "field_hint": result.get("field_hint"),
        }
    )


@bp.route("/change-password", methods=["POST"], strict_slashes=False)
@customer_login_required
def change_password_api():
    payload = request.get_json(silent=True) or request.form.to_dict()
    result = CustomerPortalService().change_password(
        int(session["portal_customer_id"]),
        payload.get("old_password") or "",
        payload.get("new_password") or "",
        payload.get("confirm_password") or "",
        skip_old_password=not bool(session.get("portal_password_changed")),
    )
    if not result.get("ok"):
        return _json_error(result)
    session["portal_password_changed"] = True
    return jsonify(
        {
            "ok": True,
            "message": result.get("message"),
            "redirect": result.get("redirect") or url_for("customer_portal.dashboard"),
        }
    )


@bp.route("/api/profile", methods=["GET"], strict_slashes=False)
@customer_login_required
def profile_api():
    """GET /customer/api/profile — logged-in customer only."""
    cid = _portal_customer_id()
    result = CustomerPortalService().get_profile(cid)
    if not result.get("ok"):
        return _json_error(result)
    return jsonify(result)


@bp.route("/api/profile", methods=["POST", "PUT"], strict_slashes=False)
@customer_password_changed_required
def profile_update_api():
    """POST/PUT /customer/api/profile — update own Customer Master profile only."""
    cid = _portal_customer_id()
    if cid is None:
        return jsonify({"ok": False, "error": "Unauthorized.", "error_code": "auth"}), 401

    if request.is_json:
        payload = request.get_json(silent=True) or {}
        photo = None
    else:
        payload = request.form.to_dict()
        photo = request.files.get("photo")

    # Security: ignore any customer_id supplied by the client.
    payload.pop("customer_id", None)
    payload.pop("customer_name", None)
    payload.pop("pan_number", None)

    ip, ua = _client_meta()
    result = CustomerPortalService().update_profile(
        cid,
        payload,
        photo_file=photo,
        actor_name=session.get("portal_customer_name") or f"Customer:{cid}",
        ip_address=ip,
        user_agent=ua,
    )
    if not result.get("ok"):
        return _json_error(result)
    if result.get("profile", {}).get("customer_name"):
        session["portal_customer_name"] = result["profile"]["customer_name"]
    return jsonify(
        {
            "ok": True,
            "message": result.get("message") or "Profile updated successfully.",
            "profile": result.get("profile"),
            "changed_fields": result.get("changed_fields") or [],
        }
    )


@bp.route("/api/module/<module_key>", methods=["GET"], strict_slashes=False)
@customer_password_changed_required
def module_api(module_key: str):
    """GET /customer/api/module/<key> — always scoped to session CustomerID."""
    cid = _portal_customer_id()
    key = (module_key or "").strip().lower()
    result = CustomerPortalService().get_module_data(cid, key)
    if not result.get("ok"):
        return _json_error(result)
    return jsonify(result)


# Back-compat alias used by older portal JS.
@bp.route("/profile-data", methods=["GET"], strict_slashes=False)
@customer_login_required
def profile_api_legacy():
    return profile_api()


@bp.route("/api/dsc-docs/<kind>", methods=["GET", "POST"], strict_slashes=False)
@customer_password_changed_required
def dsc_document(kind: str):
    from app.services import dsc_documents

    cid = _portal_customer_id()
    if cid is None:
        return jsonify({"ok": False, "error": "Unauthorized."}), 401
    if request.method == "POST":
        try:
            result = dsc_documents.save_customer_doc(
                cid,
                kind,
                request.files.get("file"),
                actor=session.get("portal_customer_name") or f"Customer:{cid}",
            )
            return jsonify(result)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
    try:
        path, name = dsc_documents.customer_doc_file(cid, kind)
        inline = str(request.args.get("inline") or "") == "1"
        return send_file(path, as_attachment=not inline, download_name=name)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
