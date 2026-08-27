from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, require_delete_reauth
from app.services.menu_service import MenuService
from app.services.purpose_master_service import PurposeMasterService
from app.utils.db_session import map_db_exception
from app.utils.master_delete_guard import MasterInUseError, json_in_use_response

bp = Blueprint("purpose_master", __name__, url_prefix="/masters/purpose")


@bp.route("", strict_slashes=False)
@bp.route("/", strict_slashes=False)
@login_required
def index():
    menu_service = MenuService()
    try:
        rows = PurposeMasterService().list_records()
    except Exception:
        rows = []
    return render_template(
        "purpose_master/index.html",
        page_title="Purpose Master",
        breadcrumb=menu_service.get_breadcrumb("/masters/purpose", session.get("role")),
        initial_rows=rows,
    )


@bp.route("/api/records")
@login_required
def list_records():
    search = (request.args.get("search") or "").strip() or None
    active_only = (request.args.get("active_only") or "").strip().lower() in {"1", "true", "yes"}
    rows = PurposeMasterService().list_records(search=search, active_only=active_only)
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


@bp.route("/api/records/<int:purpose_id>")
@login_required
def get_record(purpose_id: int):
    try:
        record = PurposeMasterService().get_record(purpose_id)
        return jsonify({"ok": True, "record": record})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/records", methods=["POST"])
@login_required
def create_record():
    try:
        record = PurposeMasterService().create_record(
            request.form,
            created_by=session.get("user_name", "System"),
        )
        return jsonify({"ok": True, "record": record, "message": "Purpose added successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:purpose_id>", methods=["POST"])
@login_required
def update_record(purpose_id: int):
    try:
        record = PurposeMasterService().update_record(purpose_id, request.form)
        return jsonify({"ok": True, "record": record, "message": "Purpose updated successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:purpose_id>/delete", methods=["POST"])
@login_required
@require_delete_reauth
def delete_record(purpose_id: int):
    try:
        message = PurposeMasterService().delete_record(purpose_id)
        return jsonify({"ok": True, "message": message})
    except MasterInUseError as exc:
        return json_in_use_response(exc)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/exit")
@login_required
def exit_module():
    return redirect(url_for("dashboard.index"))
