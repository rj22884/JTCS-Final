"""System Health blueprint — Admin Role → System Administration → System Health."""

from __future__ import annotations

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import text

from app.decorators import admin_required, login_required
from app.extensions import db
from app.modules.system_health.repository import SystemHealthRepository
from app.modules.system_health.service import SystemHealthService
from app.services.menu_service import MenuService

bp = Blueprint("system_health", __name__, url_prefix="/admin/system-health")
MENU_PATH = "/admin/system-health"

_MENU_READY = False


def ensure_system_health_menus() -> None:
    """
    Ensure Admin Role → System Administration → System Health.
    Deactivates the older Utility → System Health menu to avoid duplicates.
    """
    global _MENU_READY
    if _MENU_READY:
        return

    SystemHealthRepository().ensure_schema()

    parent_id = db.session.execute(
        text(
            """
            SELECT TOP 1 MenuID
            FROM dbo.MenuMaster
            WHERE MenuName = N'Admin Role' AND ParentMenuID IS NULL
            ORDER BY MenuID
            """
        )
    ).scalar()
    if not parent_id:
        db.session.execute(
            text(
                """
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    NULL, N'Admin Role', N'bi-archive', NULL, 1,
                    N'Administrator tools', 1, N'Administrator,Admin'
                )
                """
            )
        )
        db.session.flush()
        parent_id = db.session.execute(
            text(
                """
                SELECT TOP 1 MenuID FROM dbo.MenuMaster
                WHERE MenuName = N'Admin Role' AND ParentMenuID IS NULL
                ORDER BY MenuID DESC
                """
            )
        ).scalar()

    # System Administration folder
    admin_sys_id = db.session.execute(
        text(
            """
            SELECT TOP 1 MenuID FROM dbo.MenuMaster
            WHERE ParentMenuID = :pid
              AND (MenuName = N'System Administration'
                   OR MenuURL = N'/admin/system-administration')
            ORDER BY MenuID
            """
        ),
        {"pid": parent_id},
    ).scalar()

    if admin_sys_id:
        db.session.execute(
            text(
                """
                UPDATE dbo.MenuMaster
                SET MenuName = N'System Administration',
                    MenuIcon = N'bi-hdd-rack',
                    MenuURL = N'/admin/system-administration',
                    DisplayOrder = 58,
                    Description = N'Enterprise monitoring and infrastructure',
                    IsActive = 1,
                    RoleName = N'Administrator,Admin'
                WHERE MenuID = :id
                """
            ),
            {"id": admin_sys_id},
        )
    else:
        db.session.execute(
            text(
                """
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    :pid, N'System Administration', N'bi-hdd-rack',
                    N'/admin/system-administration', 58,
                    N'Enterprise monitoring and infrastructure', 1, N'Administrator,Admin'
                )
                """
            ),
            {"pid": parent_id},
        )
        db.session.flush()
        admin_sys_id = db.session.execute(
            text(
                """
                SELECT TOP 1 MenuID FROM dbo.MenuMaster
                WHERE ParentMenuID = :pid AND MenuName = N'System Administration'
                ORDER BY MenuID DESC
                """
            ),
            {"pid": parent_id},
        ).scalar()

    # System Health leaf (prefer URL match across old Utility item)
    existing = db.session.execute(
        text(
            """
            SELECT TOP 1 MenuID FROM dbo.MenuMaster
            WHERE MenuURL IN (N'/admin/system-health', N'/admin/utility/health')
               OR (MenuName = N'System Health' AND ParentMenuID = :pid)
            ORDER BY CASE WHEN MenuURL = N'/admin/system-health' THEN 0 ELSE 1 END, MenuID
            """
        ),
        {"pid": admin_sys_id},
    ).scalar()

    if existing:
        db.session.execute(
            text(
                """
                UPDATE dbo.MenuMaster
                SET ParentMenuID = :pid,
                    MenuName = N'System Health',
                    MenuIcon = N'bi-heart-pulse-fill',
                    MenuURL = N'/admin/system-health',
                    DisplayOrder = 1,
                    Description = N'Mission Control — app, DB, server, APIs, security',
                    IsActive = 1,
                    RoleName = N'Administrator,Admin'
                WHERE MenuID = :id
                """
            ),
            {"pid": admin_sys_id, "id": existing},
        )
    else:
        db.session.execute(
            text(
                """
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    :pid, N'System Health', N'bi-heart-pulse-fill',
                    N'/admin/system-health', 1,
                    N'Mission Control — app, DB, server, APIs, security',
                    1, N'Administrator,Admin'
                )
                """
            ),
            {"pid": admin_sys_id},
        )

    # Hide any leftover Utility → System Health duplicates
    db.session.execute(
        text(
            """
            UPDATE dbo.MenuMaster
            SET IsActive = 0
            WHERE MenuURL = N'/admin/utility/health'
               OR (MenuName = N'System Health'
                   AND MenuURL <> N'/admin/system-health'
                   AND ParentMenuID <> :pid)
            """
        ),
        {"pid": admin_sys_id},
    )
    db.session.commit()
    _MENU_READY = True


@bp.route("", strict_slashes=False)
@bp.route("/", strict_slashes=False)
@login_required
@admin_required
def index():
    """Mission Control dashboard page."""
    return render_template(
        "system_health/index.html",
        page_title="System Health",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
    )


@bp.route("/api/dashboard", methods=["GET"])
@login_required
@admin_required
def api_dashboard():
    force = request.args.get("force") in {"1", "true", "yes"}
    try:
        return jsonify(SystemHealthService().dashboard(force_scan=force))
    except Exception as exc:
        current_app.logger.exception("System health dashboard failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/scan", methods=["POST"])
@login_required
@admin_required
def api_scan():
    try:
        return jsonify(SystemHealthService().scan(persist=True))
    except Exception as exc:
        current_app.logger.exception("System health scan failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/charts", methods=["GET"])
@login_required
@admin_required
def api_charts():
    try:
        return jsonify(SystemHealthService().charts())
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/alerts", methods=["GET"])
@login_required
@admin_required
def api_alerts():
    try:
        return jsonify({"ok": True, "alerts": SystemHealthService()._alert_payload()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/logs", methods=["GET"])
@login_required
@admin_required
def api_logs():
    period = (request.args.get("period") or "today").strip()
    level = (request.args.get("level") or "").strip() or None
    try:
        return jsonify(
            {
                "ok": True,
                **SystemHealthService().collect_logs(period=period, level=level, limit=80),
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/export", methods=["GET"])
@login_required
@admin_required
def api_export():
    fmt = (request.args.get("format") or "csv").strip().lower()
    try:
        filename, mimetype, body = SystemHealthService().export_report(fmt)
        return Response(
            body,
            mimetype=mimetype,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/clear-cache", methods=["POST"])
@login_required
@admin_required
def api_clear_cache():
    try:
        return jsonify(SystemHealthService().clear_cache())
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/backup", methods=["POST"])
@login_required
@admin_required
def api_backup():
    try:
        user = session.get("user_name") or "Admin"
        return jsonify(SystemHealthService().run_backup(created_by=str(user)))
    except Exception as exc:
        current_app.logger.exception("Manual backup from System Health failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/refresh-config", methods=["POST"])
@login_required
@admin_required
def api_refresh_config():
    """Re-ensure schema/menus and return a fresh scan."""
    try:
        ensure_system_health_menus()
        from app.modules.settings.routes import ensure_integration_settings_bootstrap

        ensure_integration_settings_bootstrap()
        data = SystemHealthService().scan(persist=True)
        data["message"] = "Configuration refreshed and health scan completed."
        return jsonify(data)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
