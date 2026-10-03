"""Admin Role → System Maintenance / Storage Cleanup."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request, session
from sqlalchemy import text

from app.decorators import login_required
from app.extensions import db
from app.modules.system_maintenance.service import CLEANUP_CATEGORIES, SystemMaintenanceService
from app.services.menu_service import MenuService

bp = Blueprint("system_maintenance", __name__, url_prefix="/admin/system-maintenance")
MENU_PATH = "/admin/system-maintenance"
# Visible to every authenticated ERP role (menu RoleName filter).
_ALL_AUTH_ROLES = "Administrator,Admin,Manager,Operator,Viewer"

_MENU_READY = False


def ensure_system_maintenance_menus() -> None:
    """Admin Role → System Maintenance / Storage Cleanup (all authenticated roles)."""
    global _MENU_READY
    if _MENU_READY:
        return

    SystemMaintenanceService().ensure_schema()

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
                    N'Administrator tools', 1, :roles
                )
                """
            ),
            {"roles": _ALL_AUTH_ROLES},
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

    # Keep Admin Role visible to staff who need Data Backup / Maintenance.
    db.session.execute(
        text(
            """
            UPDATE dbo.MenuMaster
            SET RoleName = :roles,
                IsActive = 1
            WHERE MenuID = :pid
            """
        ),
        {"pid": parent_id, "roles": _ALL_AUTH_ROLES},
    )

    existing = db.session.execute(
        text(
            """
            SELECT TOP 1 MenuID FROM dbo.MenuMaster
            WHERE MenuURL = :url OR MenuName = N'System Maintenance / Storage Cleanup'
            ORDER BY MenuID
            """
        ),
        {"url": MENU_PATH},
    ).scalar()

    if existing:
        db.session.execute(
            text(
                """
                UPDATE dbo.MenuMaster
                SET ParentMenuID = :pid,
                    MenuName = N'System Maintenance / Storage Cleanup',
                    MenuIcon = N'bi-hdd-stack',
                    MenuURL = :url,
                    DisplayOrder = 55,
                    Description = N'Safe disk scan and selectable storage cleanup',
                    IsActive = 1,
                    RoleName = :roles
                WHERE MenuID = :id
                """
            ),
            {"pid": parent_id, "url": MENU_PATH, "roles": _ALL_AUTH_ROLES, "id": existing},
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
                    :pid,
                    N'System Maintenance / Storage Cleanup',
                    N'bi-hdd-stack',
                    :url,
                    55,
                    N'Safe disk scan and selectable storage cleanup',
                    1,
                    :roles
                )
                """
            ),
            {"pid": parent_id, "url": MENU_PATH, "roles": _ALL_AUTH_ROLES},
        )

    db.session.commit()
    _MENU_READY = True


def _actor() -> str:
    return (session.get("user_name") or session.get("full_name") or "System").strip() or "System"


@bp.route("", strict_slashes=False)
@bp.route("/", strict_slashes=False)
@login_required
def index():
    service = SystemMaintenanceService()
    service.ensure_schema()
    return render_template(
        "system_maintenance/index.html",
        page_title="System Maintenance / Storage Cleanup",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        catalog=[
            {"key": k, "label": v["label"], "description": v["description"]}
            for k, v in CLEANUP_CATEGORIES.items()
        ],
        disk=service.disk_summary(),
        folders=service.folder_overview(),
        audit=service.recent_audit(limit=15),
    )


@bp.route("/api/scan", methods=["POST"])
@login_required
def api_scan():
    payload = request.get_json(silent=True) or {}
    categories = payload.get("categories") or []
    try:
        service = SystemMaintenanceService()
        result = service.scan(categories if isinstance(categories, list) else [])
        dry = service.cleanup(
            categories if isinstance(categories, list) else [],
            dry_run=True,
            actor=_actor(),
        )
        result["categories"] = dry.get("categories") or result.get("categories")
        result["totals"] = {
            "bytes": dry.get("bytes_freed") or 0,
            "bytes_label": dry.get("bytes_freed_label") or "0 B",
            "items": dry.get("items_removed") or 0,
        }
        result["message"] = dry.get("message") or "Scan complete."
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        current_app.logger.exception("System maintenance scan failed")
        return jsonify({"ok": False, "error": "Scan failed."}), 500


@bp.route("/api/cleanup", methods=["POST"])
@login_required
def api_cleanup():
    payload = request.get_json(silent=True) or {}
    categories = payload.get("categories") or []
    dry_run = bool(payload.get("dry_run"))
    confirm = bool(payload.get("confirm"))
    if not dry_run and not confirm:
        return jsonify({"ok": False, "error": "Confirm cleanup is required."}), 400
    try:
        result = SystemMaintenanceService().cleanup(
            categories if isinstance(categories, list) else [],
            dry_run=dry_run,
            actor=_actor(),
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        current_app.logger.exception("System maintenance cleanup failed")
        return jsonify({"ok": False, "error": "Cleanup failed."}), 500


@bp.route("/api/audit", methods=["GET"])
@login_required
def api_audit():
    try:
        rows = SystemMaintenanceService().recent_audit(limit=int(request.args.get("limit") or 20))
        return jsonify({"ok": True, "rows": rows})
    except Exception:
        current_app.logger.exception("System maintenance audit list failed")
        return jsonify({"ok": False, "error": "Unable to load audit log."}), 500


@bp.route("/api/summary", methods=["GET"])
@login_required
def api_summary():
    try:
        service = SystemMaintenanceService()
        return jsonify(
            {
                "ok": True,
                "disk": service.disk_summary(),
                "folders": service.folder_overview(),
            }
        )
    except Exception:
        current_app.logger.exception("System maintenance summary failed")
        return jsonify({"ok": False, "error": "Unable to load disk summary."}), 500
