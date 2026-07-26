from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.services.menu_service import MenuService
from app.services.report_service import ReportFilters, ReportService

bp = Blueprint("reports", __name__, url_prefix="/reports")


def _parse_filters() -> ReportFilters:
    today = date.today()
    start = request.args.get("start_date") or request.form.get("start_date") or today.replace(day=1).isoformat()
    end = request.args.get("end_date") or request.form.get("end_date") or today.isoformat()
    customer_id = request.args.get("customer_id") or request.form.get("customer_id")
    work_type = request.args.get("work_type") or request.form.get("work_type")
    bank_name = request.args.get("bank_name") or request.form.get("bank_name")

    return ReportFilters(
        start_date=date.fromisoformat(str(start)[:10]),
        end_date=date.fromisoformat(str(end)[:10]),
        customer_id=int(customer_id) if customer_id else None,
        work_type=work_type or None,
        bank_name=bank_name or None,
    )


@bp.route("/")
@login_required
def index():
    menu_service = MenuService()
    report_service = ReportService()
    return render_template(
        "reports/index.html",
        page_title="Reports",
        breadcrumb=menu_service.get_breadcrumb("/reports", session.get("role")),
        reports=report_service.list_reports(),
    )


@bp.route("/<report_key>", methods=["GET", "POST"])
@login_required
def show(report_key: str):
    menu_service = MenuService()
    report_service = ReportService()

    if report_key not in report_service.REPORTS:
        flash("Report not found.", "danger")
        return render_template(
            "reports/index.html",
            page_title="Reports",
            breadcrumb=menu_service.get_breadcrumb("/reports", session.get("role")),
            reports=report_service.list_reports(),
        )

    filters = _parse_filters()

    if report_key == "stamp-collection" and request.method == "POST":
        action = (request.form.get("action") or "").strip()
        if action == "save_opening":
            try:
                opening_balance = Decimal(str(request.form.get("opening_balance") or "0").strip())
                opening_balance_date_raw = (request.form.get("opening_balance_date") or "").strip()
                if not opening_balance_date_raw:
                    raise ValueError("Opening balance date is required.")
                opening_balance_date = date.fromisoformat(opening_balance_date_raw[:10])
                report_service.save_shcil_opening_balance(
                    opening_balance=opening_balance,
                    opening_balance_date=opening_balance_date,
                    updated_by=session.get("username") or session.get("user") or "system",
                )
                flash("SHCIL opening balance saved successfully.", "success")
            except (InvalidOperation, ValueError) as exc:
                flash(str(exc), "danger")
            return redirect(
                url_for(
                    "reports.show",
                    report_key=report_key,
                    start_date=filters.start_date.isoformat(),
                    end_date=filters.end_date.isoformat(),
                )
            )

    try:
        result = report_service.run(report_key, filters)
    except Exception as exc:
        flash(str(exc), "danger")
        return render_template(
            "reports/index.html",
            page_title="Reports",
            breadcrumb=menu_service.get_breadcrumb("/reports", session.get("role")),
            reports=report_service.list_reports(),
        )

    template_name = "reports/stamp_collection.html" if report_key == "stamp-collection" else "reports/view.html"
    return render_template(
        template_name,
        page_title=result["title"],
        breadcrumb=menu_service.get_breadcrumb("/reports", session.get("role")),
        report_key=report_key,
        result=result,
        filters=filters,
    )
