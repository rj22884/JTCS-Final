"""Public DSC application API for jtcsxpert.com (no login required)."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from app.services import dsc_documents
from app.services.website_dsc_service import WebsiteDscService

bp = Blueprint("dsc_api", __name__, url_prefix="/api/dsc")


def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Accept, Content-Type"
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
