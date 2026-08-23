from __future__ import annotations

from flask import Blueprint, jsonify, render_template, redirect, url_for

from app.decorators import login_required
from app.services.website_dsc_service import WebsiteDscService

bp = Blueprint("dsc_orders", __name__, url_prefix="/admin/dsc-orders")


@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
def index():
    return render_template("dsc_orders/index.html", page_title="DSC Applications")


@bp.route("/exit", methods=["GET"])
@login_required
def exit_module():
    return redirect(url_for("dashboard.index"))


@bp.route("/list", methods=["GET"])
@login_required
def list_orders():
    try:
        rows = WebsiteDscService().list_applications()
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


def ensure_dsc_orders_menu() -> None:
    WebsiteDscService().ensure_schema()
