from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, require_delete_reauth
from app.extensions import db
from app.services.customer_group_service import CustomerGroupService
from app.services.menu_service import MenuService
from app.utils.master_delete_guard import MasterInUseError, json_in_use_response

bp = Blueprint("masters_group", __name__, url_prefix="/masters/group")
MENU_PATH = "/masters/group"


@bp.route("", strict_slashes=False)
@bp.route("/", strict_slashes=False)
@login_required
def index():
    service = CustomerGroupService()
    service.repository.ensure_schema()
    db.session.commit()
    menu_service = MenuService()
    return render_template(
        "masters/group_master.html",
        page_title="Customer Group Master",
        breadcrumb=menu_service.get_breadcrumb(MENU_PATH, session.get("role")),
        initial_rows=service.list_records(),
        ui_config=service.ui_config(),
    )


@bp.route("/api/records", strict_slashes=False)
@login_required
def list_records():
    search = (request.args.get("search") or "").strip() or None
    rows = CustomerGroupService().list_records(search=search)
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


@bp.route("/api/records/<int:group_id>", strict_slashes=False)
@login_required
def get_record(group_id: int):
    try:
        record = CustomerGroupService().get_record(group_id)
        return jsonify({"ok": True, "record": record})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/records", methods=["POST"], strict_slashes=False)
@login_required
def create_record():
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = CustomerGroupService().create_record(payload)
        return jsonify({"ok": True, "record": record, "message": "Group added successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/records/<int:group_id>", methods=["POST"], strict_slashes=False)
@login_required
def update_record(group_id: int):
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = CustomerGroupService().update_record(group_id, payload)
        return jsonify({"ok": True, "record": record, "message": "Group updated successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/records/<int:group_id>/activate", methods=["POST"], strict_slashes=False)
@login_required
def activate_record(group_id: int):
    try:
        record = CustomerGroupService().activate_record(group_id)
        return jsonify({"ok": True, "record": record, "message": "Group activated successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/records/<int:group_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def delete_record(group_id: int):
    try:
        message = CustomerGroupService().delete_record(group_id)
        return jsonify({"ok": True, "message": message})
    except MasterInUseError as exc:
        return json_in_use_response(exc)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/exit", strict_slashes=False)
@login_required
def exit_module():
    return redirect(url_for("dashboard.index"))
