from calendar import monthrange
from datetime import date

from flask import Blueprint, jsonify, render_template, request, session

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

    crm_widgets = {
        "today_leads": 0,
        "open_leads": 0,
        "unread_notifications": 0,
        "unread_messages": 0,
        "pending_tasks": 0,
        "pending_followups": 0,
    }
    try:
        from app.modules.communication.services import CommunicationService
        from app.modules.crm.followup_service import CrmFollowUpService
        from app.modules.crm.lead_service import CrmLeadService
        from app.modules.crm.task_service import CrmTaskService
        from app.modules.notification.services import NotificationService

        lead_stats = CrmLeadService().dashboard_stats()
        crm_widgets["today_leads"] = int(lead_stats.get("today_leads") or 0)
        crm_widgets["open_leads"] = int(lead_stats.get("open_leads") or 0)
        crm_widgets["unread_notifications"] = NotificationService().unread_count(session.get("user_id"))
        crm_widgets["unread_messages"] = CommunicationService().unread_message_count()
        crm_widgets["pending_tasks"] = int(CrmTaskService().list_tasks(status="Pending", page=1).get("total") or 0)
        crm_widgets["pending_followups"] = int(
            CrmFollowUpService().list_followups(status="Pending", page=1).get("total") or 0
        )
    except Exception:
        pass

    return render_template(
        "dashboard/index.html",
        page_title="Dashboard",
        breadcrumb=menu_service.get_breadcrumb("/dashboard", session.get("role")),
        metrics=metrics,
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
        crm_widgets=crm_widgets,
    )


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
