from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from flask import Blueprint, current_app, jsonify, render_template, request, session

from app.decorators import login_required, require_delete_reauth
from app.services.dashboard_service import DashboardService
from app.services.menu_service import MenuService
from app.whats_new import list_whats_new

bp = Blueprint("dashboard", __name__)


@bp.route("/health")
def health():
    from flask import current_app, jsonify as _jsonify

    return _jsonify({"status": "ok", "app": current_app.config["APP_NAME"]})


def _parse_date(raw: str | None) -> date | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _resolve_period(dashboard_service: DashboardService) -> tuple[date, date, str]:
    today = date.today()
    preset = (request.args.get("period") or "").strip().lower()
    if preset in {"prev_fy", "previous_fy", "pfy"}:
        preset = "prev_fy"
    date_from = _parse_date(request.args.get("from") or request.args.get("date_from"))
    date_to = _parse_date(request.args.get("to") or request.args.get("date_to"))

    legacy_date = _parse_date(request.args.get("date"))
    if legacy_date and date_from is None and date_to is None and not preset:
        date_from = legacy_date
        date_to = legacy_date

    if preset == "month":
        date_from, date_to = dashboard_service.month_bounds(today)
    elif preset in {"last7", "last_7", "7d"}:
        date_from = today - timedelta(days=6)
        date_to = today
        preset = "last7"
    elif preset in {"last30", "last_30", "30d"}:
        date_from = today - timedelta(days=29)
        date_to = today
        preset = "last30"
    elif preset == "fy":
        date_from, date_to = dashboard_service.fiscal_year_bounds(today)
        if date_to > today:
            date_to = today
    elif preset == "prev_fy":
        current_fy_from, _ = dashboard_service.fiscal_year_bounds(today)
        prev_ref = date(current_fy_from.year - 1, 4, 1)
        date_from, date_to = dashboard_service.fiscal_year_bounds(prev_ref)
    elif preset == "today" or (date_from is None and date_to is None):
        date_from = today
        date_to = today
    else:
        date_from = date_from or today
        date_to = date_to or today

    if date_from > date_to:
        date_from, date_to = date_to, date_from

    period_preset = preset or (
        "custom" if (request.args.get("from") or request.args.get("to")) else
        ("today" if date_from == today and date_to == today else "custom")
    )
    return date_from, date_to, period_preset


@bp.route("/")
@bp.route("/dashboard")
@login_required
def index():
    menu_service = MenuService()
    dashboard_service = DashboardService()
    today = date.today()
    date_from, date_to, period_preset = _resolve_period(dashboard_service)

    metrics = dashboard_service.get_metrics(date_from, date_to)
    bank_closing_hover = dashboard_service.get_bank_closing_hover(as_of=date_to)
    bank_account_closings = bank_closing_hover["accounts"]
    bank_closing_manual = bank_closing_hover["manual"]
    bank_asset_closings = [row for row in bank_account_closings if not row.credit_normal]
    bank_liability_closings = [row for row in bank_account_closings if row.credit_normal]
    bank_asset_closing_total = sum(
        (row.closing_balance for row in bank_asset_closings), Decimal("0")
    )
    bank_liability_closing_total = sum(
        (row.closing_balance for row in bank_liability_closings), Decimal("0")
    )
    today_activity = dashboard_service.get_today_activity_summary(today)
    recent = dashboard_service.recent_daily_transactions()
    fy_from, fy_to = dashboard_service.fiscal_year_bounds(today)
    month_from, month_to = dashboard_service.month_bounds(today)
    month_end = date(today.year, today.month, monthrange(today.year, today.month)[1])
    prev_fy_from, prev_fy_to = dashboard_service.fiscal_year_bounds(date(fy_from.year - 1, 4, 1))

    # Date inputs stay blank unless user is on a custom from/to range.
    show_input_dates = period_preset == "custom" and bool(
        request.args.get("from") or request.args.get("to") or request.args.get("date_from") or request.args.get("date_to")
    )

    integration_health_alerts = []
    system_health_alerts = []
    try:
        from app.utils.roles import has_admin_role
        from app.modules.settings.integration_health_service import IntegrationHealthService
        from app.modules.system_health.service import SystemHealthService

        if has_admin_role(session.get("role")):
            integration_health_alerts = IntegrationHealthService().login_alerts()[:5]
            system_health_alerts = [
                a
                for a in SystemHealthService()._alert_payload()
                if str(a.get("severity") or "").lower() in {"critical", "error", "high"}
            ][:5]
    except Exception:
        integration_health_alerts = []
        system_health_alerts = []

    return render_template(
        "dashboard/index.html",
        page_title="Dashboard",
        breadcrumb=menu_service.get_breadcrumb("/dashboard", session.get("role")),
        metrics=metrics,
        bank_account_closings=bank_account_closings,
        bank_asset_closings=bank_asset_closings,
        bank_liability_closings=bank_liability_closings,
        bank_asset_closing_total=bank_asset_closing_total,
        bank_liability_closing_total=bank_liability_closing_total,
        bank_closing_manual=bank_closing_manual,
        today_activity=today_activity,
        recent=recent,
        date_from=date_from,
        date_to=date_to,
        input_date_from=date_from.isoformat() if show_input_dates else "",
        input_date_to=date_to.isoformat() if show_input_dates else "",
        system_date=today,
        period_preset=period_preset,
        month_from=month_from,
        month_to=month_to,
        month_end=month_end,
        fy_from=fy_from,
        fy_to=min(fy_to, today),
        prev_fy_from=prev_fy_from,
        prev_fy_to=prev_fy_to,
        whats_new=list_whats_new(limit=6),
        integration_health_alerts=integration_health_alerts,
        system_health_alerts=system_health_alerts,
    )


