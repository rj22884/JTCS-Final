from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request, session
from sqlalchemy import text

from app.decorators import admin_required, login_required
from app.extensions import db
from app.services.customer_activity_service import CustomerActivityService
from app.services.menu_service import MenuService

bp = Blueprint("customer_activity", __name__, url_prefix="/admin/customer-activity")

MENU_PATH = "/admin/customer-activity"
_MENU_ENSURED = False


def _ensure_customer_activity_menu() -> None:
    global _MENU_ENSURED
    if _MENU_ENSURED:
        return
    db.session.execute(
        text(
            """
            DECLARE @ParentID INT;
            DECLARE @AdminRoles NVARCHAR(50) = N'Administrator,Admin';

            SELECT TOP 1 @ParentID = MenuID
            FROM dbo.MenuMaster
            WHERE MenuName = N'Admin Role'
              AND ParentMenuID IS NULL
            ORDER BY MenuID;

            IF @ParentID IS NULL
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    NULL,
                    N'Admin Role',
                    N'bi-archive',
                    NULL,
                    1,
                    N'Administrator tools — backups and system maintenance',
                    1,
                    @AdminRoles
                );
                SET @ParentID = SCOPE_IDENTITY();
            END
            ELSE
            BEGIN
                UPDATE dbo.MenuMaster
                SET RoleName = @AdminRoles,
                    IsActive = 1
                WHERE MenuID = @ParentID;
            END;

            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE ParentMenuID = @ParentID AND MenuName = N'Client/Customer Activity'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuURL = N'/admin/customer-activity',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-person-check'),
                    DisplayOrder = 12,
                    Description = N'Customer Portal login and activation activity',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE ParentMenuID = @ParentID AND MenuName = N'Client/Customer Activity';
            END
            ELSE IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/customer-activity'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ParentID,
                    MenuName = N'Client/Customer Activity',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-person-check'),
                    DisplayOrder = 12,
                    Description = N'Customer Portal login and activation activity',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE MenuURL = N'/admin/customer-activity';
            END
            ELSE
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID,
                    N'Client/Customer Activity',
                    N'bi-person-check',
                    N'/admin/customer-activity',
                    12,
                    N'Customer Portal login and activation activity',
                    1,
                    @AdminRoles
                );
            END;
            """
        )
    )
    db.session.commit()
    _MENU_ENSURED = True


def ensure_customer_activity_menu() -> None:
    _ensure_customer_activity_menu()


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def index():
    try:
        _ensure_customer_activity_menu()
    except Exception:
        db.session.rollback()

    service = CustomerActivityService()
    try:
        summary = service.summary()
    except Exception:
        db.session.rollback()
        summary = {"logged_count": 0, "password_set_count": 0, "total_customers": 0}

    menu_service = MenuService()
    return render_template(
        "customer_activity/index.html",
        page_title="Client/Customer Activity",
        breadcrumb=menu_service.get_breadcrumb(MENU_PATH, session.get("role")),
        summary=summary,
    )


@bp.route("/api/summary", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def api_summary():
    try:
        return jsonify({"ok": True, **CustomerActivityService().summary()})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/logged-customers", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def api_logged_customers():
    search = (request.args.get("q") or "").strip()
    filter_raw = (request.args.get("filter") or "logged").strip().lower()
    only_logged: bool | None
    if filter_raw in {"all", ""}:
        only_logged = None
    elif filter_raw in {"not_logged", "pending"}:
        only_logged = False
    else:
        only_logged = True
    try:
        limit = int(request.args.get("limit") or 200)
    except (TypeError, ValueError):
        limit = 200
    try:
        rows = CustomerActivityService().list_logged_customers(
            search=search or None,
            only_logged=only_logged,
            limit=limit,
        )
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/login-attempts", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def api_login_attempts():
    period = (request.args.get("period") or "7d").strip().lower()
    search = (request.args.get("q") or "").strip()
    try:
        limit = int(request.args.get("limit") or 100)
    except (TypeError, ValueError):
        limit = 100
    try:
        rows = CustomerActivityService().list_login_attempts(
            period=period,
            search=search or None,
            limit=limit,
        )
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 500
