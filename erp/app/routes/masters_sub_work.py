from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, require_delete_reauth
from app.services.menu_service import MenuService
from app.services.sub_work_master_service import SubWorkMasterService
from app.utils.master_delete_guard import MasterInUseError, json_in_use_response

bp = Blueprint("masters_sub_work", __name__, url_prefix="/masters/sub-work")

MENU_PATH = "/masters/sub-work"


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
                    WHERE ParentMenuID = @MastersID AND MenuName = N'Sub Work Master'
                )
                    UPDATE dbo.MenuMaster
                    SET MenuURL = N'/masters/sub-work',
                        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-diagram-3'),
                        DisplayOrder = 3,
                        Description = N'Sub works grouped by WorkMaster LedgerKind (Income / Expense / Misc.)',
                        IsActive = 1
                    WHERE ParentMenuID = @MastersID AND MenuName = N'Sub Work Master';
                ELSE
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @MastersID,
                        N'Sub Work Master',
                        N'bi-diagram-3',
                        N'/masters/sub-work',
                        3,
                        N'Sub works grouped by WorkMaster LedgerKind (Income / Expense / Misc.)',
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
    service = SubWorkMasterService()
    rows = service.list_records()
    return render_template(
        "masters/sub_work.html",
        page_title="Sub Work Master",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        initial_rows=rows,
        work_groups=service.list_work_groups(),
        ledger_kinds=service.list_ledger_kinds(),
    )


@bp.route("/exit")
@login_required
def exit_module():
    return redirect(url_for("dashboard.index"))


@bp.route("/api/works", methods=["GET"], strict_slashes=False)
@login_required
def list_works():
    ledger_kind = (request.args.get("ledger_kind") or "").strip() or None
    try:
        rows = SubWorkMasterService().list_works_for_ledger(ledger_kind)
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/records", methods=["GET"], strict_slashes=False)
@login_required
def list_records():
    search = (request.args.get("search") or "").strip() or None
    ledger_kind = (request.args.get("ledger_kind") or "").strip() or None
    try:
        rows = SubWorkMasterService().list_records(search=search, ledger_kind=ledger_kind)
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/records/<int:work_type_id>", methods=["GET"], strict_slashes=False)
@login_required
def get_record(work_type_id: int):
    try:
        return jsonify({"ok": True, "record": SubWorkMasterService().get_record(work_type_id)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/records", methods=["POST"], strict_slashes=False)
@login_required
def create_record():
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = SubWorkMasterService().create_record(payload)
        return jsonify({"ok": True, "record": record, "message": "Sub work saved."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/records/<int:work_type_id>", methods=["POST"], strict_slashes=False)
@login_required
def update_record(work_type_id: int):
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = SubWorkMasterService().update_record(work_type_id, payload)
        return jsonify({"ok": True, "record": record, "message": "Sub work updated."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/records/<int:work_type_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def delete_record(work_type_id: int):
    try:
        message = SubWorkMasterService().delete_record(work_type_id)
        return jsonify({"ok": True, "message": message})
    except MasterInUseError as exc:
        return json_in_use_response(exc)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