@bp.route("/dashboard/api/analytics")
@login_required
def analytics():
    service = DashboardService()
    date_from = _parse_date(request.args.get("from"))
    date_to = _parse_date(request.args.get("to"))
    try:
        data = service.get_analytics(date_from=date_from, date_to=date_to)
        return jsonify({"ok": True, **data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        current_app.logger.exception("Dashboard analytics failed")
        return jsonify({"ok": False, "error": "Unable to load analytics."}), 500


@bp.route("/dashboard/api/metric-details")
@login_required
def metric_details():
    service = DashboardService()
    metric_key = (request.args.get("metric") or "").strip()
    date_from = _parse_date(request.args.get("from"))
    date_to = _parse_date(request.args.get("to"))
    try:
        data = service.get_metric_details(metric_key, date_from=date_from, date_to=date_to)
        return jsonify({"ok": True, **data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/dashboard/api/today-activity-details")
@login_required
def today_activity_details():
    service = DashboardService()
    metric_key = (request.args.get("metric") or "").strip()
    account_raw = (request.args.get("account_id") or "").strip()
    account_id = None
    if account_raw:
        try:
            account_id = int(account_raw)
        except ValueError:
            return jsonify({"ok": False, "error": "Invalid bank account."}), 400
    try:
        data = service.get_today_activity_details(metric_key, account_id=account_id)
        return jsonify({"ok": True, **data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/dashboard/api/manual-entries", methods=["POST"])
@login_required
def manual_entry_create():
    service = DashboardService()
    payload = request.get_json(silent=True) or request.form
    try:
        result = service.add_manual_entry(
            metric_key=payload.get("metric_key") or payload.get("metric"),
            entry_date=_parse_date(payload.get("entry_date") or payload.get("EntryDate")),
            amount=payload.get("amount") or payload.get("Amount"),
            description=payload.get("description") or payload.get("Description"),
            created_by=session.get("user_name") or session.get("role") or "System",
        )
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/dashboard/api/manual-entries/<int:entry_id>", methods=["POST"])
@login_required
def manual_entry_update(entry_id: int):
    service = DashboardService()
    payload = request.get_json(silent=True) or request.form
    try:
        result = service.update_manual_entry(
            entry_id,
            entry_date=_parse_date(payload.get("entry_date") or payload.get("EntryDate")),
            amount=payload.get("amount") or payload.get("Amount"),
            description=payload.get("description") or payload.get("Description"),
        )
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/dashboard/api/manual-entries/<int:entry_id>/delete", methods=["POST"])
@login_required
@require_delete_reauth
def manual_entry_delete(entry_id: int):
    service = DashboardService()
    try:
        result = service.delete_manual_entry(entry_id)
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/dashboard/api/source/ecourt/<int:sale_id>/delete", methods=["POST"])
@login_required
@require_delete_reauth
def ecourt_source_delete(sale_id: int):
    """Roll back an e-Court sale shown on dashboard cash/bank closing grids."""
    service = DashboardService()
    try:
        result = service.delete_ecourt_source_sale(sale_id)
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to delete e-Court sale: {exc}"}), 500
