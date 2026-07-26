from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, require_delete_reauth
from app.services.menu_service import MenuService
from app.services.rd_account_service import RdAccountService
from app.utils.db_session import map_db_exception

bp = Blueprint("rd_account", __name__, url_prefix="/masters/rd-account")


@bp.route("/", strict_slashes=False)
@login_required
def index():
    menu_service = MenuService()
    rows = RdAccountService().list_records()
    return render_template(
        "rd_account/index.html",
        page_title="RD Account",
        breadcrumb=menu_service.get_breadcrumb("/masters/rd-account", session.get("role")),
        initial_rows=rows,
    )


@bp.route("/api/records")
@login_required
def list_records():
    search = (request.args.get("search") or "").strip() or None
    rows = RdAccountService().list_records(search=search)
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


@bp.route("/api/records/<int:rd_account_id>")
@login_required
def get_record(rd_account_id: int):
    try:
        record = RdAccountService().get_record(rd_account_id)
        return jsonify({"ok": True, "record": record})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/records", methods=["POST"])
@login_required
def create_record():
    try:
        record = RdAccountService().create_record(
            request.form,
            created_by=session.get("user_name", "System"),
        )
        return jsonify({"ok": True, "record": record, "message": "RD account added successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:rd_account_id>", methods=["POST"])
@login_required
def update_record(rd_account_id: int):
    try:
        record = RdAccountService().update_record(rd_account_id, request.form)
        return jsonify({"ok": True, "record": record, "message": "RD account updated successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:rd_account_id>/delete", methods=["POST"])
@login_required
@require_delete_reauth
def delete_record(rd_account_id: int):
    try:
        message = RdAccountService().delete_record(rd_account_id)
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/exit")
@login_required
def exit_module():
    return redirect(url_for("dashboard.index"))
