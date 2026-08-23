from __future__ import annotations

import mimetypes

from flask import Blueprint, jsonify, redirect, render_template, request, send_file, url_for

from app.decorators import login_required
from app.services.credentials_master_service import CredentialsMasterService
from app.services.shcil_login_service import SHCIL_LOGIN_URL, ShcilLoginService
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
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        inline = str(request.args.get("inline") or "").lower() in {"1", "true", "yes"}
        response = send_file(path, as_attachment=not inline, download_name=name, mimetype=mime)
        response.headers["Cache-Control"] = "private, no-store"
        return response
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


@bp.route("/<reference_no>/generate", methods=["GET"])
@login_required
def generate_page(reference_no: str):
    try:
        order = WebsiteEStampService().get_order_dict(reference_no)
    except ValueError:
        return redirect(url_for("estamp_orders.index"))
    if (order.get("payment_confirmed") or "").lower() != "yes":
        return redirect(url_for("estamp_orders.index"))
    cred = CredentialsMasterService().find_shcil_login()
    return render_template(
        "estamp_orders/generate.html",
        page_title=f"Generate Stamp · {order.get('reference_no')}",
        order=order,
        shcil_login_url=SHCIL_LOGIN_URL,
        credential={
            "found": bool(cred),
            "activity": (cred or {}).get("activity") or "",
            "user_id": (cred or {}).get("user_id") or "",
            "url": (cred or {}).get("url") or SHCIL_LOGIN_URL,
            "has_password": bool((cred or {}).get("password")),
        },
    )


@bp.route("/<reference_no>/shcil-login", methods=["POST"])
@login_required
def shcil_login(reference_no: str):
    try:
        order = WebsiteEStampService().get_order_dict(reference_no)
        cred = CredentialsMasterService().find_shcil_login()
        if not cred:
            return jsonify({
                "ok": False,
                "error": "Add SHCIL / e-Stamp User ID and password in Credentials Master first.",
            }), 400
        result = ShcilLoginService().launch(
            cred.get("user_id") or "",
            cred.get("password") or "",
            reference_no=reference_no,
            order=order,
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"Unable to open SHCIL login: {exc}"}), 500


@bp.route("/<reference_no>/shcil-status", methods=["GET"])
@login_required
def shcil_status(reference_no: str):
    job_id = (request.args.get("job_id") or "").strip()
    if not job_id:
        return jsonify({"ok": False, "error": "job_id is required."}), 400
    job = ShcilLoginService().get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Login job not found."}), 404
    return jsonify({
        "ok": True,
        "job": {
            "job_id": job_id,
            "status": job.get("status") or "",
            "phase": job.get("phase") or "",
            "message": job.get("message") or "",
            "user_id": job.get("user_id") or "",
            "reference_no": job.get("reference_no") or reference_no,
        },
    })


def ensure_estamp_orders_menu() -> None:
    WebsiteEStampService().ensure_schema()
