from datetime import date

from flask import Blueprint, jsonify, render_template, request, session

from app.decorators import login_required, require_delete_reauth
from app.services.menu_service import MenuService
from app.services.others_bank_cash_service import OthersBankCashService
from app.services.purpose_master_service import PurposeMasterService

bp = Blueprint("others_bank_cash", __name__, url_prefix="/others/bank-cash-transactions")

MENU_PATH = "/others/bank-cash-transactions"


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
def index():
    service = OthersBankCashService()
    menu_service = MenuService()
    try:
        purposes = PurposeMasterService().list_records(active_only=True)
    except Exception:
        purposes = []
    return render_template(
        "others/bank_cash_transactions.html",
        page_title="Other Bank/Cash Transactions",
        breadcrumb=menu_service.get_breadcrumb(MENU_PATH, session.get("role")),
        default_date=date.today().isoformat(),
        accounts=service.list_accounts(),
        purposes=purposes or [],
        next_voucher=service.next_voucher_no(),
        load_entry_id=request.args.get("load_entry", type=int),
    )


@bp.route("/save", methods=["POST"], strict_slashes=False)
@login_required
def save_record():
    service = OthersBankCashService()
    try:
        created_by = OthersBankCashService.actor_login_email(
            user_id=session.get("user_id"),
            fallback=session.get("user_name", "System"),
        )
        result = service.save_entry(
            request.form,
            created_by=created_by,
        )
        return jsonify(
            {
                "ok": True,
                "message": result.message,
                "entry_id": result.entry_id,
                "voucher_no": result.voucher_no,
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to save entry: {exc}"}), 500


@bp.route("/grid", methods=["GET"], strict_slashes=False)
@login_required
def grid():
    return jsonify({"ok": True, "rows": OthersBankCashService().list_entries()})


@bp.route("/accounts", methods=["GET"], strict_slashes=False)
@login_required
def accounts():
    return jsonify({"ok": True, "rows": OthersBankCashService().list_accounts()})


@bp.route("/next-voucher", methods=["GET"], strict_slashes=False)
@login_required
def next_voucher():
    work_date = (request.args.get("work_date") or "").strip() or None
    try:
        voucher = OthersBankCashService().next_voucher_no(work_date)
        return jsonify({"ok": True, "voucher_no": voucher})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/entry/<int:entry_id>", methods=["GET"], strict_slashes=False)
@login_required
def get_record(entry_id: int):
    try:
        record = OthersBankCashService().get_entry(entry_id)
        return jsonify({"ok": True, "record": record})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to load entry: {exc}"}), 500


@bp.route("/delete/<int:entry_id>", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def delete_record(entry_id: int):
    try:
        message = OthersBankCashService().delete_entry(entry_id)
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to delete: {exc}"}), 500
