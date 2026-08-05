"""Admin Role → Menu Customization (Excel/Word-style main + submenu editor)."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import text

from app.decorators import admin_required, login_required
from app.extensions import db
from app.services.menu_service import MenuService

bp = Blueprint("menu_customization", __name__, url_prefix="/admin/menu-customization")

MENU_PATH = "/admin/menu-customization"
_MENU_ENSURED = False


def _ensure_menu_customization_menu() -> None:
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
            END;

            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE ParentMenuID = @ParentID AND MenuName = N'Menu Customization'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuURL = N'/admin/menu-customization',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-ui-checks-grid'),
                    DisplayOrder = 55,
                    Description = N'Customize main ribbon menus — reorder, add, remove',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE ParentMenuID = @ParentID AND MenuName = N'Menu Customization';
            END
            ELSE IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/menu-customization'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ParentID,
                    MenuName = N'Menu Customization',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-ui-checks-grid'),
                    DisplayOrder = 55,
                    Description = N'Customize main ribbon menus — reorder, add, remove',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE MenuURL = N'/admin/menu-customization';
            END
            ELSE
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID,
                    N'Menu Customization',
                    N'bi-ui-checks-grid',
                    N'/admin/menu-customization',
                    55,
                    N'Customize main ribbon menus — reorder, add, remove',
                    1,
                    @AdminRoles
                );
            END;
            """
        )
    )
    db.session.commit()
    _MENU_ENSURED = True


def ensure_menu_customization_menu() -> None:
    _ensure_menu_customization_menu()


def _parse_parent_id(raw) -> int | None | object:
    """Return None for main level, int for parent, or False if invalid."""
    if raw in (None, "", "null", "None"):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return False


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def index():
    try:
        _ensure_menu_customization_menu()
    except Exception:
        db.session.rollback()
    return render_template(
        "menu_customization/index.html",
        page_title="Menu Customization",
    )


@bp.route("/api/list", methods=["GET"])
@login_required
@admin_required
def api_list():
    parent_raw = request.args.get("parent_id")
    parent_id = _parse_parent_id(parent_raw)
    if parent_id is False:
        return jsonify({"ok": False, "error": "Invalid parent id."}), 400
    payload = MenuService().list_menus_for_customization(parent_id)
    if not payload.get("ok", True) and payload.get("error"):
        return jsonify({"ok": False, "error": payload["error"]}), 404
    return jsonify({"ok": True, **payload})


@bp.route("/api/move", methods=["POST"])
@login_required
@admin_required
def api_move():
    payload = request.get_json(silent=True) or {}
    try:
        menu_id = int(payload.get("menu_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid menu id."}), 400
    parent_id = _parse_parent_id(payload.get("parent_id"))
    if parent_id is False:
        return jsonify({"ok": False, "error": "Invalid parent id."}), 400
    direction = str(payload.get("direction") or "")
    svc = MenuService()
    ok, error = svc.move_customization_menu(menu_id, direction, parent_id=parent_id)
    if not ok:
        return jsonify({"ok": False, "error": error or "Move failed."}), 400
    data = svc.list_menus_for_customization(parent_id)
    return jsonify({"ok": True, **data})


@bp.route("/api/add", methods=["POST"])
@login_required
@admin_required
def api_add():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "")
    url = str(payload.get("url") or "") or None
    icon = str(payload.get("icon") or "") or None
    parent_id = _parse_parent_id(payload.get("parent_id"))
    if parent_id is False:
        return jsonify({"ok": False, "error": "Invalid parent id."}), 400
    svc = MenuService()
    menu, error = svc.add_customization_menu(
        name, parent_id=parent_id, url=url, icon=icon
    )
    if error or menu is None:
        return jsonify({"ok": False, "error": error or "Could not add menu."}), 400
    data = svc.list_menus_for_customization(parent_id)
    return jsonify({"ok": True, **data, "menu_id": menu.MenuID})


@bp.route("/api/remove", methods=["POST"])
@login_required
@admin_required
def api_remove():
    payload = request.get_json(silent=True) or {}
    try:
        menu_id = int(payload.get("menu_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid menu id."}), 400
    parent_id = _parse_parent_id(payload.get("parent_id"))
    if parent_id is False:
        return jsonify({"ok": False, "error": "Invalid parent id."}), 400
    svc = MenuService()
    ok, error = svc.remove_customization_menu(menu_id)
    if not ok:
        return jsonify({"ok": False, "error": error or "Remove failed."}), 400
    data = svc.list_menus_for_customization(parent_id)
    return jsonify({"ok": True, **data})


@bp.route("/api/edit", methods=["POST"])
@login_required
@admin_required
def api_edit():
    payload = request.get_json(silent=True) or {}
    try:
        menu_id = int(payload.get("menu_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid menu id."}), 400
    parent_id = _parse_parent_id(payload.get("parent_id"))
    if parent_id is False:
        return jsonify({"ok": False, "error": "Invalid parent id."}), 400
    name = str(payload.get("name") or "")
    url = str(payload.get("url") or "") or None
    icon = str(payload.get("icon") or "") or None
    svc = MenuService()
    menu, error = svc.update_customization_menu(
        menu_id, name=name, url=url, icon=icon
    )
    if error or menu is None:
        return jsonify({"ok": False, "error": error or "Could not update menu."}), 400
    data = svc.list_menus_for_customization(parent_id)
    return jsonify({"ok": True, **data, "menu_id": menu.MenuID})
