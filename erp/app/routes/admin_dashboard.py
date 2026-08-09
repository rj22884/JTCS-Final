from __future__ import annotations

from datetime import date

from flask import Blueprint, Response, jsonify, render_template, request, session
from sqlalchemy import text

from app.decorators import admin_required, login_required
from app.extensions import db
from app.services.admin_dashboard_service import AdminDashboardService
from app.services.login_activity_service import LoginActivityService
from app.services.menu_service import MenuService

bp = Blueprint("admin_dashboard", __name__, url_prefix="/admin/dashboard")
# Product aliases: /admin/recent-logins and /admin/password-events
activity_bp = Blueprint("admin_activity_api", __name__, url_prefix="/admin")

MENU_PATH = "/admin/dashboard"
_MENU_ENSURED = False


def _ensure_admin_dashboard_menu() -> None:
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
                WHERE ParentMenuID = @ParentID AND MenuName = N'Admin Dashboard'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuURL = N'/admin/dashboard',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-speedometer2'),
                    DisplayOrder = 0,
                    Description = N'Administrator dashboard — bank closings and key totals',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE ParentMenuID = @ParentID AND MenuName = N'Admin Dashboard';
            END
            ELSE IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/dashboard'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ParentID,
                    MenuName = N'Admin Dashboard',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-speedometer2'),
                    DisplayOrder = 0,
                    Description = N'Administrator dashboard — bank closings and key totals',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE MenuURL = N'/admin/dashboard';
            END
            ELSE
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID,
                    N'Admin Dashboard',
                    N'bi-speedometer2',
                    N'/admin/dashboard',
                    0,
                    N'Administrator dashboard — bank closings and key totals',
                    1,
                    @AdminRoles
                );
            END;
            """
        )
    )
    db.session.commit()
    _MENU_ENSURED = True


def ensure_admin_dashboard_menu() -> None:
    _ensure_admin_dashboard_menu()


def _parse_date(raw: str | None) -> date | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _resolve_period() -> tuple[date, date, str]:
    today = date.today()
    preset = (request.args.get("period") or "today").strip().lower()
    custom_from = _parse_date(request.args.get("from"))
    custom_to = _parse_date(request.args.get("to"))

    if custom_from and custom_to:
        if custom_from > custom_to:
            custom_from, custom_to = custom_to, custom_from
        return custom_from, custom_to, "custom"

    if preset == "month":
        start = today.replace(day=1)
        return start, today, "month"
    if preset == "fy":
        fy_start_year = today.year if today.month >= 4 else today.year - 1
        return date(fy_start_year, 4, 1), today, "fy"
    if preset == "prev_fy":
        fy_start_year = today.year if today.month >= 4 else today.year - 1
        prev_start = date(fy_start_year - 1, 4, 1)
        prev_end = date(fy_start_year, 3, 31)
        return prev_start, prev_end, "prev_fy"

    return today, today, "today"


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def index():
    try:
        _ensure_admin_dashboard_menu()
    except Exception:
        db.session.rollback()

    date_from, date_to, period_preset = _resolve_period()
    data = AdminDashboardService().get_page_data(date_from=date_from, date_to=date_to)
    activity = LoginActivityService()
    try:
        recent_logins = activity.recent_logins(limit=10, period="today")
        password_events = activity.recent_password_events(limit=10, period="7d")
    except Exception:
        db.session.rollback()
        recent_logins = []
        password_events = []
    menu_service = MenuService()
    return render_template(
        "admin_dashboard/index.html",
        page_title="Admin Dashboard",
        breadcrumb=menu_service.get_breadcrumb(MENU_PATH, session.get("role")),
        date_from=date_from,
        date_to=date_to,
        input_date_from=date_from.isoformat(),
        input_date_to=date_to.isoformat(),
        period_preset=period_preset,
        metrics=data["metrics"],
        banks=data["banks"],
        banks_total=data["banks_total"],
        cards=data["cards"],
        recent_logins=recent_logins,
        password_events=password_events,
    )


@bp.route("/api/recent-logins", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def recent_logins():
    """Top recent staff login rows for Admin Dashboard."""
    try:
        limit = int(request.args.get("limit") or 10)
    except (TypeError, ValueError):
        limit = 10
    period = (request.args.get("period") or "all").strip().lower()
    search = (request.args.get("q") or "").strip()
    try:
        rows = LoginActivityService().recent_logins(limit=limit, period=period, search=search)
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to load login activity: {exc}"}), 500


@bp.route("/api/password-events", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def password_events():
    try:
        limit = int(request.args.get("limit") or 10)
    except (TypeError, ValueError):
        limit = 10
    period = (request.args.get("period") or "all").strip().lower()
    search = (request.args.get("q") or "").strip()
    try:
        rows = LoginActivityService().recent_password_events(
            limit=limit, period=period, search=search
        )
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to load password events: {exc}"}), 500


@bp.route("/api/recent-logins/export", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def recent_logins_export():
    period = (request.args.get("period") or "all").strip().lower()
    search = (request.args.get("q") or "").strip()
    try:
        csv_text = LoginActivityService().export_logins_csv(period=period, search=search)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to export: {exc}"}), 500
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=recent_login_activity.csv",
        },
    )


@activity_bp.route("/recent-logins", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def admin_recent_logins_alias():
    return recent_logins()


@activity_bp.route("/password-events", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def admin_password_events_alias():
    return password_events()


@bp.route("/api/bank-source/<int:account_id>", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def bank_source(account_id: int):
    as_of = _parse_date(request.args.get("as_of")) or date.today()
    try:
        payload = AdminDashboardService().get_bank_source_details(account_id, as_of=as_of)
        return jsonify({"ok": True, **payload})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to load bank source: {exc}"}), 500


@bp.route("/api/metric-details", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def metric_details():
    metric_key = (request.args.get("metric") or "").strip()
    date_from = _parse_date(request.args.get("from"))
    date_to = _parse_date(request.args.get("to"))
    if date_from is None or date_to is None:
        date_from, date_to, _ = _resolve_period()
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    try:
        payload = AdminDashboardService().get_metric_details(
            metric_key, date_from=date_from, date_to=date_to
        )
        return jsonify({"ok": True, **payload})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to load metric details: {exc}"}), 500
