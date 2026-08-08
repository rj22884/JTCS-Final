"""Admin Role → Utility (Upload VPS locally / Download Local on VPS)."""

from __future__ import annotations

import json

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    stream_with_context,
    url_for,
)
from sqlalchemy import text

from app.decorators import admin_required, login_required
from app.extensions import db
from app.services.menu_service import MenuService
from app.services.utility_service import UtilityService
from app.utils.runtime_env import (
    is_vps_runtime,
    sync_menu_description,
    sync_menu_label,
)

bp = Blueprint("utility", __name__, url_prefix="/admin/utility")

_MENU_ENSURED = False


def ensure_utility_menus() -> None:
    """Admin Role → Utility → children (idempotent; sync label follows runtime)."""
    global _MENU_ENSURED
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

    utility_id = db.session.execute(
        text(
            """
            SELECT TOP 1 MenuID FROM dbo.MenuMaster
            WHERE ParentMenuID = :pid
              AND (MenuName = N'Utility' OR MenuURL = N'/admin/utility')
            ORDER BY MenuID
            """
        ),
        {"pid": parent_id},
    ).scalar()

    if utility_id:
        db.session.execute(
            text(
                """
                UPDATE dbo.MenuMaster
                SET MenuName = N'Utility',
                    MenuIcon = N'bi-tools',
                    MenuURL = N'/admin/utility',
                    DisplayOrder = 60,
                    IsActive = 1,
                    Description = N'Local/VPS sync and maintenance tools',
                    RoleName = N'Administrator,Admin'
                WHERE MenuID = :id
                """
            ),
            {"id": utility_id},
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
                    :pid, N'Utility', N'bi-tools', N'/admin/utility', 60,
                    N'Local/VPS sync and maintenance tools', 1, N'Administrator,Admin'
                )
                """
            ),
            {"pid": parent_id},
        )
        db.session.flush()
        utility_id = db.session.execute(
            text(
                """
                SELECT TOP 1 MenuID FROM dbo.MenuMaster
                WHERE ParentMenuID = :pid AND MenuURL = N'/admin/utility'
                ORDER BY MenuID DESC
                """
            ),
            {"pid": parent_id},
        ).scalar()

    sync_name = sync_menu_label()
    sync_desc = sync_menu_description()
    # System Health moved to Admin → System Administration → System Health
    children = (
        (sync_name, "/admin/utility/sync", 1, "bi-cloud-arrow-up", sync_desc),
        ("Clear Cache", "/admin/utility/clear-cache", 2, "bi-trash", "Clear Python/template caches"),
        ("App Info", "/admin/utility/info", 3, "bi-info-circle", "Runtime mode, paths, VPS target"),
    )

    for name, url, order, icon, desc in children:
        # Sync item is keyed by URL so the label can flip Local ↔ VPS safely.
        if url == "/admin/utility/sync":
            existing = db.session.execute(
                text(
                    """
                    SELECT TOP 1 MenuID FROM dbo.MenuMaster
                    WHERE MenuURL = N'/admin/utility/sync'
                    ORDER BY MenuID
                    """
                )
            ).scalar()
        else:
            existing = db.session.execute(
                text(
                    """
                    SELECT TOP 1 MenuID FROM dbo.MenuMaster
                    WHERE ParentMenuID = :pid
                      AND (MenuURL = :url OR MenuName = :name)
                    ORDER BY MenuID
                    """
                ),
                {"pid": utility_id, "url": url, "name": name},
            ).scalar()
        if existing:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.MenuMaster
                    SET MenuName = :name,
                        MenuURL = :url,
                        MenuIcon = :icon,
                        DisplayOrder = :ord,
                        Description = :desc,
                        IsActive = 1,
                        RoleName = N'Administrator,Admin',
                        ParentMenuID = :pid
                    WHERE MenuID = :id
                    """
                ),
                {
                    "name": name,
                    "url": url,
                    "icon": icon,
                    "ord": order,
                    "desc": desc,
                    "pid": utility_id,
                    "id": existing,
                },
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
                        :pid, :name, :icon, :url, :ord, :desc, 1, N'Administrator,Admin'
                    )
                    """
                ),
                {
                    "pid": utility_id,
                    "name": name,
                    "icon": icon,
                    "url": url,
                    "ord": order,
                    "desc": desc,
                },
            )

    # Prefer cloud-download icon when running on VPS.
    db.session.execute(
        text(
            """
            UPDATE dbo.MenuMaster
            SET MenuIcon = :icon
            WHERE MenuURL = N'/admin/utility/sync'
            """
        ),
        {"icon": "bi-cloud-arrow-down" if is_vps_runtime() else "bi-cloud-arrow-up"},
    )
    db.session.commit()
    _MENU_ENSURED = True


@bp.before_request
def _refresh_sync_label():
    try:
        ensure_utility_menus()
    except Exception:
        db.session.rollback()


def _actor() -> str:
    return (
        session.get("full_name")
        or session.get("username")
        or session.get("user_id")
        or "Admin"
    )


@bp.route("", strict_slashes=False)
@bp.route("/", strict_slashes=False)
@login_required
@admin_required
def index():
    return render_template(
        "utility/index.html",
        page_title="Utility",
        breadcrumb=MenuService().get_breadcrumb("/admin/utility", session.get("role")),
        is_vps=is_vps_runtime(),
        sync_label=sync_menu_label(),
        info=UtilityService().app_info(),
    )


@bp.route("/sync", strict_slashes=False)
@login_required
@admin_required
def sync_page():
    svc = UtilityService()
    vps = is_vps_runtime()
    return render_template(
        "utility/sync.html",
        page_title=sync_menu_label(),
        breadcrumb=MenuService().get_breadcrumb(
            "/admin/utility/sync", session.get("role")
        ),
        is_vps=vps,
        sync_label=sync_menu_label(),
        info=svc.app_info(),
    )


@bp.route("/clear-cache", strict_slashes=False)
@login_required
@admin_required
def clear_cache_page():
    return render_template(
        "utility/clear_cache.html",
        page_title="Clear Cache",
        breadcrumb=MenuService().get_breadcrumb(
            "/admin/utility/clear-cache", session.get("role")
        ),
    )


@bp.route("/health", strict_slashes=False)
@login_required
@admin_required
def health_page():
    """Legacy URL — Mission Control lives under System Administration."""
    return redirect(url_for("system_health.index"))


@bp.route("/info", strict_slashes=False)
@login_required
@admin_required
def info_page():
    return render_template(
        "utility/info.html",
        page_title="App Info",
        breadcrumb=MenuService().get_breadcrumb(
            "/admin/utility/info", session.get("role")
        ),
        info=UtilityService().app_info(),
    )


@bp.route("/api/deploy", methods=["POST"])
@login_required
@admin_required
def api_deploy():
    """Legacy JSON deploy (no live log). Prefer /api/deploy/stream."""
    if is_vps_runtime():
        return jsonify(ok=False, error="Upload VPS only works on local PC."), 400
    payload = request.get_json(silent=True) or {}
    password = str(payload.get("password") or "")
    commit_message = str(payload.get("commit_message") or "").strip()
    try:
        result = UtilityService().deploy_to_vps(
            password=password,
            commit_message=commit_message,
            created_by=_actor(),
        )
        return jsonify(result)
    except Exception as exc:
        current_app.logger.exception("Utility Upload VPS failed")
        return jsonify(ok=False, error=str(exc)), 500


@bp.route("/api/deploy/stream", methods=["POST"])
@login_required
@admin_required
def api_deploy_stream():
    """NDJSON stream of deploy logs for the live panel."""
    if is_vps_runtime():
        return jsonify(ok=False, error="Upload VPS only works on local PC."), 400
    payload = request.get_json(silent=True) or {}
    password = str(payload.get("password") or "")
    commit_message = str(payload.get("commit_message") or "").strip()
    actor = _actor()

    @stream_with_context
    def generate():
        try:
            for event in UtilityService().iter_deploy_to_vps(
                password=password,
                commit_message=commit_message,
                created_by=actor,
            ):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception as exc:
            current_app.logger.exception("Utility Upload VPS stream failed")
            yield json.dumps({"type": "error", "ok": False, "error": str(exc)}) + "\n"

    return Response(
        generate(),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@bp.route("/api/download", methods=["POST"])
@login_required
@admin_required
def api_download_create():
    if not is_vps_runtime():
        return jsonify(ok=False, error="Download Local only works on the VPS."), 400
    try:
        info = UtilityService().create_download_package(created_by=_actor())
        return jsonify(ok=True, **info)
    except Exception as exc:
        current_app.logger.exception("Utility Download Local failed")
        return jsonify(ok=False, error=str(exc)), 500


@bp.route("/api/download/<path:file_name>", methods=["GET"])
@login_required
@admin_required
def api_download_file(file_name: str):
    if not is_vps_runtime():
        return jsonify(ok=False, error="Download Local only works on the VPS."), 400
    try:
        path = UtilityService().resolve_download_package(file_name)
        return send_file(
            path,
            as_attachment=True,
            download_name=path.name,
            mimetype="application/zip",
        )
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 404


@bp.route("/api/clear-cache", methods=["POST"])
@login_required
@admin_required
def api_clear_cache():
    try:
        return jsonify(UtilityService().clear_caches())
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 500


@bp.route("/api/health", methods=["GET"])
@login_required
@admin_required
def api_health():
    return jsonify(UtilityService().system_health())
