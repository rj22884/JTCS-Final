from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from app.decorators import admin_required, login_required, require_delete_reauth
from app.services.menu_service import MenuService

bp = Blueprint("menu_admin", __name__, url_prefix="/admin/menus")


@bp.route("/")
@login_required
@admin_required
def index():
    menu_service = MenuService()
    menu_tree = menu_service.list_tree_for_admin(include_inactive=True)
    return render_template(
        "menu_admin/list.html",
        page_title="Menu Management",
        menu_tree=menu_tree,
    )


@bp.route("/reorder", methods=["POST"])
@login_required
@admin_required
def reorder():
    payload = request.get_json(silent=True) or {}
    items = payload.get("orders")
    if not isinstance(items, list):
        return jsonify({"ok": False, "error": "Invalid reorder payload."}), 400

    menu_service = MenuService()
    ok, error = menu_service.reorder_batch(items)
    if not ok:
        return jsonify({"ok": False, "error": error or "Could not update order."}), 400
    return jsonify({"ok": True, "message": "Menu order / parent updated."})


@bp.route("/create", methods=["GET", "POST"])
@login_required
@admin_required
def create():
    menu_service = MenuService()
    parent_options = menu_service.flat_menu_options()

    if request.method == "POST":
        menu, error = menu_service.create_menu(request.form)
        if error:
            flash(error, "danger")
        else:
            flash("Menu created successfully.", "success")
            return redirect(url_for("menu_admin.index"))

    return render_template(
        "menu_admin/form.html",
        page_title="Add Menu",
        menu=None,
        parent_options=parent_options,
        roles=["Administrator", "Manager", "Operator", "Viewer"],
    )


@bp.route("/<int:menu_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit(menu_id: int):
    menu_service = MenuService()
    menu = menu_service.get(menu_id)
    if menu is None:
        flash("Menu not found.", "danger")
        return redirect(url_for("menu_admin.index"))

    parent_options = menu_service.flat_menu_options(exclude_id=menu_id)

    if request.method == "POST":
        updated, error = menu_service.update_menu(menu_id, request.form)
        if error:
            flash(error, "danger")
        else:
            flash("Menu updated successfully.", "success")
            return redirect(url_for("menu_admin.index"))

    return render_template(
        "menu_admin/form.html",
        page_title="Edit Menu",
        menu=menu,
        parent_options=parent_options,
        roles=["Administrator", "Manager", "Operator", "Viewer"],
    )


@bp.route("/<int:menu_id>/delete", methods=["POST"])
@login_required
@admin_required
@require_delete_reauth
def delete(menu_id: int):
    menu_service = MenuService()
    ok, error = menu_service.delete_menu(menu_id)
    flash(error or "Menu deleted successfully.", "danger" if error else "success")
    return redirect(url_for("menu_admin.index"))


@bp.route("/<int:menu_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle(menu_id: int):
    menu_service = MenuService()
    menu = menu_service.get(menu_id)
    if menu is None:
        flash("Menu not found.", "danger")
        return redirect(url_for("menu_admin.index"))

    menu_service.set_active(menu_id, not menu.IsActive)
    flash("Menu status updated.", "success")
    return redirect(url_for("menu_admin.index"))


@bp.route("/<int:menu_id>/order", methods=["POST"])
@login_required
@admin_required
def change_order(menu_id: int):
    menu_service = MenuService()
    display_order = int(request.form.get("DisplayOrder", 0))
    _, error = menu_service.change_order(menu_id, display_order)
    flash(error or "Display order updated.", "danger" if error else "success")
    return redirect(url_for("menu_admin.index"))
