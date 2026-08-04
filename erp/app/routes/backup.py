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
from werkzeug.exceptions import RequestEntityTooLarge

from app.decorators import admin_required, login_required, require_delete_reauth
from app.extensions import csrf, db
from app.services.backup_service import BackupService
from app.services.menu_service import MenuService

bp = Blueprint("backup", __name__, url_prefix="/admin/backup")

_MENU_ENSURED = False
# Restore uploads (.bak/.zip) are often 30–500MB; other modules keep app default (10MB).
_RESTORE_UPLOAD_MAX_BYTES = 2 * 1024 * 1024 * 1024
_RESTORE_UPLOAD_SUFFIX = "/admin/backup/api/restore/upload"


def _is_restore_upload_path(path: str, method: str = "POST") -> bool:
    return (method or "").upper() == "POST" and (path or "").rstrip("/").endswith(
        _RESTORE_UPLOAD_SUFFIX
    )


def _is_restore_upload_request() -> bool:
    return _is_restore_upload_path(request.path or "", request.method or "")


@bp.record_once
def _install_restore_upload_large_body(state) -> None:
    """Bump MAX_CONTENT_LENGTH at WSGI layer BEFORE CSRF/body parse (restore upload only)."""
    app = state.app
    original_wsgi = app.wsgi_app

    def wsgi_app(environ, start_response):
        path = environ.get("PATH_INFO") or ""
        method = environ.get("REQUEST_METHOD") or ""
        if not _is_restore_upload_path(path, method):
            return original_wsgi(environ, start_response)

        prev = app.config.get("MAX_CONTENT_LENGTH")
        app.config["MAX_CONTENT_LENGTH"] = max(int(prev or 0), _RESTORE_UPLOAD_MAX_BYTES)
        try:
            return original_wsgi(environ, start_response)
        finally:
            app.config["MAX_CONTENT_LENGTH"] = prev

    app.wsgi_app = wsgi_app

    # App-level 413 JSON for this path (blueprint handler misses pre-view failures).
    @app.errorhandler(RequestEntityTooLarge)
    def _restore_or_default_too_large(exc):
        if _is_restore_upload_request():
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": (
                            "Backup file is too large for upload (max 2 GB). "
                            "Copy the VPS .bak into the Local data folder shown on this page, "
                            "refresh, then click Restore."
                        ),
                    }
                ),
                413,
            )
        return exc.get_response()


@bp.errorhandler(RequestEntityTooLarge)
def _restore_upload_too_large(_exc):
    return (
        jsonify(
            {
                "ok": False,
                "error": (
                    "Backup file is too large for upload (max 2 GB). "
                    "Copy the VPS .bak into the Local data folder shown on this page, "
                    "refresh, then click Restore."
                ),
            }
        ),
        413,
    )


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

            /* Restore Backup */
            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE ParentMenuID = @ParentID
                  AND MenuName = N'Restore Backup'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuURL = N'/admin/backup/restore',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-arrow-counterclockwise'),
                    DisplayOrder = 3,
                    Description = N'Upload VPS backup and restore on this local PC',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE ParentMenuID = @ParentID
                  AND MenuName = N'Restore Backup';
            END
            ELSE IF NOT EXISTS (
                SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/backup/restore'
            )
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID,
                    N'Restore Backup',
                    N'bi-arrow-counterclockwise',
                    N'/admin/backup/restore',
                    3,
                    N'Upload VPS backup and restore on this local PC',
                    1,
                    @AdminRoles
                );
            END
            ELSE
            BEGIN
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ParentID,
                    MenuName = N'Restore Backup',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-arrow-counterclockwise'),
                    DisplayOrder = 3,
                    Description = N'Upload VPS backup and restore on this local PC',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE MenuURL = N'/admin/backup/restore';
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


