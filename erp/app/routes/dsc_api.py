"""Public DSC application API for jtcsxpert.com (no login required)."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, send_file

from app.services import dsc_documents
from app.services.website_dsc_portal import WebsiteDscPortalService, require_session
from app.services.website_dsc_service import WebsiteDscService

bp = Blueprint("dsc_api", __name__, url_prefix="/api/dsc")


def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Accept, Content-Type, Authorization"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@bp.after_request
def dsc_api_cors(response):
    return _cors(response)


@bp.route("/options", methods=["GET", "OPTIONS"], strict_slashes=False)
def options():
    if request.method == "OPTIONS":
        return ("", 204)
    return jsonify(WebsiteDscService().options())


@bp.route("/trust-stats", methods=["GET", "OPTIONS"], strict_slashes=False)
def trust_stats():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        count = dsc_documents.customer_master_count()
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify(
        {
            "ok": True,
            "customer_count": count,
            "dsc_issued": count,
        }
    )


@bp.route("/pan-check", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def pan_check():
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.get_json(silent=True) or {}
    pan = (request.args.get("pan") or payload.get("pan") or "").strip().upper()
    if not pan:
        return jsonify({"ok": False, "error": "Enter PAN."}), 400
    try:
        found = dsc_documents.pan_exists(pan)
        docs = dsc_documents.docs_for_pan(pan) if found else []
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    login_url = "https://app.jtcsxpert.com/customer/login"
    if found:
        login_url += f"?userid={pan}&next=/customer/module/documents"
    return jsonify(
        {
            "ok": True,
            "found": found,
            "login_url": login_url if found else "",
            "website_login": "/pages/login.html?from=dsc&pan=" + pan if found else "",
            "docs": docs,
        }
    )


@bp.route("/gstin-search", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def gstin_search():
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.get_json(silent=True) or {}
    gstin = request.args.get("gstin") or payload.get("gstin") or ""
    try:
        return jsonify(dsc_documents.search_gstin(gstin))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/authorization-letter-pdf", methods=["POST", "OPTIONS"], strict_slashes=False)
def authorization_letter_pdf():
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.get_json(silent=True) or {}
    pdf = dsc_documents.authorization_letter_pdf(payload)
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="DSC-Authorization-Letter.pdf"'},
    )


@bp.route("/authorization-letter-template", methods=["GET", "OPTIONS"], strict_slashes=False)
def authorization_template():
    if request.method == "OPTIONS":
        return ("", 204)
    pdf = dsc_documents.authorization_letter_pdf({})
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="DSC-Authorization-Letter.pdf"'},
    )


@bp.route("/applications", methods=["POST", "OPTIONS"], strict_slashes=False)
def create_application():
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.get_json(silent=True) or {}
    try:
        result = WebsiteDscService().upsert(payload, paid=False)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/applications/<reference_no>/letter", methods=["POST", "OPTIONS"], strict_slashes=False)
def upload_letter(reference_no: str):
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        return jsonify(WebsiteDscService().save_document(reference_no, "auth_letter", request.files.get("file")))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/applications/<reference_no>/document", methods=["POST", "OPTIONS"], strict_slashes=False)
def upload_document(reference_no: str):
    if request.method == "OPTIONS":
        return ("", 204)
    kind = (request.form.get("kind") or request.args.get("kind") or "auth_letter").strip().lower()
    try:
        return jsonify(WebsiteDscService().save_document(reference_no, kind, request.files.get("file")))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/applications/<reference_no>/pay", methods=["POST", "OPTIONS"], strict_slashes=False)
def pay_application(reference_no: str):
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.get_json(silent=True) or {}
    payload["reference_no"] = reference_no
    payload["paid"] = True
    payload["payment_status"] = "paid"
    try:
        return jsonify(WebsiteDscService().upsert(payload, paid=True))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/applications/<reference_no>/invoice", methods=["GET", "OPTIONS"], strict_slashes=False)
def invoice(reference_no: str):
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        html = WebsiteDscService().invoice_html(reference_no)
        return Response(html, mimetype="text/html; charset=utf-8")
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


def _json_payload() -> dict:
    return request.get_json(silent=True) or {}


def _portal_reply(result: dict):
    status = int(result.get("status_code") or (200 if result.get("ok") else 400))
    return jsonify(result), status


def _portal_guard(exc: Exception):
    msg = str(exc)
    lowered = msg.lower()
    code = 401 if ("login" in lowered or "expired" in lowered or "invalid login" in lowered) else 400
    return jsonify({"ok": False, "error": msg}), code


@bp.route("/portal/login/start", methods=["POST", "OPTIONS"], strict_slashes=False)
def portal_login_start():
    if request.method == "OPTIONS":
        return ("", 204)
    payload = _json_payload()
    user_id = (payload.get("user_id") or request.form.get("user_id") or "").strip()
    return _portal_reply(WebsiteDscPortalService().login_start(user_id))


@bp.route("/portal/login", methods=["POST", "OPTIONS"], strict_slashes=False)
def portal_login():
    if request.method == "OPTIONS":
        return ("", 204)
    payload = _json_payload()
    user_id = (payload.get("user_id") or request.form.get("user_id") or "").strip()
    password = payload.get("password") or request.form.get("password") or ""
    return _portal_reply(WebsiteDscPortalService().login_password(user_id, password))


@bp.route("/portal/login/verify", methods=["POST", "OPTIONS"], strict_slashes=False)
def portal_login_verify():
    if request.method == "OPTIONS":
        return ("", 204)
    payload = _json_payload()
    return _portal_reply(
        WebsiteDscPortalService().login_verify(
            (payload.get("user_id") or "").strip(),
            payload.get("verify_value") or "",
            payload.get("setup_token") or "",
        )
    )


@bp.route("/portal/login/set-password", methods=["POST", "OPTIONS"], strict_slashes=False)
def portal_login_set_password():
    if request.method == "OPTIONS":
        return ("", 204)
    payload = _json_payload()
    return _portal_reply(
        WebsiteDscPortalService().login_set_password(
            payload.get("new_password") or "",
            payload.get("confirm_password") or "",
            payload.get("setup_token") or "",
        )
    )


@bp.route("/portal/login/reset", methods=["POST", "OPTIONS"], strict_slashes=False)
def portal_login_reset():
    if request.method == "OPTIONS":
        return ("", 204)
    payload = _json_payload()
    user_id = (payload.get("user_id") or request.form.get("user_id") or "").strip()
    return _portal_reply(WebsiteDscPortalService().reset_password(user_id))


@bp.route("/portal/docs", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def portal_docs():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        session = require_session()
        svc = WebsiteDscPortalService()
        if request.method == "POST":
            saved = 0
            for kind, _label in (("pan", ""), ("aadhaar", ""), ("org_id", ""), ("auth_letter", "")):
                fs = request.files.get(kind)
                if fs and getattr(fs, "filename", None):
                    svc.save_doc(session, kind, fs)
                    saved += 1
            single = request.files.get("file")
            kind = (request.form.get("kind") or "").strip().lower()
            if single and getattr(single, "filename", None) and kind:
                svc.save_doc(session, kind, single)
                saved += 1
            if saved == 0:
                return jsonify({"ok": False, "error": "Choose a new file to save."}), 400
        return jsonify(svc.docs(session))
    except ValueError as exc:
        return _portal_guard(exc)


@bp.route("/portal/docs/<kind>", methods=["GET", "OPTIONS"], strict_slashes=False)
def portal_doc_file(kind: str):
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        session = require_session()
        path, name = WebsiteDscPortalService().doc_file(session, kind)
        inline = str(request.args.get("inline") or "1") == "1"
        return send_file(path, as_attachment=not inline, download_name=name)
    except ValueError as exc:
        return _portal_guard(exc)
