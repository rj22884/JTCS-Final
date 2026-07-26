from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
    session,
)
from sqlalchemy import text

from app.decorators import admin_required, login_required, require_delete_reauth
from app.extensions import db
from app.services.backup_service import BackupService
from app.services.menu_service import MenuService

bp = Blueprint("backup", __name__, url_prefix="/admin/backup")

_MENU_ENSURED = False


def _ensure_backup_menus() -> None:
    """Wire Admin Role → Backup Full / Data Backup menu URLs (idempotent)."""
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
                SET MenuURL = NULL,
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-archive'),
                    Description = COALESCE(
                        Description,
                        N'Administrator tools — backups and system maintenance'
                    ),
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE MenuID = @ParentID;
            END;

            /* Backup Full */
            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE ParentMenuID = @ParentID
                  AND MenuName = N'Backup Full'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuURL = N'/admin/backup/full',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-database-fill'),
                    DisplayOrder = 1,
                    Description = N'Full application + database backup (ZIP)',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE ParentMenuID = @ParentID
                  AND MenuName = N'Backup Full';
            END
            ELSE IF NOT EXISTS (
                SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/backup/full'
            )
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID,
                    N'Backup Full',
                    N'bi-database-fill',
                    N'/admin/backup/full',
                    1,
                    N'Full application + database backup (ZIP)',
                    1,
                    @AdminRoles
                );
            END
            ELSE
            BEGIN
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ParentID,
                    MenuName = N'Backup Full',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-database-fill'),
                    DisplayOrder = 1,
                    Description = N'Full application + database backup (ZIP)',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE MenuURL = N'/admin/backup/full';
            END;

            /* Data Backup */
            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE ParentMenuID = @ParentID
                  AND MenuName = N'Data Backup'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuURL = N'/admin/backup/data',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-clipboard-data'),
                    DisplayOrder = 2,
                    Description = N'SQL Server database backup (.bak)',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE ParentMenuID = @ParentID
                  AND MenuName = N'Data Backup';
            END
            ELSE IF NOT EXISTS (
                SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/backup/data'
            )
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID,
                    N'Data Backup',
                    N'bi-clipboard-data',
                    N'/admin/backup/data',
                    2,
                    N'SQL Server database backup (.bak)',
                    1,
                    @AdminRoles
                );
            END
            ELSE
            BEGIN
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ParentID,
                    MenuName = N'Data Backup',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-clipboard-data'),
                    DisplayOrder = 2,
                    Description = N'SQL Server database backup (.bak)',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE MenuURL = N'/admin/backup/data';
            END;

            UPDATE dbo.MenuMaster
            SET RoleName = @AdminRoles
            WHERE ParentMenuID = @ParentID;
            """
        )
    )
    db.session.commit()
    _MENU_ENSURED = True


def ensure_backup_menus() -> None:
    _ensure_backup_menus()


def _actor() -> str:
    return (session.get("user_name") or session.get("full_name") or "System").strip() or "System"


@bp.route("/data", strict_slashes=False)
@login_required
@admin_required
def data_backup_page():
    service = BackupService()
    menu_service = MenuService()
    return render_template(
        "backup/data.html",
        page_title="Data Backup",
        breadcrumb=menu_service.get_breadcrumb("/admin/backup/data", session.get("role")),
        connection=service.connection_info(),
        backups=service.list_database_backups(),
    )


@bp.route("/full", strict_slashes=False)
@login_required
@admin_required
def full_backup_page():
    service = BackupService()
    menu_service = MenuService()
    return render_template(
        "backup/full.html",
        page_title="Backup Full",
        breadcrumb=menu_service.get_breadcrumb("/admin/backup/full", session.get("role")),
        connection=service.connection_info(),
        backups=service.list_full_backups(),
    )


@bp.route("/api/database/list")
@login_required
@admin_required
def list_database_backups():
    rows = BackupService().list_database_backups()
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


@bp.route("/api/full/list")
@login_required
@admin_required
def list_full_backups():
    rows = BackupService().list_full_backups()
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


@bp.route("/api/database/create", methods=["POST"])
@login_required
@admin_required
def create_database_backup():
    try:
        info = BackupService().create_database_backup(created_by=_actor())
        return jsonify({"ok": True, "backup": info, "message": info["message"]})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Database backup failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/full/create", methods=["POST"])
@login_required
@admin_required
def create_full_backup():
    try:
        info = BackupService().create_full_backup(created_by=_actor())
        return jsonify({"ok": True, "backup": info, "message": info["message"]})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Full backup failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/<kind>/download/<path:file_name>")
@login_required
@admin_required
def download_backup(kind: str, file_name: str):
    try:
        path = BackupService().resolve_download(kind, file_name)
        return send_file(
            path,
            as_attachment=True,
            download_name=path.name,
            mimetype="application/octet-stream",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/<kind>/delete", methods=["POST"])
@login_required
@admin_required
@require_delete_reauth
def delete_backup(kind: str):
    payload = request.get_json(silent=True) or {}
    file_name = (payload.get("file_name") or request.form.get("file_name") or "").strip()
    try:
        message = BackupService().delete_backup(kind, file_name)
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
