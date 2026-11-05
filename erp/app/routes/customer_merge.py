"""Admin Role → Merge Customer. Every signed-in user can merge duplicates."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import text

from app.decorators import login_required
from app.extensions import db
from app.repositories.menu_repository import MenuRepository
from app.services.customer_merge_service import CustomerMergeService

bp = Blueprint("customer_merge", __name__, url_prefix="/admin/merge-customer")

_MENU_ENSURED = False
MENU_PATH = "/admin/merge-customer"


def ensure_merge_customer_menu() -> None:
    """Admin Role → Merge Customer, allowed for every signed-in user."""
    global _MENU_ENSURED
    if _MENU_ENSURED:
        return
    try:
        MenuRepository().ensure_style_columns()
        db.session.execute(
            text(
                """
                DECLARE @ParentID INT;

                SELECT TOP 1 @ParentID = MenuID
                FROM dbo.MenuMaster
                WHERE MenuName = N'Admin Role' AND ParentMenuID IS NULL
                ORDER BY MenuID;

                IF @ParentID IS NULL
                    RETURN;

                IF EXISTS (
                    SELECT 1 FROM dbo.MenuMaster
                    WHERE MenuURL = N'/admin/merge-customer' OR MenuName = N'Merge Customer'
                )
                BEGIN
                    UPDATE dbo.MenuMaster
                    SET ParentMenuID = @ParentID,
                        MenuName = N'Merge Customer',
                        MenuIcon = N'bi-people',
                        MenuURL = N'/admin/merge-customer',
                        DisplayOrder = 5,
                        Description = N'Merge duplicate customers by name, phone, or both',
                        IsActive = 1,
                        RoleName = NULL,
                        AllowAllUsers = 1
                    WHERE MenuURL = N'/admin/merge-customer' OR MenuName = N'Merge Customer';
                END
                ELSE
                BEGIN
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName, AllowAllUsers
                    )
                    VALUES (
                        @ParentID, N'Merge Customer', N'bi-people', N'/admin/merge-customer', 5,
                        N'Merge duplicate customers by name, phone, or both',
                        1, NULL, 1
                    );
                END;
                """
            )
        )
        db.session.commit()
        _MENU_ENSURED = True
    except Exception:
        db.session.rollback()


@bp.route("", methods=["GET"], strict_slashes=False)
@login_required
def merge_customer_page():
    ensure_merge_customer_menu()
    return render_template(
        "admin/merge_customer.html",
        page_title="Merge Customer",
    )


@bp.route("/groups", methods=["GET"], strict_slashes=False)
@login_required
def merge_customer_groups():
    mode = (request.args.get("mode") or "name_phone").strip().lower()
    try:
        groups = CustomerMergeService().list_groups(mode)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "mode": mode, "groups": groups, "count": len(groups)})


@bp.route("/merge", methods=["POST"], strict_slashes=False)
@login_required
def merge_customers():
    payload = request.get_json(silent=True) or {}
    try:
        result = CustomerMergeService().merge(
            int(payload.get("main_customer_id") or 0),
            payload.get("merge_customer_ids") or [],
            (payload.get("mode") or "").strip().lower(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc) or "Unable to merge these customers."}), 500
    name = result["main_customer_name"] or "the main customer"
    return jsonify(
        {
            "ok": True,
            "message": f"{result['merged_count']} customer merged into {name}.",
            **result,
        }
    )
