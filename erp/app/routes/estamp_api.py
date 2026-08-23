"""Public e-Stamp purchase API for jtcsxpert.com (no login required)."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.website_estamp_service import WebsiteEStampService

bp = Blueprint("estamp_api", __name__, url_prefix="/api/estamp")


def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Accept, Content-Type"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@bp.after_request
def estamp_api_cors(response):
    return _cors(response)


@bp.route("/route-km", methods=["GET", "OPTIONS"], strict_slashes=False)
def route_km():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        lat = float(request.args.get("lat") or "")
        lng = float(request.args.get("lng") or "")
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Valid lat/lng required."}), 400
    from app.services.website_estamp_service import driving_route_km

    try:
        km, source = driving_route_km(lat, lng)
        return jsonify({"ok": True, "km": km, "source": source})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/articles", methods=["GET", "OPTIONS"], strict_slashes=False)
def articles():
    if request.method == "OPTIONS":
        return ("", 204)
    return jsonify({"ok": True, "articles": WebsiteEStampService().articles()})


@bp.route("/orders", methods=["POST", "OPTIONS"], strict_slashes=False)
def create_order():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        data = request.get_json(silent=True) or {}
        return jsonify(WebsiteEStampService().create_paid(data))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/orders/<reference_no>", methods=["POST", "OPTIONS"], strict_slashes=False)
def update_order(reference_no: str):
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.get_json(silent=True) or {}
    payload["reference_no"] = reference_no
    try:
        return jsonify(WebsiteEStampService().create_paid(payload))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/orders/<reference_no>/delete", methods=["POST", "OPTIONS"], strict_slashes=False)
def delete_order(reference_no: str):
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.get_json(silent=True) or {}
    try:
        WebsiteEStampService().delete(reference_no, payload.get("mobile") or "")
        return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/orders/<reference_no>/poi", methods=["POST", "OPTIONS"], strict_slashes=False)
def upload_poi(reference_no: str):
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        return jsonify(
            WebsiteEStampService().save_poi(
                reference_no,
                request.files.get("file"),
                request.form.get("poi_document_type") or "",
            )
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/orders/<reference_no>/pay", methods=["POST", "OPTIONS"], strict_slashes=False)
@bp.route("/orders/<reference_no>/pay/upi", methods=["POST", "OPTIONS"], strict_slashes=False)
@bp.route("/orders/<reference_no>/pay/verify", methods=["POST", "OPTIONS"], strict_slashes=False)
def pay_order(reference_no: str):
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.get_json(silent=True) or {}
    payload["reference_no"] = reference_no
    payload["paid"] = True
    payload["payment_status"] = "paid"
    try:
        return jsonify(WebsiteEStampService().create_paid(payload))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
