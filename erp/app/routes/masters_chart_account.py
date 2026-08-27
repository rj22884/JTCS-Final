from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, require_delete_reauth
from app.services.chart_account_service import ChartAccountService
from app.services.menu_service import MenuService
from app.utils.db_session import map_db_exception
from app.utils.master_delete_guard import MasterInUseError, json_in_use_response

bp = Blueprint("masters_chart_account", __name__, url_prefix="/masters/chart-account")

MENU_PATH = "/masters/chart-account"


def _ensure_menu() -> None:
    from sqlalchemy import text

    from app.extensions import db

    db.session.execute(
        text(
            """
            DECLARE @MastersID INT;
            SELECT TOP 1 @MastersID = MenuID
            FROM dbo.MenuMaster
            WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
            ORDER BY MenuID;

            IF @MastersID IS NOT NULL
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM dbo.MenuMaster
                    WHERE ParentMenuID = @MastersID AND MenuName = N'Chart of Account Master'
                )
                    UPDATE dbo.MenuMaster
                    SET MenuURL = N'/masters/chart-account',
                        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-journal-text'),
                        DisplayOrder = 31,
                        Description = N'Customer / ledger accounts — assign Chart of Group',
                        IsActive = 1
                    WHERE ParentMenuID = @MastersID AND MenuName = N'Chart of Account Master';
                ELSE
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @MastersID,
                        N'Chart of Account Master',
                        N'bi-journal-text',
                        N'/masters/chart-account',
                        31,
                        N'Customer / ledger accounts — assign Chart of Group',
                        1,
                        NULL
                    );
            END
            """
        )
    )
    db.session.commit()


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
def index():
    try:
        _ensure_menu()
    except Exception:
        from app.extensions import db

        db.session.rollback()
    service = ChartAccountService()
    rows = service.list_records()
    return render_template(
        "masters/chart_account.html",
        page_title="Chart of Account Master",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        initial_rows=rows,
    )


@bp.route("/api/records", methods=["GET"], strict_slashes=False)
@login_required
def list_records():
    search = (request.args.get("search") or "").strip() or None
    active_only = (request.args.get("active_only") or "").strip().lower() in {"1", "true", "yes"}
    try:
        rows = ChartAccountService().list_records(search=search, active_only=active_only)
        return jsonify({"ok": True, "rows": rows, "count": len(rows)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/records/<int:account_id>", methods=["GET"], strict_slashes=False)
@login_required
def get_record(account_id: int):
    try:
        return jsonify({"ok": True, "record": ChartAccountService().get_record(account_id)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/customers/<int:customer_id>", methods=["GET"], strict_slashes=False)
@login_required
def get_customer_record(customer_id: int):
    try:
        return jsonify({"ok": True, "record": ChartAccountService().get_customer_record(customer_id)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/customers/<int:customer_id>", methods=["POST"], strict_slashes=False)
@login_required
def assign_customer_group(customer_id: int):
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = ChartAccountService().assign_customer_group(customer_id, payload)
        return jsonify({"ok": True, "record": record, "message": "Group assigned successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/customers/<int:customer_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def clear_customer_group(customer_id: int):
    try:
        message = ChartAccountService().clear_customer_group(customer_id)
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/works/<int:work_id>", methods=["GET"], strict_slashes=False)
@login_required
def get_work_record(work_id: int):
    try:
        return jsonify({"ok": True, "record": ChartAccountService().get_work_record(work_id)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/works/<int:work_id>", methods=["POST"], strict_slashes=False)
@login_required
def assign_work_group(work_id: int):
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = ChartAccountService().assign_work_group(work_id, payload)
        return jsonify({"ok": True, "record": record, "message": "Group assigned successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/works/<int:work_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def clear_work_group(work_id: int):
    try:
        message = ChartAccountService().clear_work_group(work_id)
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records", methods=["POST"], strict_slashes=False)
@login_required
def create_record():
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = ChartAccountService().create_record(payload)
        return jsonify({"ok": True, "record": record, "message": "Account added successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:account_id>", methods=["POST"], strict_slashes=False)
@login_required
def update_record(account_id: int):
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = ChartAccountService().update_record(account_id, payload)
        return jsonify({"ok": True, "record": record, "message": "Account updated successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:account_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def delete_record(account_id: int):
    try:
        message = ChartAccountService().delete_record(account_id)
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
