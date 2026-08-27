from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, require_delete_reauth
from app.services.menu_service import MenuService
from app.services.work_master_service import WorkMasterService
from app.utils.master_delete_guard import MasterInUseError, json_in_use_response

bp = Blueprint("masters_work", __name__, url_prefix="/masters/income-expense")

MENU_PATH = "/masters/income-expense"
MENU_NAME = "Work/Category Master"


def _ensure_menu() -> None:
    """Ensure one Masters → Work/Category Master row (dedupe legacy duplicates)."""
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

            IF @MastersID IS NULL
                RETURN;

            DECLARE @KeepID INT;
            SELECT TOP 1 @KeepID = MenuID
            FROM dbo.MenuMaster
            WHERE ParentMenuID = @MastersID
              AND (
                    MenuName IN (
                        N'Work/Category Master',
                        N'Income/Expense',
                        N'Income Expense',
                        N'Work Master'
                    )
                    OR MenuURL = N'/masters/income-expense'
                  )
            ORDER BY
                CASE WHEN MenuName = N'Work/Category Master' THEN 0 ELSE 1 END,
                MenuID;

            IF @KeepID IS NOT NULL
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuName = N'Work/Category Master',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-sliders'),
                    MenuURL = N'/masters/income-expense',
                    DisplayOrder = 2,
                    Description = N'Work / category master (Income, Expense, Misc.)',
                    IsActive = 1,
                    RoleName = NULL
                WHERE MenuID = @KeepID;

                UPDATE dbo.MenuMaster
                SET IsActive = 0
                WHERE ParentMenuID = @MastersID
                  AND MenuID <> @KeepID
                  AND (
                        MenuName IN (
                            N'Work/Category Master',
                            N'Income/Expense',
                            N'Income Expense',
                            N'Work Master'
                        )
                        OR MenuURL = N'/masters/income-expense'
                      );
            END
            ELSE
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @MastersID,
                    N'Work/Category Master',
                    N'bi-sliders',
                    N'/masters/income-expense',
                    2,
                    N'Work / category master (Income, Expense, Misc.)',
                    1,
                    NULL
                );
            """
        )
    )
    db.session.commit()


@bp.route("", strict_slashes=False)
@bp.route("/", strict_slashes=False)
@login_required
def index():
    try:
        _ensure_menu()
    except Exception:
        from app.extensions import db

        db.session.rollback()
    menu_service = MenuService()
    service = WorkMasterService()
    rows = service.list_records(status="active")
    return render_template(
        "masters/income_expense.html",
        page_title=MENU_NAME,
        breadcrumb=menu_service.get_breadcrumb(MENU_PATH, session.get("role")),
        initial_rows=rows,
        chart_groups=service.list_chart_groups_for_form(),
    )


@bp.route("/api/records")
@login_required
def list_records():
    search = (request.args.get("search") or "").strip() or None
    ledger_kind = (request.args.get("ledger_kind") or "").strip() or None
    status = (request.args.get("status") or "").strip() or None
    rows = WorkMasterService().list_records(
        search=search,
        ledger_kind=ledger_kind or None,
        status=status,
    )
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


@bp.route("/api/records/<int:work_id>")
@login_required
def get_record(work_id: int):
    try:
        record = WorkMasterService().get_record(work_id)
        return jsonify({"ok": True, "record": record})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/records", methods=["POST"])
@login_required
def create_record():
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = WorkMasterService().create_record(payload)
        return jsonify({"ok": True, "record": record, "message": "Work type added successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/records/<int:work_id>", methods=["POST"])
@login_required
def update_record(work_id: int):
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = WorkMasterService().update_record(work_id, payload)
        return jsonify({"ok": True, "record": record, "message": "Work type updated successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/records/<int:work_id>/delete", methods=["POST"])
@login_required
@require_delete_reauth
def delete_record(work_id: int):
    try:
        message = WorkMasterService().delete_record(work_id)
        return jsonify({"ok": True, "message": message})
    except MasterInUseError as exc:
        return json_in_use_response(exc)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


# Legacy URLs used by older menus / bookmarks.
legacy_income_bp = Blueprint("masters_income_legacy", __name__, url_prefix="/masters/income")
legacy_expense_bp = Blueprint("masters_expense_legacy", __name__, url_prefix="/masters/expense")


@legacy_income_bp.route("", strict_slashes=False)
@legacy_income_bp.route("/", strict_slashes=False)
@login_required
def legacy_income_redirect():
    return redirect(url_for("masters_work.index"))


@legacy_expense_bp.route("", strict_slashes=False)
@legacy_expense_bp.route("/", strict_slashes=False)
@login_required
def legacy_expense_redirect():
    return redirect(url_for("masters_work.index"))


@bp.route("/exit")
@login_required
def exit_module():
    return redirect(url_for("dashboard.index"))
