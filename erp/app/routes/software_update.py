"""Admin Software Updates / About Software / version APIs."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request, session
from sqlalchemy import text

from app.decorators import admin_required, login_required
from app.extensions import db
from app.services.menu_service import MenuService
from app.services.version_service import VersionService

bp = Blueprint("software_update", __name__, url_prefix="/admin")

_MENU_ENSURED = False


def _ensure_menus() -> None:
    global _MENU_ENSURED
    if _MENU_ENSURED:
        return
    try:
        db.session.execute(
            text(
                """
                DECLARE @ParentID INT;
                DECLARE @AdminRoles NVARCHAR(50) = N'Administrator,Admin';

                SELECT TOP 1 @ParentID = MenuID
                FROM dbo.MenuMaster
                WHERE MenuName = N'Admin Role' AND ParentMenuID IS NULL
                ORDER BY MenuID;

                IF @ParentID IS NULL
                BEGIN
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        NULL, N'Admin Role', N'bi-archive', NULL, 1,
                        N'Administrator tools', 1, @AdminRoles
                    );
                    SET @ParentID = SCOPE_IDENTITY();
                END;

                IF NOT EXISTS (
                    SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/software-updates'
                )
                BEGIN
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @ParentID, N'Software Updates', N'bi-arrow-repeat',
                        N'/admin/software-updates', 8,
                        N'Version history, change log, health and rollback',
                        1, @AdminRoles
                    );
                END;

                IF NOT EXISTS (
                    SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/about-software'
                )
                BEGIN
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @ParentID, N'About Software', N'bi-info-circle',
                        N'/admin/about-software', 9,
                        N'Application version and release information',
                        1, @AdminRoles
                    );
                END;
                """
            )
        )
        db.session.commit()
        _MENU_ENSURED = True
    except Exception:
        db.session.rollback()


@bp.before_request
def _boot_menus():
    _ensure_menus()


@bp.route("/software-updates")
@login_required
@admin_required
def software_updates():
    svc = VersionService()
    current = svc.get_current()
    history = svc.list_history(limit=100)
    previous = history[1] if len(history) > 1 else None
    menu_service = MenuService()
    return render_template(
        "admin/software_update.html",
        page_title="Software Updates",
        breadcrumb=menu_service.get_breadcrumb("/admin/software-updates", session.get("role")),
        current=current,
        previous=previous,
        history=history,
    )


@bp.route("/about-software")
@login_required
def about_software():
    svc = VersionService()
    current = svc.get_current()
    history = svc.list_history(limit=20)
    menu_service = MenuService()
    return render_template(
        "admin/about_software.html",
        page_title="About Software",
        breadcrumb=menu_service.get_breadcrumb("/admin/about-software", session.get("role")),
        current=current,
        history=history,
    )


@bp.route("/api/version/current")
@login_required
def api_current_version():
    svc = VersionService()
    current = svc.get_current()
    fallback = current_app.config.get("APP_VERSION", "1.0.0")
    if not current:
        return jsonify({"ok": True, "version": fallback, "source": "env"})
    return jsonify({"ok": True, "version": svc.to_dict(current), "source": "database"})


@bp.route("/api/version/history")
@login_required
@admin_required
def api_version_history():
    limit = request.args.get("limit", 50, type=int) or 50
    return jsonify({"ok": True, "rows": VersionService().history_as_dicts(limit=limit)})


@bp.route("/api/version/health")
@login_required
@admin_required
def api_version_health():
    """Best-effort local health summary for the Software Updates page."""
    db_ok = False
    try:
        db.session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"ok": False, "database": False, "error": str(exc)}), 500

    return jsonify(
        {
            "ok": True,
            "database": db_ok,
            "app_name": current_app.config.get("APP_NAME", "JTCS ERP"),
            "app_version": VersionService().get_display_version(
                current_app.config.get("APP_VERSION", "1.0.0")
            ),
        }
    )


@bp.route("/api/version/rollback", methods=["POST"])
@login_required
@admin_required
def api_request_rollback():
    """
    Records a rollback request. Actual file/DB restore must run on the VPS
    via deployment/rollback.sh (SSH). This endpoint does not execute remote SSH
    with embedded credentials.
    """
    payload = request.get_json(silent=True) or {}
    version = (payload.get("version") or "").strip()
    if not version:
        return jsonify({"ok": False, "error": "version is required"}), 400

    row = VersionService().get_by_version_string(version)
    backup = row.BackupPath if row else ""
    hint = (
        f"On the VPS run: bash deployment/rollback.sh --version {version}"
        + (f"   # backup: {backup}" if backup else "")
    )
    return jsonify(
        {
            "ok": True,
            "message": "Rollback must be executed on the VPS (no passwords in app).",
            "command": hint,
            "backup_path": backup or None,
        }
    )
