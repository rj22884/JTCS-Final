from flask import Blueprint, abort, render_template, session

from app.decorators import login_required
from app.services.menu_service import MenuService

bp = Blueprint("pages", __name__)

RESERVED_PATHS = {
    "login",
    "logout",
    "health",
    "dashboard",
    "admin",
    "setup",
    "register",
    "transactions",
    "reports",
    "shcil",
    "others",
    "masters",
    "exceptional-report",
}


def _render_builtin_module(page_path: str):
    normalized = (page_path or "").strip().strip("/").lower()
    if normalized == "masters/bank":
        from app.routes.bank_master import index as bank_master_index

        return bank_master_index()
    if normalized == "masters/income-expense":
        from app.routes.masters_work import index as income_expense_index

        return income_expense_index()
    if normalized == "masters/sub-work":
        from app.routes.masters_sub_work import index as sub_work_index

        return sub_work_index()
    if normalized == "masters/customer":
        from app.routes.masters_customer import index as customer_master_index

        return customer_master_index()
    if normalized == "masters/group":
        from app.routes.masters_group import index as group_master_index

        return group_master_index()
    if normalized == "masters/purpose":
        from app.routes.purpose_master import index as purpose_master_index

        return purpose_master_index()
    if normalized == "masters/credentials":
        from app.routes.credentials_master import index as credentials_master_index

        return credentials_master_index()
    return None


@bp.route("/<path:page_path>")
@login_required
def render_page(page_path: str):
    builtin = _render_builtin_module(page_path)
    if builtin is not None:
        return builtin

    root_segment = page_path.split("/", 1)[0]
    if root_segment in RESERVED_PATHS or page_path.startswith("masters/"):
        abort(404)

    menu_url = f"/{page_path}"
    menu_service = MenuService()
    menu = menu_service.repository.find_by_url(menu_url)

    if menu is None:
        abort(404)

    if not menu_service.can_access_menu(menu, session.get("role")):
        abort(403)

    breadcrumb = menu_service.get_breadcrumb(menu_url, session.get("role"))
    return render_template(
        "pages/placeholder.html",
        page_title=menu.MenuName,
        menu=menu,
        breadcrumb=breadcrumb,
    )
