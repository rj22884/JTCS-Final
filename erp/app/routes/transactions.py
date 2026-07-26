from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.repositories.transaction_repository import MasterRepository
from app.services.menu_service import MenuService
from app.services.transaction_service import TransactionService

bp = Blueprint("transactions", __name__, url_prefix="/transactions")


def _is_tds_return_filing(work_type: str, sub_work_type: str) -> bool:
    return (
        work_type.strip().upper() == "TDS"
        and sub_work_type.strip().lower() == "return filing"
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    master_repo = MasterRepository()
    txn_service = TransactionService()
    menu_service = MenuService()

    selected_work_type = (request.args.get("work_type") or "").strip()
    selected_sub_work_type = (request.args.get("sub_work_type") or "").strip()

    # TDS Return Filing uses Deductor Master UI — keep other work types on the daily form.
    if request.method == "GET" and _is_tds_return_filing(selected_work_type, selected_sub_work_type):
        deductors = txn_service.list_tds_deductors()
        return render_template(
            "transactions/tds_return_filing.html",
            page_title="",
            breadcrumb=[],
            selected_work_type=selected_work_type,
            selected_sub_work_type=selected_sub_work_type,
            deductors=deductors,
            customer_master_url=url_for("masters_customer.index"),
            return_register_url="/tds/register",
            delete_url_template=url_for("masters_customer.delete_record", customer_id=0),
        )

    if request.method == "POST":
        try:
            result = txn_service.save_daily_transaction(
                request.form,
                session.get("user_name", "System"),
            )
            flash(result.message, "success")
            return redirect(url_for("transactions.create"))
        except Exception as exc:
            flash(str(exc), "danger")

    if selected_work_type and selected_work_type not in txn_service.WORK_TYPES:
        flash(f"Unknown work type '{selected_work_type}'. Select a valid type.", "warning")
        selected_work_type = ""

    page_title = (
        f"{selected_work_type} Transaction"
        if selected_work_type
        else "Daily Transaction"
    )

    return render_template(
        "transactions/form.html",
        page_title=page_title,
        breadcrumb=menu_service.get_breadcrumb_for_work_type(
            selected_work_type or None,
            session.get("role"),
        ),
        work_types=txn_service.WORK_TYPES,
        selected_work_type=selected_work_type,
        selected_sub_work_type=selected_sub_work_type,
        default_date=date.today().isoformat(),
        payment_modes=master_repo.list_payment_modes(),
        customers=master_repo.list_customers(),
        mode="daily",
    )


@bp.route("/contra", methods=["GET", "POST"])
@login_required
def contra():
    master_repo = MasterRepository()
    txn_service = TransactionService()
    menu_service = MenuService()

    if request.method == "POST":
        try:
            result = txn_service.save_contra(
                request.form,
                session.get("user_name", "System"),
            )
            flash(f"{result.message} Reference: {result.contra_reference}", "success")
            return redirect(url_for("transactions.contra"))
        except Exception as exc:
            flash(str(exc), "danger")

    return render_template(
        "transactions/form.html",
        page_title="Contra Entry",
        breadcrumb=menu_service.get_breadcrumb("/transactions/contra", session.get("role")),
        default_date=date.today().isoformat(),
        payment_modes=master_repo.list_payment_modes(),
        mode="contra",
    )
