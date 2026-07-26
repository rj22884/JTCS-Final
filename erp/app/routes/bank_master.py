from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, require_delete_reauth
from app.services.bank_master_service import BankMasterService
from app.services.menu_service import MenuService
from app.utils.db_session import map_db_exception

bp = Blueprint("bank_master", __name__, url_prefix="/masters/bank")


@bp.route("/", strict_slashes=False)
@login_required
def index():
    # Keep Account Type Master menu available under Masters.
    try:
        from app.routes.masters_account_type import _ensure_menu

        _ensure_menu()
    except Exception:
        from app.extensions import db

        db.session.rollback()

    menu_service = MenuService()
    service = BankMasterService()
    rows = service.list_records()
    return render_template(
        "bank_master/index.html",
        page_title="Bank Master",
        breadcrumb=menu_service.get_breadcrumb("/masters/bank", session.get("role")),
        account_types=service.list_account_types_for_form(),
        initial_rows=rows,
    )


@bp.route("/api/records")
@login_required
def list_records():
    search = (request.args.get("search") or "").strip() or None
    rows = BankMasterService().list_records(search=search)
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


@bp.route("/api/records/<int:account_id>")
@login_required
def get_record(account_id: int):
    try:
        record = BankMasterService().get_record(account_id)
        return jsonify({"ok": True, "record": record})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/records", methods=["POST"])
@login_required
def create_record():
    try:
        record = BankMasterService().create_record(request.form)
        return jsonify({"ok": True, "record": record, "message": "Bank account added successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:account_id>", methods=["POST"])
@login_required
def update_record(account_id: int):
    try:
        record = BankMasterService().update_record(account_id, request.form)
        return jsonify({"ok": True, "record": record, "message": "Bank account updated successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:account_id>/delete", methods=["POST"])
@login_required
@require_delete_reauth
def delete_record(account_id: int):
    try:
        message = BankMasterService().delete_record(account_id)
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/exit")
@login_required
def exit_module():
    return redirect(url_for("dashboard.index"))
