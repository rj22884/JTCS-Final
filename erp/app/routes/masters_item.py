from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, require_delete_reauth
from app.services.chart_group_service import ChartGroupService
from app.services.hsn_sac_search_service import search_hsn_sac
from app.services.item_master_service import ItemMasterService
from app.services.menu_service import MenuService
from app.utils.db_session import map_db_exception
from app.utils.master_delete_guard import MasterInUseError, json_in_use_response

bp = Blueprint("masters_item", __name__, url_prefix="/masters/item")

MENU_PATH = "/masters/item"


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
                    WHERE ParentMenuID = @MastersID AND MenuName = N'Item Master'
                )
                    UPDATE dbo.MenuMaster
                    SET MenuURL = N'/masters/item',
                        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-box-seam'),
                        DisplayOrder = 19,
                        Description = N'GST item master (HSN/SAC, rates)',
                        IsActive = 1
                    WHERE ParentMenuID = @MastersID AND MenuName = N'Item Master';
                ELSE
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @MastersID, N'Item Master', N'bi-box-seam', N'/masters/item',
                        19, N'GST item master (HSN/SAC, rates)', 1, NULL
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
    rows = ItemMasterService().list_records()
    try:
        chart_groups = ChartGroupService().list_active_for_dropdown()
    except Exception:
        from app.extensions import db

        db.session.rollback()
        chart_groups = []
    return render_template(
        "masters/item.html",
        page_title="Item Master",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        initial_rows=rows,
        chart_groups=chart_groups,
    )


@bp.route("/api/records", methods=["GET"], strict_slashes=False)
@login_required
def list_records():
    search = (request.args.get("search") or "").strip() or None
    active_only = (request.args.get("active_only") or "").strip().lower() in {"1", "true", "yes"}
    try:
        rows = ItemMasterService().list_records(search=search, active_only=active_only)
        return jsonify({"ok": True, "rows": rows, "count": len(rows)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/active", methods=["GET"], strict_slashes=False)
@login_required
def list_active():
    try:
        rows = ItemMasterService().list_active_for_dropdown()
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/hsn-search", methods=["GET"], strict_slashes=False)
@login_required
def hsn_search():
    query = (request.args.get("q") or request.args.get("query") or "").strip()
    hsn_type = (request.args.get("type") or request.args.get("hsn_sac_type") or "").strip()
    try:
        limit = int(request.args.get("limit") or 25)
    except (TypeError, ValueError):
        limit = 25
    try:
        rows = search_hsn_sac(query, hsn_sac_type=hsn_type or None, limit=limit)
        return jsonify({"ok": True, "rows": rows, "count": len(rows)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/records/<int:item_id>", methods=["GET"], strict_slashes=False)
@login_required
def get_record(item_id: int):
    try:
        return jsonify({"ok": True, "record": ItemMasterService().get_record(item_id)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/records", methods=["POST"], strict_slashes=False)
@login_required
def create_record():
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = ItemMasterService().create_record(payload)
        return jsonify({"ok": True, "record": record, "message": "Item added successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:item_id>", methods=["POST"], strict_slashes=False)
@login_required
def update_record(item_id: int):
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = ItemMasterService().update_record(item_id, payload)
        return jsonify({"ok": True, "record": record, "message": "Item updated successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/records/<int:item_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def delete_record(item_id: int):
    try:
        message = ItemMasterService().delete_record(item_id)
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
