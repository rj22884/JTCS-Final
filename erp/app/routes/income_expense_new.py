"""Activities → income expense new (moved Income/Expense records)."""

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.services.income_expense_new_service import IncomeExpenseNewService
from app.services.menu_service import MenuService

bp = Blueprint(
    "income_expense_new",
    __name__,
    url_prefix="/activities/income_expense_new",
)

bp_alias = Blueprint(
    "income_expense_new_alias",
    __name__,
    url_prefix="/activities/income-expense-new",
)

MENU_PATH = "/activities/income_expense_new"


def _index_response():
    service = IncomeExpenseNewService()
    rows = service.list_entries()
    return render_template(
        "activities/income_expense_new.html",
        page_title="Income Expense New",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        initial_rows=rows,
    )


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
def index():
    return _index_response()


@bp_alias.route("", methods=["GET"], strict_slashes=False)
@bp_alias.route("/", methods=["GET"], strict_slashes=False)
@bp_alias.route("/<path:rest>", methods=["GET", "POST"], strict_slashes=False)
@login_required
def redirect_hyphen_alias(rest: str | None = None):
    target = "/activities/income_expense_new"
    if rest:
        target = f"{target}/{rest.lstrip('/')}"
    if request.query_string:
        target = f"{target}?{request.query_string.decode('utf-8', errors='ignore')}"
    return redirect(target, code=307)


@bp.route("/exit")
@login_required
def exit_module():
    return redirect(url_for("dashboard.index"))


@bp.route("/api/grid", methods=["GET"], strict_slashes=False)
@login_required
def grid():
    ledger_kind = (request.args.get("ledger_kind") or "").strip() or None
    try:
        rows = IncomeExpenseNewService().list_entries(ledger_kind=ledger_kind)
        return jsonify({"ok": True, "rows": rows, "count": len(rows)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
