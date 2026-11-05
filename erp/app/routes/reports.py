from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.services.menu_service import MenuService
from app.services.report_service import ReportFilters, ReportService

bp = Blueprint("reports", __name__, url_prefix="/reports")
_SUMMARY_MENU_ENSURED = False


def ensure_summary_menu() -> None:
    """Ensure Summary is shown in the same Reports submenu as Daily Collection."""
    global _SUMMARY_MENU_ENSURED
    if _SUMMARY_MENU_ENSURED:
        return

    from sqlalchemy import text

    from app.extensions import db

    reports_id = db.session.execute(
        text(
            """
            SELECT TOP 1 r.MenuID
            FROM dbo.MenuMaster r
            WHERE r.MenuName IN (N'Reports', N'Reports and Analysis', N'Reports & Analysis')
              AND ISNULL(r.IsActive, 1) = 1
            ORDER BY CASE WHEN EXISTS (
                         SELECT 1 FROM dbo.MenuMaster c
                         WHERE c.ParentMenuID = r.MenuID
                           AND c.MenuName = N'Daily Collection'
                           AND ISNULL(c.IsActive, 1) = 1
                     ) THEN 0
                     WHEN r.ParentMenuID IS NOT NULL THEN 1
                     WHEN r.MenuURL = N'/accounting/reports' THEN 2
                     ELSE 3 END,
                     r.MenuID
            """
        )
    ).scalar()
    if reports_id:
        db.session.execute(
            text(
                """
                IF EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/reports/summary')
                    UPDATE dbo.MenuMaster
                    SET ParentMenuID = :parent_id,
                        MenuName = N'Summary', MenuIcon = N'bi-search',
                        DisplayOrder = 0,
                        Description = N'Search ledgers and view date-wise linked details',
                        IsActive = 1
                    WHERE MenuURL = N'/reports/summary';
                ELSE
                    INSERT INTO dbo.MenuMaster
                        (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                         Description, IsActive, RoleName)
                    VALUES
                        (:parent_id, N'Summary', N'bi-search', N'/reports/summary', 0,
                         N'Search ledgers and view date-wise linked details', 1, NULL);
                """
            ),
            {"parent_id": int(reports_id)},
        )
        db.session.commit()
    _SUMMARY_MENU_ENSURED = True


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

    if report_key == "summary":
        from app.services.ledger_report_service import LedgerReportService

        today = date.today()
        return render_template(
            "reports/summary.html",
            page_title="Summary",
            breadcrumb=menu_service.get_breadcrumb("/reports/summary", session.get("role")),
            today=today.isoformat(),
            fy_start=LedgerReportService._fy_start(today).isoformat(),
        )

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


@bp.route("/api/summary-reference", methods=["GET"], strict_slashes=False)
@login_required
def summary_reference():
    search = (request.args.get("search") or "").strip()
    if not search:
        return jsonify({"ok": False, "error": "Enter an invoice, bill, customer, or item reference."}), 400
    try:
        date_from = date.fromisoformat(request.args["date_from"][:10]) if request.args.get("date_from") else None
        date_to = date.fromisoformat(request.args["date_to"][:10]) if request.args.get("date_to") else None
        return jsonify({"ok": True, **ReportService().summary_reference(search, date_from, date_to)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        from app.extensions import db

        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/summary-date", methods=["GET"], strict_slashes=False)
@login_required
def summary_date():
    raw_date = (request.args.get("date") or "").strip()
    if not raw_date:
        return jsonify({"ok": False, "error": "Choose a date first."}), 400
    try:
        txn_date = date.fromisoformat(raw_date[:10])
        return jsonify({"ok": True, **ReportService().summary_datewise(txn_date)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        from app.extensions import db

        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 500
