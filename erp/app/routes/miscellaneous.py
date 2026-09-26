"""Activities → Miscellaneous (Misc. Work/Category from Work/Category Master)."""

from datetime import date

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from werkzeug.datastructures import MultiDict

from app.customer_master.constants import CUSTOMER_TYPES
from app.decorators import login_required, require_delete_reauth
from app.repositories.transaction_repository import MasterRepository
from app.services.followup_service import default_tax_period, tax_period_options
from app.services.bank_master_service import BankMasterService
from app.services.gst_invoice_service import STATE_CODES, GstInvoiceService
from app.services.menu_service import MenuService
from app.services.others_income_expense_service import OthersIncomeExpenseService

bp = Blueprint(
    "miscellaneous",
    __name__,
    url_prefix="/activities/miscellaneous",
)

# Existing Menu Customization entry "misc new"
bp_alias = Blueprint(
    "miscellaneous_alias",
    __name__,
    url_prefix="/activities/misc_new",
)

MENU_PATH = "/activities/miscellaneous"
FORCE_KIND = OthersIncomeExpenseService.LEDGER_MISC


def _index_response():
    service = OthersIncomeExpenseService()
    master_repo = MasterRepository()
    return render_template(
        "others/income_expense_activity.html",
        page_title="Miscellaneous",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        default_date=date.today().isoformat(),
        income_work_types=[],
        expense_work_types=[],
        misc_work_types=service.list_work_types(ledger_kind=FORCE_KIND),
        payment_modes=master_repo.list_stamp_bank_payment_modes(),
        customer_groups=service.list_customer_groups(),
        customer_types=CUSTOMER_TYPES,
        load_entry_id=request.args.get("load_entry", type=int),
        hide_misc=False,
        force_ledger_kind=FORCE_KIND,
        module_title="Miscellaneous Records",
        api_blueprint="miscellaneous",
        company=GstInvoiceService.company_profile(),
    )


def _forced_form():
    data = MultiDict(request.form)
    data.setlist("LedgerKind", [FORCE_KIND])
    return data


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
def index():
    return _index_response()


@bp_alias.route("", methods=["GET"], strict_slashes=False)
@bp_alias.route("/", methods=["GET"], strict_slashes=False)
@login_required
def index_alias():
    return _index_response()


@bp.route("/exit")
@bp_alias.route("/exit")
@login_required
def exit_module():
    return redirect(url_for("dashboard.index"))


