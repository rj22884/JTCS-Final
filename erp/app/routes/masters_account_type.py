from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, require_delete_reauth
from app.services.account_type_master_service import AccountTypeMasterService
from app.services.menu_service import MenuService
from app.utils.db_session import map_db_exception
from app.utils.master_delete_guard import MasterInUseError, json_in_use_response

bp = Blueprint("masters_account_type", __name__, url_prefix="/masters/account-type")

MENU_PATH = "/masters/account-type"


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
                    WHERE ParentMenuID = @MastersID AND MenuName = N'Account Type Master'
                )
                    UPDATE dbo.MenuMaster
                    SET MenuURL = N'/masters/account-type',
                        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-tags'),
                        DisplayOrder = 18,
                        Description = N'Bank account types (SB, CC/OD, OTH, RD, …)',
                        IsActive = 1
                    WHERE ParentMenuID = @MastersID AND MenuName = N'Account Type Master';
                ELSE
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @MastersID,
                        N'Account Type Master',
                        N'bi-tags',
                        N'/masters/account-type',
                        18,
                        N'Bank account types (SB, CC/OD, OTH, RD, …)',
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
    service = AccountTypeMasterService()
    rows = service.list_records()
    return render_template(
        "masters/account_type.html",
        page_title="Account Type Master",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        initial_rows=rows,
    )


@bp.route("/api/records", methods=["GET"], strict_slashes=False)
@login_required
def list_records():
    search = (request.args.get("search") or "").strip() or None
    active_only = (request.args.get("active_only") or "").strip().lower() in {"1", "true", "yes"}
    try:
        rows = AccountTypeMasterService().list_records(search=search, active_only=active_only)
        return jsonify({"ok": True, "rows": rows, "count": len(rows)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/active", methods=["GET"], strict_slashes=False)
@login_required
def list_active():
    try:
        rows = AccountTypeMasterService().list_active_for_dropdown()
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/records/<int:account_type_id>", methods=["GET"], strict_slashes=False)
@login_required
def get_record(account_type_id: int):
    try:
        return jsonify({"ok": True, "record": AccountTypeMasterService().get_record(account_type_id)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/records", methods=["POST"], strict_slashes=False)
@login_required
def create_record():
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = AccountTypeMasterService().create_record(payload)
        return jsonify({"ok": True, "record": record, "message": "Account type added successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:account_type_id>", methods=["POST"], strict_slashes=False)
@login_required
def update_record(account_type_id: int):
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = AccountTypeMasterService().update_record(account_type_id, payload)
        return jsonify({"ok": True, "record": record, "message": "Account type updated successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:account_type_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def delete_record(account_type_id: int):
    try:
        message = AccountTypeMasterService().delete_record(account_type_id)
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
