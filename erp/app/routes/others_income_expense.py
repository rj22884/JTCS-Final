from datetime import date

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.customer_master.constants import CUSTOMER_TYPES
from app.decorators import login_required, require_delete_reauth
from app.repositories.transaction_repository import MasterRepository
from app.services.menu_service import MenuService
from app.services.others_income_expense_service import OthersIncomeExpenseService

bp = Blueprint("others_income_expense", __name__, url_prefix="/others/income-expense")

MENU_PATH = "/others/income-expense"


@bp.route("", methods=["GET", "POST"], strict_slashes=False)
@bp.route("/", methods=["GET", "POST"], strict_slashes=False)
@login_required
def index():
    service = OthersIncomeExpenseService()
    menu_service = MenuService()
    master_repo = MasterRepository()

    if request.method == "POST":
        try:
            result = service.save_entry(
                request.form,
                created_by=session.get("user_name", "System"),
            )
            flash(result.message, "success")
            return redirect(url_for("others_income_expense.index"))
        except ValueError as exc:
            flash(str(exc), "danger")
        except Exception as exc:
            flash(f"Unable to save entry: {exc}", "danger")

    return render_template(
        "others/income_expense_activity.html",
        page_title="Income / Expense",
        breadcrumb=menu_service.get_breadcrumb(MENU_PATH, session.get("role")),
        default_date=date.today().isoformat(),
        income_work_types=service.list_work_types(ledger_kind=OthersIncomeExpenseService.LEDGER_INCOME),
        expense_work_types=service.list_work_types(ledger_kind=OthersIncomeExpenseService.LEDGER_EXPENSE),
        misc_work_types=service.list_work_types(ledger_kind=OthersIncomeExpenseService.LEDGER_MISC),
        payment_modes=master_repo.list_stamp_bank_payment_modes(qr_bill_received_only=False),
        customer_groups=service.list_customer_groups(),
        customer_types=CUSTOMER_TYPES,
        load_entry_id=request.args.get("load_entry", type=int),
    )


@bp.route("/save", methods=["POST"], strict_slashes=False)
@login_required
def save_record():
    service = OthersIncomeExpenseService()
    try:
        result = service.save_entry(
            request.form,
            created_by=session.get("user_name", "System"),
        )
        return jsonify(
            {
                "ok": True,
                "message": result.message,
                "entry_id": result.entry_id,
                "bill_no": result.bill_no,
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to save entry: {exc}"}), 500


@bp.route("/grid", methods=["GET"], strict_slashes=False)
@login_required
def grid():
    service = OthersIncomeExpenseService()
    ledger_kind = (request.args.get("ledger_kind") or "").strip() or None
    if ledger_kind not in OthersIncomeExpenseService.LEDGER_KINDS:
        ledger_kind = None
    return jsonify({"ok": True, "rows": service.list_entries(ledger_kind=ledger_kind)})


@bp.route("/work-types", methods=["GET"], strict_slashes=False)
@login_required
def work_types():
    service = OthersIncomeExpenseService()
    ledger_kind = (request.args.get("ledger_kind") or "").strip()
    if ledger_kind not in OthersIncomeExpenseService.LEDGER_KINDS:
        return jsonify({"ok": False, "error": "ledger_kind must be Income, Expense, or Misc."}), 400
    return jsonify({"ok": True, "rows": service.list_work_types(ledger_kind=ledger_kind)})


@bp.route("/sub-works", methods=["GET"], strict_slashes=False)
@login_required
def sub_works():
    service = OthersIncomeExpenseService()
    work_name = (request.args.get("work_name") or request.args.get("workName") or "").strip()
    if not work_name:
        return jsonify({"ok": False, "error": "work_name is required."}), 400
    return jsonify({"ok": True, "rows": service.list_sub_works(work_name)})


@bp.route("/next-bill-no", methods=["GET"], strict_slashes=False)
@login_required
def next_bill_no():
    service = OthersIncomeExpenseService()
    work_date_raw = (request.args.get("work_date") or "").strip()
    ledger_kind = (request.args.get("ledger_kind") or OthersIncomeExpenseService.LEDGER_INCOME).strip()
    try:
        work_date = date.fromisoformat(work_date_raw[:10])
    except ValueError:
        return jsonify({"ok": False, "error": "Valid work date is required."}), 400
    if ledger_kind not in OthersIncomeExpenseService.LEDGER_KINDS:
        ledger_kind = OthersIncomeExpenseService.LEDGER_INCOME
    return jsonify({"ok": True, "bill_no": service.next_bill_no(work_date, ledger_kind=ledger_kind)})


@bp.route("/customers/search", methods=["GET"], strict_slashes=False)
@login_required
def customer_search():
    query = (request.args.get("q") or request.args.get("query") or "").strip()
    rows = OthersIncomeExpenseService().search_customers(query)
    return jsonify({"ok": True, "rows": rows})


@bp.route("/customers", methods=["POST"], strict_slashes=False)
@login_required
def customer_create():
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        customer = OthersIncomeExpenseService().create_customer(payload)
        return jsonify({"ok": True, "customer": customer, "message": "Customer added successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to add customer: {exc}"}), 500


@bp.route("/records/<int:entry_id>", methods=["GET"], strict_slashes=False)
@login_required
def record(entry_id: int):
    service = OthersIncomeExpenseService()
    try:
        return jsonify({"ok": True, "record": service.get_entry(entry_id)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/records/<int:entry_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def delete_record(entry_id: int):
    service = OthersIncomeExpenseService()
    try:
        message = service.delete_entry(entry_id)
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
