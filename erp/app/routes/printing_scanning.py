from datetime import date

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, require_delete_reauth
from app.repositories.transaction_repository import MasterRepository
from app.services.menu_service import MenuService
from app.services.printing_scan_service import PrintingScanService

income_bp = Blueprint("printing_scanning", __name__, url_prefix="/others/income")
expense_bp = Blueprint("printing_scan_expense", __name__, url_prefix="/others/expense")


def _render_activity(*, blueprint: str, ledger_kind: str, menu_path: str):
    service = PrintingScanService()
    master_repo = MasterRepository()
    menu_service = MenuService()

    if request.method == "POST":
        try:
            result = service.save_entry(
                request.form,
                created_by=session.get("user_name", "System"),
                ledger_kind=ledger_kind,
            )
            flash(result.message, "success")
            return redirect(url_for(f"{blueprint}.printing_scanning"))
        except ValueError as exc:
            flash(str(exc), "danger")
        except Exception as exc:
            flash(f"Unable to save entry: {exc}", "danger")

    work_types = (
        service.list_income_work_types()
        if ledger_kind == PrintingScanService.LEDGER_INCOME
        else service.list_expense_work_types()
    )

    return render_template(
        "others/printing_scanning_activity.html",
        page_title="Printing and Scanning",
        ledger_kind=ledger_kind,
        breadcrumb=menu_service.get_breadcrumb(menu_path, session.get("role")),
        default_date=date.today().isoformat(),
        payment_modes=master_repo.list_stamp_bank_payment_modes(),
        work_types=work_types,
        pscan_blueprint=blueprint,
        load_entry_id=request.args.get("load_entry", type=int),
    )


def _register_routes(bp: Blueprint, *, blueprint: str, ledger_kind: str, base_path: str) -> None:
    menu_path = f"{base_path}/printing-scanning"
    others_path = f"{base_path}/others"

    @bp.route("/printing-scanning", methods=["GET", "POST"], strict_slashes=False)
    @login_required
    def printing_scanning():
        return _render_activity(blueprint=blueprint, ledger_kind=ledger_kind, menu_path=menu_path)

    @bp.route("/printing-scanning/grid", methods=["GET"], strict_slashes=False)
    @login_required
    def printing_scanning_grid():
        service = PrintingScanService()
        return jsonify({"ok": True, "rows": service.list_entries(ledger_kind=ledger_kind)})

    @bp.route("/printing-scanning/next-bill-no", methods=["GET"], strict_slashes=False)
    @login_required
    def printing_scanning_next_bill_no():
        service = PrintingScanService()
        work_date_raw = (request.args.get("work_date") or "").strip()
        try:
            work_date = date.fromisoformat(work_date_raw[:10])
        except ValueError:
            return jsonify({"ok": False, "error": "Valid work date is required."}), 400
        return jsonify(
            {"ok": True, "bill_no": service.next_bill_no(work_date, ledger_kind=ledger_kind)}
        )

    @bp.route(
        "/printing-scanning/records/<int:printing_scan_id>",
        methods=["GET"],
        strict_slashes=False,
    )
    @login_required
    def printing_scanning_record(printing_scan_id: int):
        service = PrintingScanService()
        try:
            return jsonify({"ok": True, "record": service.get_entry(printing_scan_id)})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @bp.route(
        "/printing-scanning/records/<int:printing_scan_id>/delete",
        methods=["POST"],
        strict_slashes=False,
    )
    @login_required
    @require_delete_reauth
    def printing_scanning_delete(printing_scan_id: int):
        service = PrintingScanService()
        try:
            message = service.delete_entry(printing_scan_id)
            return jsonify({"ok": True, "message": message})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @bp.route("/printing-scanning/work-types", methods=["GET", "POST"], strict_slashes=False)
    @login_required
    def printing_scanning_work_types():
        service = PrintingScanService()
        if request.method == "GET":
            kind = (request.args.get("ledger_kind") or "").strip() or None
            return jsonify({"ok": True, "rows": service.list_work_master(ledger_kind=kind)})

        payload = request.get_json(silent=True) or request.form.to_dict()
        try:
            result = service.save_work_master(payload)
            return jsonify({"ok": True, **result})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @bp.route(
        "/printing-scanning/work-types/<int:work_id>",
        methods=["DELETE"],
        strict_slashes=False,
    )
    @login_required
    @require_delete_reauth
    def printing_scanning_work_type_delete(work_id: int):
        service = PrintingScanService()
        try:
            result = service.delete_work_master(work_id)
            return jsonify({"ok": True, **result})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @bp.route("/others", strict_slashes=False)
    @login_required
    def others_placeholder():
        menu_service = MenuService()
        section = "Income" if ledger_kind == PrintingScanService.LEDGER_INCOME else "Expense"
        template = (
            "others/income_others.html"
            if ledger_kind == PrintingScanService.LEDGER_INCOME
            else "others/expense_others.html"
        )
        return render_template(
            template,
            page_title="Others",
            breadcrumb=menu_service.get_breadcrumb(others_path, session.get("role")),
            section_label=section,
        )