@bp.route("/restore", strict_slashes=False)
@login_required
@admin_required
def restore_backup_page():
    service = BackupService()
    menu_service = MenuService()
    return render_template(
        "backup/restore.html",
        page_title="Restore Backup",
        breadcrumb=menu_service.get_breadcrumb("/admin/backup/restore", session.get("role")),
        connection=service.connection_info(),
        database_backups=service.list_database_backups(),
        full_backups=service.list_full_backups(),
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


@bp.route("/api/restore/list")
@login_required
@admin_required
def list_restore_backups():
    service = BackupService()
    database_rows = service.list_database_backups()
    full_rows = service.list_full_backups()
    return jsonify(
        {
            "ok": True,
            "database": database_rows,
            "full": full_rows,
            "count": len(database_rows) + len(full_rows),
        }
    )


@bp.route("/api/restore/upload", methods=["POST"])
@csrf.exempt  # large multipart; auth still via login_required + admin_required
@login_required
@admin_required
def upload_restore_backup():
    # Ensure limit is raised even if WSGI wrapper order differs under reloader.
    current_app.config["MAX_CONTENT_LENGTH"] = max(
        int(current_app.config.get("MAX_CONTENT_LENGTH") or 0),
        _RESTORE_UPLOAD_MAX_BYTES,
    )
    try:
        upload = request.files.get("file")
    except RequestEntityTooLarge:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": (
                        "Backup file is too large for upload (max 2 GB). "
                        "Copy it into the Local data folder and click Restore."
                    ),
                }
            ),
            413,
        )
    kind = (request.form.get("kind") or "").strip().lower()
    if kind in {"", "auto"}:
        kind = ""
    if upload is None or not upload.filename:
        return jsonify({"ok": False, "error": "Select a VPS .bak or .zip backup file."}), 400
    file_name = upload.filename.strip()
    lower = file_name.lower()
    if not kind:
        if lower.endswith(".bak"):
            kind = "database"
        elif lower.endswith(".zip"):
            kind = "full"
        else:
            return jsonify({"ok": False, "error": "File must be .bak or .zip."}), 400
    if kind == "database" and not lower.endswith(".bak"):
        return jsonify({"ok": False, "error": "Database restore upload must be a .bak file."}), 400
    if kind == "full" and not lower.endswith(".zip"):
        return jsonify({"ok": False, "error": "Full restore upload must be a .zip file."}), 400
    try:
        # Stream to disk — do not upload.read() entire .bak into memory.
        info = BackupService().save_uploaded_backup(kind, file_name, upload)
        return jsonify({"ok": True, "backup": info, "message": info["message"]})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RequestEntityTooLarge:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "File too large for upload (max 2 GB). Copy into Local data folder, then Restore.",
                }
            ),
            413,
        )
    except Exception as exc:
        current_app.logger.exception("Backup upload failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


def _release_db_session_after_restore() -> None:
    """Avoid SQLAlchemy teardown rollback on connections killed by RESTORE."""
    try:
        db.session.invalidate()
    except Exception:
        pass
    try:
        db.session.remove()
    except Exception:
        pass
    try:
        db.engine.dispose()
    except Exception:
        pass


@bp.route("/api/restore/run", methods=["POST"])
@login_required
@admin_required
@require_delete_reauth
def run_restore_backup():
    payload = request.get_json(silent=True) or {}
    kind = (payload.get("kind") or request.form.get("kind") or "").strip().lower()
    file_name = (payload.get("file_name") or request.form.get("file_name") or "").strip()
    if not kind or not file_name:
        return jsonify({"ok": False, "error": "kind and file_name are required."}), 400

    # Credential check may have opened a pooled JTCSS connection — release it
    # before RESTORE SET SINGLE_USER disconnects everyone.
    _release_db_session_after_restore()

    service = BackupService()
    try:
        if kind == "database":
            info = service.restore_database(file_name, restored_by=_actor())
        elif kind == "full":
            info = service.restore_full(file_name, restored_by=_actor())
        else:
            return jsonify({"ok": False, "error": "Unknown backup kind."}), 400

        _release_db_session_after_restore()
        # Prove local DB accepts new connections (best-effort; do not fail restore).
        try:
            db.session.execute(text("SELECT 1"))
            db.session.commit()
        except Exception as exc:
            current_app.logger.warning("Post-restore ping: %s", exc)
            _release_db_session_after_restore()

        response = jsonify(
            {
                "ok": True,
                "restore": info,
                "message": info.get("message") or "Restore complete.",
                "reload_recommended": True,
            }
        )
        _release_db_session_after_restore()
        return response
    except ValueError as exc:
        _release_db_session_after_restore()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Backup restore failed")
        _release_db_session_after_restore()
        return jsonify({"ok": False, "error": str(exc)}), 500