@bp.route("/save", methods=["POST"], strict_slashes=False)
@bp_alias.route("/save", methods=["POST"], strict_slashes=False)
@login_required
def save_record():
    try:
        result = OthersIncomeExpenseService().save_entry(
            _forced_form(),
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
@bp_alias.route("/grid", methods=["GET"], strict_slashes=False)
@login_required
def grid():
    rows = OthersIncomeExpenseService().list_entries(ledger_kind=FORCE_KIND)
    return jsonify({"ok": True, "rows": rows})


@bp.route("/work-types", methods=["GET"], strict_slashes=False)
@bp_alias.route("/work-types", methods=["GET"], strict_slashes=False)
@login_required
def work_types():
    rows = OthersIncomeExpenseService().list_work_types(ledger_kind=FORCE_KIND)
    return jsonify({"ok": True, "rows": rows})


@bp.route("/sub-works", methods=["GET"], strict_slashes=False)
@bp_alias.route("/sub-works", methods=["GET"], strict_slashes=False)
@login_required
def sub_works():
    work_name = (request.args.get("work_name") or request.args.get("workName") or "").strip()
    if not work_name:
        return jsonify({"ok": False, "error": "work_name is required."}), 400
    return jsonify({"ok": True, "rows": OthersIncomeExpenseService().list_sub_works(work_name)})


def upi_bank_choices() -> list[dict]:
    """Active Bank Master accounts with QR/Bill Received = Yes."""
    try:
        rows = BankMasterService().list_records()
    except Exception:
        return []
    choices = []
    for row in rows:
        if not row.get("active_status", True):
            continue
        if not row.get("qr_bill_received"):
            continue
        name = (row.get("bank_name") or "").strip()
        number = (row.get("account_number") or "").strip()
        if name.casefold() == "cash" or number.casefold() == "cash":
            continue
        if not name and not number:
            continue
        choices.append(
            {
                "account_id": row.get("account_id"),
                "bank_name": name or "Bank",
                "account_number": number,
                "ifsc_code": (row.get("ifsc_code") or "").strip(),
                "upi_id": (row.get("upi_id") or "").strip(),
            }
        )
    return choices


@bp.route("/generate-bill/invoice", methods=["GET"], strict_slashes=False)
@bp_alias.route("/generate-bill/invoice", methods=["GET"], strict_slashes=False)
@login_required
def generate_bill_invoice():
    """Saved Miscellaneous invoice for this bill number, used by Edit."""
    bill_no = (request.args.get("bill_no") or "").strip()
    if not bill_no:
        return jsonify({"ok": False, "found": False, "error": "Bill number is required."}), 400
    found = GstInvoiceService().find_invoice_for_tally_bill(bill_no)
    if not found:
        return jsonify({"ok": True, "found": False})
    record = GstInvoiceService().get_record(int(found["invoice_id"]))
    return jsonify({"ok": True, "found": True, "record": record})


@bp.route("/payment-received", methods=["POST"], strict_slashes=False)
@bp_alias.route("/payment-received", methods=["POST"], strict_slashes=False)
@login_required
def mark_payment_received():
    """Source Payment Received Yes/No. Sale invoice grid follows this."""
    payload = request.get_json(silent=True) or {}
    bill_no = (payload.get("bill_no") or "").strip()
    paid = str(payload.get("payment_received") or "").strip().lower() in {"1", "true", "yes", "on"}
    if not bill_no:
        return jsonify({"ok": False, "error": "Bill number is required."}), 400
    try:
        GstInvoiceService().mark_source_payment_received(bill_no, paid)
        return jsonify({"ok": True, "payment_received": paid})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/generate-bill/invoice/delete", methods=["POST"], strict_slashes=False)
@bp_alias.route("/generate-bill/invoice/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def delete_generated_bill_invoices():
    """Permanently delete sale invoices created from this bill number."""
    payload = request.get_json(silent=True) or {}
    bill_no = (payload.get("bill_no") or "").strip()
    if not bill_no:
        return jsonify({"ok": False, "error": "Bill number is required."}), 400
    try:
        count = GstInvoiceService().delete_invoices_for_bill(bill_no)
        noun = "invoice" if count == 1 else "invoices"
        return jsonify(
            {
                "ok": True,
                "deleted": count,
                "message": f"Permanently deleted {count} related {noun}.",
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/generate-bill", methods=["GET"], strict_slashes=False)
@bp_alias.route("/generate-bill", methods=["GET"], strict_slashes=False)
@login_required
def generate_bill_page():
    """Compact Misc sales-invoice bill popup (9in × 4in window)."""
    company = GstInvoiceService.company_profile()
    states = [
        {
            "name": " ".join(part.capitalize() for part in name.split()),
            "code": code,
        }
        for name, code in sorted(STATE_CODES.items(), key=lambda item: item[0])
    ]
    return render_template(
        "others/misc_generate_bill.html",
        page_title="Generate Bill",
        company=company,
        states=states,
        tax_periods=tax_period_options(),
        default_tax_period=default_tax_period(),
        preview_pdf_url=url_for("accounting_invoice.api_preview_pdf"),
        create_url=url_for("accounting_invoice.api_create_invoice"),
        update_url=url_for("accounting_invoice.api_update_invoice", invoice_id=0),
        customer_url=url_for("accounting_invoice.api_customer_detail", customer_id=0),
        lookup_url=url_for("miscellaneous.generate_bill_invoice"),
        delete_url=url_for("accounting_invoice.api_delete_invoice", invoice_id=0),
        upi_banks=upi_bank_choices(),
    )


@bp.route("/next-bill-no", methods=["GET"], strict_slashes=False)
@bp_alias.route("/next-bill-no", methods=["GET"], strict_slashes=False)
@login_required
def next_bill_no():
    work_date_raw = (request.args.get("work_date") or "").strip()
    try:
        work_date = date.fromisoformat(work_date_raw[:10])
    except ValueError:
        return jsonify({"ok": False, "error": "Valid work date is required."}), 400
    bill_no = OthersIncomeExpenseService().next_bill_no(work_date, ledger_kind=FORCE_KIND)
    return jsonify({"ok": True, "bill_no": bill_no})


@bp.route("/customers/search", methods=["GET"], strict_slashes=False)
@bp_alias.route("/customers/search", methods=["GET"], strict_slashes=False)
@login_required
def customer_search():
    query = (request.args.get("q") or request.args.get("query") or "").strip()
    rows = OthersIncomeExpenseService().search_customers(query)
    return jsonify({"ok": True, "rows": rows})


@bp.route("/customers", methods=["POST"], strict_slashes=False)
@bp_alias.route("/customers", methods=["POST"], strict_slashes=False)
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
@bp_alias.route("/records/<int:entry_id>", methods=["GET"], strict_slashes=False)
@login_required
def record(entry_id: int):
    try:
        data = OthersIncomeExpenseService().get_entry(entry_id)
        if (data.get("ledger_kind") or "") != FORCE_KIND:
            return jsonify({"ok": False, "error": "Record is not a Miscellaneous entry."}), 404
        return jsonify({"ok": True, "record": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/records/<int:entry_id>/delete", methods=["POST"], strict_slashes=False)
@bp_alias.route("/records/<int:entry_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def delete_record(entry_id: int):
    try:
        service = OthersIncomeExpenseService()
        row = service.entry_repo.get_by_id(entry_id)
        if row is None:
            return jsonify({"ok": False, "error": "Income / expense record not found."}), 404
        existing = service._entry_dict(row)
        if (existing.get("ledger_kind") or "") != FORCE_KIND:
            return jsonify({"ok": False, "error": "Record is not a Miscellaneous entry."}), 404
        message = service.delete_entry(entry_id)
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