_register_routes(
    income_bp,
    blueprint="printing_scanning",
    ledger_kind=PrintingScanService.LEDGER_INCOME,
    base_path="/others/income",
)


def _register_expense_routes(bp: Blueprint, *, blueprint: str, ledger_kind: str, base_path: str) -> None:
    """Expense activity only — same as income printing-scanning, Expense WorkMaster filter."""
    menu_path = f"{base_path}/printing-scanning"

    @bp.route("/printing-scanning", methods=["GET", "POST"], strict_slashes=False)
    @login_required
    def printing_scanning():
        return _render_activity(blueprint=blueprint, ledger_kind=ledger_kind, menu_path=menu_path)

    @bp.route("/printing-scanning/grid", methods=["GET"], strict_slashes=False)
    @login_required
    def printing_scanning_grid():
        service = PrintingScanService()
        return jsonify({"ok": True, "rows": service.list_entries(ledger_kind=ledger_kind)})

    @bp.route("/printing-scanning/next-bill-no", methods=["GET"], strict_slashes=False)
    @login_required
    def printing_scanning_next_bill_no():
        service = PrintingScanService()
        work_date_raw = (request.args.get("work_date") or "").strip()
        try:
            work_date = date.fromisoformat(work_date_raw[:10])
        except ValueError:
            return jsonify({"ok": False, "error": "Valid work date is required."}), 400
        return jsonify(
            {"ok": True, "bill_no": service.next_bill_no(work_date, ledger_kind=ledger_kind)}
        )

    @bp.route(
        "/printing-scanning/records/<int:printing_scan_id>",
        methods=["GET"],
        strict_slashes=False,
    )
    @login_required
    def printing_scanning_record(printing_scan_id: int):
        service = PrintingScanService()
        try:
            return jsonify({"ok": True, "record": service.get_entry(printing_scan_id)})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @bp.route(
        "/printing-scanning/records/<int:printing_scan_id>/delete",
        methods=["POST"],
        strict_slashes=False,
    )
    @login_required
    @require_delete_reauth
    def printing_scanning_delete(printing_scan_id: int):
        service = PrintingScanService()
        try:
            message = service.delete_entry(printing_scan_id)
            return jsonify({"ok": True, "message": message})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @bp.route("/printing-scanning/work-types", methods=["GET", "POST"], strict_slashes=False)
    @login_required
    def printing_scanning_work_types():
        service = PrintingScanService()
        if request.method == "GET":
            return jsonify({"ok": True, "rows": service.list_work_master(ledger_kind=ledger_kind)})

        payload = request.get_json(silent=True) or request.form.to_dict()
        payload["ledger_kind"] = ledger_kind
        try:
            result = service.save_work_master(payload)
            return jsonify({"ok": True, **result})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @bp.route(
        "/printing-scanning/work-types/<int:work_id>",
        methods=["DELETE"],
        strict_slashes=False,
    )
    @login_required
    @require_delete_reauth
    def printing_scanning_work_type_delete(work_id: int):
        service = PrintingScanService()
        try:
            result = service.delete_work_master(work_id)
            return jsonify({"ok": True, **result})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500


_register_expense_routes(
    expense_bp,
    blueprint="printing_scan_expense",
    ledger_kind=PrintingScanService.LEDGER_EXPENSE,
    base_path="/others/expense",
)

# Backward-compatible alias for existing imports
bp = income_bp
