from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, require_delete_reauth
from app.services.chart_group_service import ChartGroupService
from app.services.menu_service import MenuService
from app.utils.db_session import map_db_exception

bp = Blueprint("masters_chart_group", __name__, url_prefix="/masters/chart-group")

MENU_PATH = "/masters/chart-group"


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
                    WHERE ParentMenuID = @MastersID AND MenuName = N'Chart of Group Master'
                )
                    UPDATE dbo.MenuMaster
                    SET MenuURL = N'/masters/chart-group',
                        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-diagram-3'),
                        DisplayOrder = 30,
                        Description = N'Tally-style chart of groups (Assets / Liabilities)',
                        IsActive = 1
                    WHERE ParentMenuID = @MastersID AND MenuName = N'Chart of Group Master';
                ELSE
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @MastersID,
                        N'Chart of Group Master',
                        N'bi-diagram-3',
                        N'/masters/chart-group',
                        30,
                        N'Tally-style chart of groups (Assets / Liabilities)',
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
    service = ChartGroupService()
    rows = service.list_records()
    return render_template(
        "masters/chart_group.html",
        page_title="Chart of Group Master",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        initial_rows=rows,
    )


@bp.route("/api/records", methods=["GET"], strict_slashes=False)
@login_required
def list_records():
    search = (request.args.get("search") or "").strip() or None
    active_only = (request.args.get("active_only") or "").strip().lower() in {"1", "true", "yes"}
    try:
        rows = ChartGroupService().list_records(search=search, active_only=active_only)
        return jsonify({"ok": True, "rows": rows, "count": len(rows)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/active", methods=["GET"], strict_slashes=False)
@login_required
def list_active():
    try:
        rows = ChartGroupService().list_active_for_dropdown()
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/records/<int:group_id>", methods=["GET"], strict_slashes=False)
@login_required
def get_record(group_id: int):
    try:
        return jsonify({"ok": True, "record": ChartGroupService().get_record(group_id)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/records", methods=["POST"], strict_slashes=False)
@login_required
def create_record():
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = ChartGroupService().create_record(payload)
        return jsonify({"ok": True, "record": record, "message": "Group added successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:group_id>", methods=["POST"], strict_slashes=False)
@login_required
def update_record(group_id: int):
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = ChartGroupService().update_record(group_id, payload)
        return jsonify({"ok": True, "record": record, "message": "Group updated successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:group_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def delete_record(group_id: int):
    try:
        message = ChartGroupService().delete_record(group_id)
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/exit")
@login_required
def exit_module():
    return redirect(url_for("dashboard.index"))
