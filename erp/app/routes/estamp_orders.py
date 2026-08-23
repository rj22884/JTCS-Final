from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request, send_file

from app.decorators import login_required
from app.services.website_estamp_service import WebsiteEStampService

bp = Blueprint("estamp_orders", __name__, url_prefix="/admin/estamp-orders")


@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
def index():
    return render_template("estamp_orders/index.html", page_title="e-Stamp Orders")


@bp.route("/exit", methods=["GET"])
@login_required
def exit_module():
    from flask import redirect, url_for

    return redirect(url_for("dashboard.index"))


@bp.route("/list", methods=["GET"])
@login_required
def list_orders():
    try:
        rows = WebsiteEStampService().list_paid()
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/review", methods=["POST"])
@login_required
def review():
    data = request.get_json(silent=True) or {}
    try:
        row = WebsiteEStampService().update_review(
            data.get("reference_no") or "",
            data.get("status") or "",
            data.get("review_notes") or "",
        )
        return jsonify({"ok": True, "row": row})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/<reference_no>/poi", methods=["GET"])
@login_required
def download_poi(reference_no: str):
    try:
        path, name = WebsiteEStampService().poi_file(reference_no)
        return send_file(path, as_attachment=True, download_name=name)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/<reference_no>/payment-confirm", methods=["POST"])
@login_required
def payment_confirm(reference_no: str):
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(WebsiteEStampService().set_payment_confirm(reference_no, data.get("confirmed") or ""))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/<reference_no>/reject", methods=["POST"])
@login_required
def reject_order(reference_no: str):
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(WebsiteEStampService().reject_order(reference_no, data.get("reason") or "rejected"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/<reference_no>/delete", methods=["POST"])
@login_required
def delete_order(reference_no: str):
    try:
        WebsiteEStampService().admin_delete(reference_no)
        return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/<reference_no>/update", methods=["POST"])
@login_required
def update_order(reference_no: str):
    data = request.get_json(silent=True) or {}
    try:
        return jsonify({"ok": True, "row": WebsiteEStampService().admin_update(reference_no, data)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/<reference_no>/generate-stamp", methods=["POST"])
@login_required
def generate_stamp(reference_no: str):
    try:
        return jsonify(WebsiteEStampService().generate_stamp(reference_no))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def ensure_estamp_orders_menu() -> None:
    WebsiteEStampService().ensure_schema()
