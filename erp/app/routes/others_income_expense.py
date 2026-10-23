from datetime import date
from decimal import Decimal

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.customer_master.constants import CUSTOMER_TYPES, GENDERS
from app.decorators import login_required, require_delete_reauth
from app.repositories.transaction_repository import MasterRepository
from app.services.menu_service import MenuService
from app.services.others_income_expense_service import OthersIncomeExpenseService
from app.services.chart_group_service import ChartGroupService
from app.services.scoped_customer_service import ScopedCustomerService

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
        kind = (request.form.get("LedgerKind") or "").strip()
        if kind in ("Misc.", "Misc", "m", "M"):
            flash("Miscellaneous entries belong in Activities → Miscellaneous.", "danger")
        else:
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
        misc_work_types=[],
        payment_modes=master_repo.list_stamp_bank_payment_modes(),
        customer_groups=service.list_customer_groups(),
        chart_of_groups=ChartGroupService().list_active_for_dropdown(),
        customer_types=CUSTOMER_TYPES,
        genders=GENDERS,
        load_entry_id=request.args.get("load_entry", type=int),
        hide_misc=True,
    )


@bp.route("/duplicate-check", methods=["GET"], strict_slashes=False)
@login_required
def duplicate_check():
    service = OthersIncomeExpenseService()
    try:
        customer_id = int(request.args.get("customer_id") or 0)
    except (TypeError, ValueError):
        customer_id = 0
    try:
        amount = Decimal(str(request.args.get("amount") or "0"))
    except Exception:
        amount = Decimal("0")
    dates: list[date] = []
    raw_dates = request.args.getlist("dates") or []
    work_date = (request.args.get("work_date") or "").strip()
    if work_date:
        raw_dates.append(work_date)
    for raw in raw_dates:
        try:
            dates.append(date.fromisoformat(str(raw)[:10]))
        except ValueError:
            continue
    try:
        exclude_raw = (request.args.get("exclude_entry_id") or "").strip()
        exclude_entry_id = int(exclude_raw) if exclude_raw else None
    except (TypeError, ValueError):
        exclude_entry_id = None
    try:
        result = service.duplicate_customer_warning(
            customer_id=customer_id,
            amount=amount,
            dates=dates,
            exclude_entry_id=exclude_entry_id,
        )
    except Exception as exc:
        return jsonify({"ok": False, "duplicate": False, "error": str(exc)}), 500
    return jsonify({"ok": True, **result})


@bp.route("/save", methods=["POST"], strict_slashes=False)
@login_required
def save_record():
    service = OthersIncomeExpenseService()
    kind = (request.form.get("LedgerKind") or request.form.get("ledger_kind") or "").strip()
    if kind in ("Misc.", "Misc", "m", "M"):
        return jsonify(
            {
                "ok": False,
                "error": "Miscellaneous entries belong in Activities → Miscellaneous.",
            }
        ), 400
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
    income = OthersIncomeExpenseService.LEDGER_INCOME
    expense = OthersIncomeExpenseService.LEDGER_EXPENSE
    ledger_kind = (request.args.get("ledger_kind") or "").strip() or None
    if ledger_kind == OthersIncomeExpenseService.LEDGER_MISC:
        return jsonify({"ok": True, "rows": []})
    if ledger_kind in (income, expense):
        rows = service.list_entries(ledger_kind=ledger_kind)
    else:
        rows = service.list_entries(ledger_kinds=(income, expense))
    return jsonify({"ok": True, "rows": rows})


@bp.route("/work-types", methods=["GET"], strict_slashes=False)
@login_required
def work_types():
    service = OthersIncomeExpenseService()
    ledger_kind = (request.args.get("ledger_kind") or "").strip()
    if ledger_kind not in (
        OthersIncomeExpenseService.LEDGER_INCOME,
        OthersIncomeExpenseService.LEDGER_EXPENSE,
    ):
        return jsonify({"ok": False, "error": "ledger_kind must be Income or Expense."}), 400
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
        customer = ScopedCustomerService().create(payload)
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
        data = service.get_entry(entry_id)
        if (data.get("ledger_kind") or "") == OthersIncomeExpenseService.LEDGER_MISC:
            return jsonify(
                {
                    "ok": False,
                    "error": "This is a Miscellaneous entry. Open it from Activities → Miscellaneous.",
                }
            ), 404
        return jsonify({"ok": True, "record": data})
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
        row = service.entry_repo.get_by_id(entry_id)
        if row is None:
            return jsonify({"ok": False, "error": "Income / expense record not found."}), 404
        data = service._entry_dict(row)
        if (data.get("ledger_kind") or "") == OthersIncomeExpenseService.LEDGER_MISC:
            return jsonify(
                {
                    "ok": False,
                    "error": "Miscellaneous entries can only be deleted from Activities → Miscellaneous.",
                }
            ), 400
        message = service.delete_entry(entry_id)
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
