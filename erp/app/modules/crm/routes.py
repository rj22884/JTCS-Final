"""CRM blueprints — pages and JSON APIs."""

from __future__ import annotations

from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.decorators import login_required
from app.modules.ai.providers import AiDraftService
from app.modules.calendar.services import CalendarService
from app.modules.communication.ai_chatbot_stub import AiChatbotStub
from app.modules.communication.broadcast_stub import BroadcastStub
from app.modules.communication.call_log_service import CallLogService
from app.modules.communication.customer_link_service import CustomerLinkService
from app.modules.communication.email_channel_service import EmailChannelService
from app.modules.communication.label_service import LabelService
from app.modules.communication.meta_whatsapp_service import MetaWhatsAppService
from app.modules.communication.services import CommunicationService
from app.modules.communication.sms_provider import SmsGatewayProvider
from app.modules.communication.template_service import TemplateService
from app.modules.communication.webhook_service import WhatsAppWebhookService
from app.modules.communication.whatsapp_provider import get_whatsapp_provider, is_cloud_api_configured
from app.modules.crm.customer360_service import Customer360Service
from app.modules.crm.followup_service import CrmFollowUpService
from app.modules.crm.lead_service import CrmLeadService
from app.modules.crm.opportunity_stub import OpportunityStub
from app.modules.crm.permissions import require_crm_capability, user_has_capability
from app.modules.crm.task_service import CrmTaskService
from app.modules.crm.whatsapp import wa_me_url
from app.modules.documents.services import DocumentService
from app.modules.notification.services import NotificationService
from app.modules.reports.services import CrmReportService
from app.modules.shared.audit_service import AuditService
from app.modules.shared.search_service import GlobalSearchService
from app.modules.shared.timeline_service import TimelineService
from app.modules.workflow.services import WorkflowService
from app.services.menu_service import MenuService

crm_bp = Blueprint("crm", __name__, url_prefix="/crm")
crm_api_bp = Blueprint("crm_api", __name__, url_prefix="/api/crm")
public_intake_bp = Blueprint("public_intake", __name__, url_prefix="/api/public")
search_api_bp = Blueprint("search_api", __name__, url_prefix="/api")
notification_api_bp = Blueprint("notification_api", __name__, url_prefix="/api/notifications")


def _uid():
    return session.get("user_id")


def _uname():
    return session.get("user_name")


def _menu(path: str):
    return MenuService().get_breadcrumb(path, session.get("role"))


def _parse_dt(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if "T" in text and len(text) > 19 else text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid date/time: {value}")


def _entity_id(result, key: str) -> int:
    if isinstance(result, dict):
        return int(result.get(key) or result.get(key.replace("_", "")) or 0)
    return int(result or 0)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@crm_bp.route("/dashboard", strict_slashes=False)
@login_required
def dashboard():
    empty_comm = {
        "today_messages": 0,
        "unread_messages": 0,
        "pending_replies": 0,
        "resolved_today": 0,
        "open_conversations": 0,
        "today_calls": 0,
        "today_emails": 0,
        "website_enquiries": 0,
        "ai_conversations": 0,
        "failed_messages": 0,
        "total_customers": 0,
        "avg_response_minutes": None,
        "customer_satisfaction": None,
        "recent_activities": [],
    }
    try:
        lead_stats = CrmLeadService().dashboard_stats()
    except Exception:
        lead_stats = {}
    try:
        comm_stats = CommunicationService().dashboard_stats()
    except Exception:
        current_app.logger.exception("Communication dashboard_stats failed")
        comm_stats = empty_comm
    try:
        unread_msgs = CommunicationService().unread_message_count()
    except Exception:
        unread_msgs = 0
    try:
        unread_notif = NotificationService().unread_count(_uid())
    except Exception:
        unread_notif = 0
    try:
        tasks = CrmTaskService().list_tasks(status="Pending", page=1)
    except Exception:
        tasks = {"total": 0}
    try:
        followups = CrmFollowUpService().list_followups(status="Pending", page=1)
    except Exception:
        followups = {"total": 0}
    return render_template(
        "crm/dashboard.html",
        page_title="Communication Center Dashboard",
        breadcrumb=_menu("/crm/dashboard"),
        stats=lead_stats,
        comm_stats=comm_stats,
        unread_msgs=unread_msgs,
        unread_notif=unread_notif,
        pending_tasks=tasks.get("total", 0),
        pending_followups=followups.get("total", 0),
        poll_seconds=current_app.config.get("NOTIFICATION_POLL_SECONDS", 15),
        api={"dashboard_stats": url_for("crm_api.dashboard_stats")},
    )


@crm_bp.route("/leads", strict_slashes=False)
@login_required
def leads_page():
    return render_template(
        "crm/leads.html",
        page_title="CRM Leads",
        breadcrumb=_menu("/crm/leads"),
        api={
            "list": url_for("crm_api.leads_list"),
            "create": url_for("crm_api.leads_create"),
            "convert": url_for("crm_api.leads_convert", lead_id=0),
            "assign": url_for("crm_api.leads_assign", lead_id=0),
        },
    )


@crm_bp.route("/leads/<int:lead_id>", strict_slashes=False)
@login_required
def lead_detail(lead_id: int):
    lead = CrmLeadService().get_lead(lead_id)
    if not lead:
        flash(f"Lead #{lead_id} was not found.", "warning")
        return redirect(url_for("crm.leads_page"))
    return render_template(
        "crm/lead_detail.html",
        page_title=f"Lead #{lead_id}",
        breadcrumb=_menu("/crm/leads"),
        lead=lead,
        api={
            "convert": url_for("crm_api.leads_convert", lead_id=lead_id),
            "assign": url_for("crm_api.leads_assign", lead_id=lead_id),
        },
    )


@crm_bp.route("/customer-360", strict_slashes=False)
@crm_bp.route("/customer-360/<int:customer_id>", strict_slashes=False)
@login_required
def customer_360(customer_id: int | None = None):
    data = None
    if customer_id:
        try:
            data = Customer360Service().get(customer_id)
        except ValueError:
            data = None
    return render_template(
        "crm/customer_360.html",
        page_title="Customer 360",
        breadcrumb=_menu("/crm/customer-360"),
        customer_id=customer_id,
        data=data,
        search_api=url_for("search_api.global_search"),
        wa_url=wa_me_url((data or {}).get("profile", {}).get("whatsapp_number") or (data or {}).get("profile", {}).get("mobile_number")) if data else None,
    )


@crm_bp.route("/inbox", strict_slashes=False)
@login_required
def inbox_page():
    channel = (request.args.get("channel") or "").strip()
    return render_template(
        "crm/inbox.html",
        page_title="Communication Center",
        breadcrumb=_menu("/crm/inbox"),
        poll_seconds=current_app.config.get("NOTIFICATION_POLL_SECONDS", 15),
        initial_channel=channel,
        initial_conversation_id=request.args.get("c") or "",
        test_mode=not is_cloud_api_configured(),
        api={
            "list": url_for("crm_api.conversations_list"),
            "detail": url_for("crm_api.conversation_detail", conversation_id=0),
            "messages": url_for("crm_api.conversation_messages", conversation_id=0),
            "reply": url_for("crm_api.conversation_reply", conversation_id=0),
            "update": url_for("crm_api.conversation_update", conversation_id=0),
            "attachments": url_for("crm_api.conversation_attachments", conversation_id=0),
            "quick_replies": url_for("crm_api.quick_replies_list"),
            "templates": url_for("crm_api.templates_list"),
            "email_sync": url_for("crm_api.email_sync"),
            "staff": url_for("crm_api.staff_list"),
            "labels": url_for("crm_api.labels_list"),
            "simulate": url_for("crm_api.whatsapp_simulate_inbound"),
            "link": url_for("crm_api.conversation_link", conversation_id=0),
            "conv_labels": url_for("crm_api.conversation_labels", conversation_id=0),
            "tasks": url_for("crm_api.tasks_create"),
            "followups": url_for("crm_api.followups_create"),
            "customer360": url_for("crm.customer_360"),
            "simulate_status": url_for("crm_api.whatsapp_simulate_status"),
        },
    )


@crm_bp.route("/whatsapp-templates", strict_slashes=False)
@login_required
def whatsapp_templates_page():
    return render_template(
        "crm/whatsapp_templates.html",
        page_title="WhatsApp Templates",
        breadcrumb=_menu("/crm/whatsapp-templates"),
        api={
            "list": url_for("crm_api.templates_list"),
            "create": url_for("crm_api.templates_create"),
            "quick_replies": url_for("crm_api.quick_replies_list"),
            "quick_create": url_for("crm_api.quick_replies_create"),
        },
    )


@crm_bp.route("/call-logs", strict_slashes=False)
@login_required
def call_logs_page():
    return render_template(
        "crm/call_logs.html",
        page_title="Call Logs",
        breadcrumb=_menu("/crm/call-logs"),
        api={
            "list": url_for("crm_api.call_logs_list"),
            "create": url_for("crm_api.call_logs_create"),
        },
    )


@crm_bp.route("/opportunities", strict_slashes=False)
@login_required
def opportunities_page():
    return render_template(
        "crm/opportunities.html",
        page_title="Opportunities",
        breadcrumb=_menu("/crm/opportunities"),
    )


@crm_bp.route("/followups", strict_slashes=False)
@login_required
def followups_page():
    return render_template(
        "crm/followups.html",
        page_title="CRM Follow-ups",
        breadcrumb=_menu("/crm/followups"),
        api={
            "list": url_for("crm_api.followups_list"),
            "create": url_for("crm_api.followups_create"),
            "complete": url_for("crm_api.followups_complete", followup_id=0),
        },
    )


@crm_bp.route("/tasks", strict_slashes=False)
@login_required
def tasks_page():
    return render_template(
        "crm/tasks.html",
        page_title="CRM Tasks",
        breadcrumb=_menu("/crm/tasks"),
        api={
            "list": url_for("crm_api.tasks_list"),
            "create": url_for("crm_api.tasks_create"),
            "complete": url_for("crm_api.tasks_complete", task_id=0),
            "update": url_for("crm_api.tasks_update", task_id=0),
        },
    )


@crm_bp.route("/timeline", strict_slashes=False)
@login_required
def timeline_page():
    return render_template(
        "crm/timeline.html",
        page_title="Activity Timeline",
        breadcrumb=_menu("/crm/timeline"),
        api=url_for("crm_api.timeline_list"),
    )


@crm_bp.route("/documents", strict_slashes=False)
@login_required
def documents_page():
    return render_template(
        "crm/documents.html",
        page_title="Document Vault",
        breadcrumb=_menu("/crm/documents"),
        folders=DocumentService.FOLDERS,
        api={
            "list": url_for("crm_api.documents_list"),
            "upload": url_for("crm_api.documents_upload"),
            "versions": url_for("crm_api.documents_versions", document_id=0),
            "delete": url_for("crm_api.documents_delete", document_id=0),
        },
    )


@crm_bp.route("/notifications", strict_slashes=False)
@login_required
def notifications_page():
    return render_template(
        "crm/notifications.html",
        page_title="Notifications",
        breadcrumb=_menu("/crm/notifications"),
        poll_seconds=current_app.config.get("NOTIFICATION_POLL_SECONDS", 15),
    )


@crm_bp.route("/workflow", strict_slashes=False)
@login_required
def workflow_page():
    defs = WorkflowService().list_definitions()
    instances = WorkflowService().list_instances(page=1)
    return render_template(
        "crm/workflow.html",
        page_title="CRM Workflow",
        breadcrumb=_menu("/crm/workflow"),
        definitions=defs,
        instances=instances.get("rows", []),
        api={
            "start": url_for("crm_api.workflow_start"),
            "advance": url_for("crm_api.workflow_advance", instance_id=0),
            "list": url_for("crm_api.workflow_list"),
        },
    )


@crm_bp.route("/calendar", strict_slashes=False)
@login_required
def calendar_page():
    return render_template(
        "crm/calendar.html",
        page_title="CRM Calendar",
        breadcrumb=_menu("/crm/calendar"),
        api=url_for("crm_api.calendar_events"),
    )


@crm_bp.route("/analytics", strict_slashes=False)
@login_required
def analytics_page():
    reports = CrmReportService()
    return render_template(
        "crm/analytics.html",
        page_title="CRM Analytics",
        breadcrumb=_menu("/crm/analytics"),
        lead_summary=reports.lead_summary(),
        conversion=reports.conversion_stats(),
        pending_followups=reports.pending_followups(),
        pending_documents=reports.pending_documents_count(),
        staff=reports.staff_performance(),
        daily=reports.daily_activity(days=14),
    )


@crm_bp.route("/audit", strict_slashes=False)
@login_required
def audit_page():
    return render_template(
        "crm/audit.html",
        page_title="Audit Log",
        breadcrumb=_menu("/crm/analytics"),
        api=url_for("crm_api.audit_list"),
    )


# ---------------------------------------------------------------------------
# CRM JSON APIs
# ---------------------------------------------------------------------------


@crm_api_bp.route("/leads", methods=["GET"])
@login_required
def leads_list():
    data = CrmLeadService().list_leads(
        status=request.args.get("status"),
        search=request.args.get("search"),
        page=int(request.args.get("page") or 1),
    )
    return jsonify({"ok": True, **data})


@crm_api_bp.route("/leads", methods=["POST"])
@login_required
def leads_create():
    payload = request.get_json(silent=True) or {}
    try:
        result = CrmLeadService().create_lead(
            source=payload.get("source") or "Internal",
            request_type=payload.get("request_type") or "Contact",
            full_name=payload.get("full_name") or "",
            mobile=payload.get("mobile"),
            email=payload.get("email"),
            business_name=payload.get("business_name"),
            message=payload.get("message"),
            priority=payload.get("priority") or "Normal",
            user_id=_uid(),
            user_name=_uname(),
        )
        return jsonify({"ok": True, "lead_id": _entity_id(result, "lead_id"), "result": result}), 201
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@crm_api_bp.route("/leads/<int:lead_id>/convert", methods=["POST"])
@login_required
def leads_convert(lead_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = CrmLeadService().convert_to_customer(
            lead_id,
            pan=payload.get("pan"),
            user_id=_uid(),
            user_name=_uname(),
        )
        return jsonify({"ok": True, "customer_id": _entity_id(result, "customer_id"), "result": result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@crm_api_bp.route("/leads/<int:lead_id>/assign", methods=["POST"])
@login_required
def leads_assign(lead_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        CrmLeadService().assign_lead(
            lead_id,
            assigned_user_id=int(payload["assigned_user_id"]),
            user_id=_uid(),
            user_name=_uname(),
        )
        return jsonify({"ok": True})
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@crm_api_bp.route("/dashboard/stats", methods=["GET"])
@login_required
def dashboard_stats():
    return jsonify({"ok": True, **CommunicationService().dashboard_stats()})


@crm_api_bp.route("/conversations", methods=["GET"])
@login_required
def conversations_list():
    date_preset = (request.args.get("date") or "").strip().lower()
    date_from = date_to = None
    if date_preset:
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        start_today = datetime(now.year, now.month, now.day)
        if date_preset == "today":
            date_from, date_to = start_today, start_today + timedelta(days=1)
        elif date_preset == "yesterday":
            date_from, date_to = start_today - timedelta(days=1), start_today
        elif date_preset == "week":
            date_from, date_to = start_today - timedelta(days=7), start_today + timedelta(days=1)
        elif date_preset == "month":
            date_from, date_to = start_today - timedelta(days=30), start_today + timedelta(days=1)

    bucket = (request.args.get("bucket") or "").strip().lower()
    data = CommunicationService().list_conversations(
        status=request.args.get("status"),
        priority=None if bucket == "high" else request.args.get("priority"),
        search=request.args.get("search"),
        channel=request.args.get("channel") or None,
        unread_only=request.args.get("unread") == "1" or bucket == "unread",
        archived=request.args.get("archived") == "1",
        pinned_only=request.args.get("pinned") == "1",
        starred_only=request.args.get("starred") == "1",
        has_attachments=request.args.get("attachments") == "1",
        date_from=date_from,
        date_to=date_to,
        page=int(request.args.get("page") or 1),
        assigned_to_me=_uid() if bucket == "mine" else None,
        unknown_only=bucket == "unknown",
        pending_reply=bucket == "pending",
        high_priority=bucket == "high",
        label_id=int(request.args["label_id"]) if request.args.get("label_id") else None,
        message_search=request.args.get("q") or None,
    )
    for row in data.get("rows", []):
        mobile = (
            row.get("ContactMobile")
            or row.get("WhatsAppNumber")
            or row.get("MobileNumber")
            or row.get("LeadMobile")
        )
        row["wa_url"] = wa_me_url(mobile)
    return jsonify({"ok": True, **data})


@crm_api_bp.route("/conversations/<int:conversation_id>", methods=["GET"])
@login_required
def conversation_detail(conversation_id: int):
    row = CommunicationService().get_conversation(conversation_id)
    if not row:
        return jsonify({"ok": False, "error": "Not found"}), 404
    CommunicationService().mark_read(conversation_id)
    row["UnreadCount"] = 0
    mobile = row.get("WhatsAppNumber") or row.get("MobileNumber") or row.get("LeadMobile")
    row["wa_url"] = wa_me_url(mobile or row.get("ContactMobile"))
    row["labels"] = LabelService().conversation_labels(conversation_id)
    link = CustomerLinkService()
    candidates = link.find_customers_by_mobile(row.get("ContactMobile") or mobile)
    hint = link.find_whatsapp_mapping(
        row.get("ContactMobile") or mobile,
        conversation_id=conversation_id,
    )
    row["match_candidates"] = candidates
    row["match_count"] = len(candidates)
    row["suggested_customer_id"] = (
        int(row["CustomerID"])
        if row.get("CustomerID")
        else (hint.get("customer_id") if hint else None)
    )
    timeline = TimelineService().list_events(
        customer_id=row.get("CustomerID"),
        lead_id=row.get("LeadID"),
        page_size=20,
    )
    return jsonify({"ok": True, "conversation": row, "timeline": timeline.get("rows", [])})


@crm_api_bp.route("/conversations/<int:conversation_id>/messages", methods=["GET"])
@login_required
def conversation_messages(conversation_id: int):
    if not CommunicationService().get_conversation(conversation_id):
        return jsonify({"ok": False, "error": "Conversation not found"}), 404
    return jsonify({"ok": True, "rows": CommunicationService().list_messages(conversation_id)})


@crm_api_bp.route("/conversations/<int:conversation_id>/reply", methods=["POST"])
@login_required
@require_crm_capability("crm.reply")
def conversation_reply(conversation_id: int):
    payload = request.get_json(silent=True) or {}
    body = (payload.get("body") or "").strip()
    if not body:
        return jsonify({"ok": False, "error": "Message body required"}), 400
    conv = CommunicationService().get_conversation(conversation_id)
    if not conv:
        return jsonify({"ok": False, "error": "Conversation not found"}), 404

    channel = payload.get("channel") or conv.get("Channel") or "Internal"
    is_note = bool(payload.get("is_internal_note"))
    delivery_status = None
    external_id = None
    error_detail = None
    send_result = None
    is_test = False

    vars_map = {
        "customer_name": conv.get("CustomerName") or conv.get("LeadName") or "",
        "firm_name": "Joshi Tax Consultancy & Services",
        "financial_year": "",
        "due_date": "",
        "service_name": "",
        "amount": "",
    }
    if payload.get("template_vars") and isinstance(payload.get("template_vars"), dict):
        vars_map.update({str(k): str(v or "") for k, v in payload["template_vars"].items()})
    body = TemplateService.interpolate(body, vars_map)

    if not is_note and channel == "WhatsApp":
        mobile = (
            conv.get("ContactMobile")
            or conv.get("WhatsAppNumber")
            or conv.get("MobileNumber")
            or conv.get("LeadMobile")
        )
        provider = get_whatsapp_provider()
        send_result = provider.send_message(mobile or "", body)
        if send_result.get("ok"):
            external_id = send_result.get("external_message_id")
            delivery_status = "Sent"
            is_test = bool(send_result.get("is_test"))
        else:
            delivery_status = "Failed"
            error_detail = send_result.get("error")
            is_test = bool(send_result.get("is_test"))
            # Still store the outbound attempt for auditability
    elif not is_note and channel == "Email":
        to_email = conv.get("ContactEmail") or conv.get("EmailID") or conv.get("LeadEmail")
        send_result = EmailChannelService().send_reply(
            to_email=to_email or "",
            body=body,
            subject=f"Re: {conv.get('Subject') or 'JTCS'}",
            conversation_id=conversation_id,
        )
        if send_result.get("ok"):
            external_id = send_result.get("external_message_id")
            delivery_status = "Sent"
        else:
            delivery_status = "Failed"
            error_detail = send_result.get("error")
    elif not is_note and channel == "SMS":
        send_result = SmsGatewayProvider().send_sms(
            conv.get("ContactMobile") or conv.get("MobileNumber") or "",
            body,
        )
        delivery_status = "Failed"
        error_detail = send_result.get("error")

    msg_id = CommunicationService().add_message(
        conversation_id,
        body=body,
        channel=channel,
        direction="Internal" if is_note else "Outbound",
        is_internal_note=is_note,
        external_message_id=external_id,
        delivery_status=delivery_status,
        error_detail=error_detail,
        media_type="text",
        is_test=is_test,
        user_id=_uid(),
        user_name=_uname(),
        bump_unread=False,
    )
    TimelineService().add_event(
        event_type="InternalNote" if is_note else "MessageSent",
        title="Internal note" if is_note else (
            "WhatsApp – Employee Reply" if channel == "WhatsApp" else f"{channel} message sent"
        ) + (" (TEST)" if is_test else ""),
        description=body[:500],
        customer_id=conv.get("CustomerID"),
        lead_id=conv.get("LeadID"),
        entity_type="CrmMessage",
        entity_id=msg_id,
        user_id=_uid(),
        user_name=_uname(),
    )
    resp = {"ok": True, "message_id": msg_id, "delivery_status": delivery_status, "is_test": is_test}
    if send_result and not send_result.get("ok") and channel in {"WhatsApp", "Email"}:
        resp["warning"] = send_result.get("error")
    AuditService().log(
        action_name="MessageSent",
        entity_type="CrmMessage",
        entity_id=msg_id,
        new_value={"channel": channel, "is_test": is_test, "status": delivery_status},
        user_id=_uid(),
        user_name=_uname(),
    )
    return jsonify(resp)


@crm_api_bp.route("/conversations/<int:conversation_id>/attachments", methods=["POST"])
@login_required
@require_crm_capability("crm.reply")
def conversation_attachments(conversation_id: int):
    """Upload attachment and optionally send via WhatsApp Cloud API."""
    from pathlib import Path
    import mimetypes
    import uuid

    conv = CommunicationService().get_conversation(conversation_id)
    if not conv:
        return jsonify({"ok": False, "error": "Conversation not found"}), 404
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "file required"}), 400
    channel = request.form.get("channel") or conv.get("Channel") or "WhatsApp"
    caption = (request.form.get("caption") or request.form.get("body") or "").strip()
    folder = Path(current_app.config.get("CRM_WHATSAPP_MEDIA_FOLDER")
                  or (Path(current_app.config["UPLOAD_FOLDER"]) / "whatsapp_media"))
    folder.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in f.filename)[:180]
    dest = folder / f"{uuid.uuid4().hex}_{safe}"
    f.save(dest)
    mime = mimetypes.guess_type(str(dest))[0] or f.mimetype or "application/octet-stream"
    if mime.startswith("image/"):
        media_type = "image"
    elif mime.startswith("audio/"):
        media_type = "audio"
    elif mime.startswith("video/"):
        media_type = "video"
    else:
        media_type = "document"
    try:
        rel = dest.relative_to(Path(current_app.config["UPLOAD_FOLDER"]))
        store_path = f"uploads/{rel.as_posix()}"
    except ValueError:
        store_path = str(dest)

    external_id = None
    delivery_status = None
    error_detail = None
    if channel == "WhatsApp":
        mobile = (
            conv.get("ContactMobile")
            or conv.get("WhatsAppNumber")
            or conv.get("MobileNumber")
            or conv.get("LeadMobile")
        )
        provider = get_whatsapp_provider()
        # Prefer media upload + id when Cloud API
        send_result = {"ok": False, "error": "Provider cannot send media"}
        try:
            from app.modules.communication.whatsapp_provider import WhatsAppCloudApiProvider
            from app.modules.settings.services import IntegrationSettingsService

            if isinstance(provider, WhatsAppCloudApiProvider):
                cfg = IntegrationSettingsService().get_provider_config_decrypted("whatsapp_meta")
                client = provider._client()
                uploaded = client.upload_media(cfg["phone_number_id"], dest, mime_type=mime)
                media_id = uploaded.get("id")
                send_result = provider.send_media(
                    mobile or "",
                    media_type=media_type,
                    media_id=media_id,
                    caption=caption or None,
                    filename=safe,
                )
        except Exception as exc:
            send_result = {"ok": False, "error": str(exc)}
        if send_result.get("ok"):
            external_id = send_result.get("external_message_id")
            delivery_status = "Sent"
        else:
            delivery_status = "Failed"
            error_detail = send_result.get("error")

    msg_id = CommunicationService().add_message(
        conversation_id,
        body=caption or f"[{media_type}] {safe}",
        channel=channel,
        direction="Outbound",
        attachment_path=store_path,
        attachment_name=safe,
        attachment_mime_type=mime,
        attachment_size_bytes=dest.stat().st_size,
        media_type=media_type,
        external_message_id=external_id,
        delivery_status=delivery_status,
        error_detail=error_detail,
        user_id=_uid(),
        user_name=_uname(),
        bump_unread=False,
    )
    return jsonify(
        {
            "ok": True,
            "message_id": msg_id,
            "attachment_path": store_path,
            "delivery_status": delivery_status,
            "warning": error_detail,
        }
    )


@crm_api_bp.route("/conversations/<int:conversation_id>", methods=["PATCH"])
@login_required
def conversation_update(conversation_id: int):
    if not CommunicationService().get_conversation(conversation_id):
        return jsonify({"ok": False, "error": "Conversation not found"}), 404
    payload = request.get_json(silent=True) or {}
    if payload.get("status") == "Closed" and not user_has_capability("crm.close"):
        return jsonify({"ok": False, "error": "Permission denied"}), 403
    if "assigned_user_id" in payload and not user_has_capability("crm.assign"):
        return jsonify({"ok": False, "error": "Permission denied"}), 403
    CommunicationService().update_conversation(
        conversation_id,
        status=payload.get("status"),
        priority=payload.get("priority"),
        assigned_user_id=payload.get("assigned_user_id"),
        assign_set="assigned_user_id" in payload,
        assigned_by_user_id=_uid(),
        assigned_by_name=_uname(),
        is_pinned=payload.get("is_pinned") if "is_pinned" in payload else None,
        is_archived=payload.get("is_archived") if "is_archived" in payload else None,
        is_starred=payload.get("is_starred") if "is_starred" in payload else None,
    )
    return jsonify({"ok": True})


@crm_api_bp.route("/staff", methods=["GET"])
@login_required
def staff_list():
    from sqlalchemy import text
    from app.extensions import db

    rows = db.session.execute(
        text(
            """
            SELECT UserID, FullName, Role
            FROM dbo.Users
            WHERE ISNULL(IsActive, 1) = 1
              AND UserStatus IN (N'Active', N'Approved')
            ORDER BY FullName
            """
        )
    ).mappings().all()
    return jsonify({"ok": True, "rows": [dict(r) for r in rows]})


@crm_api_bp.route("/labels", methods=["GET"])
@login_required
def labels_list():
    return jsonify({"ok": True, "rows": LabelService().list_labels()})


@crm_api_bp.route("/conversations/<int:conversation_id>/labels", methods=["GET", "POST"])
@login_required
def conversation_labels(conversation_id: int):
    if request.method == "GET":
        return jsonify({"ok": True, "rows": LabelService().conversation_labels(conversation_id)})
    payload = request.get_json(silent=True) or {}
    ids = payload.get("label_ids") or []
    rows = LabelService().set_labels(conversation_id, ids)
    AuditService().log(
        action_name="ConversationLabelsUpdated",
        entity_type="CrmConversation",
        entity_id=conversation_id,
        new_value={"label_ids": ids},
        user_id=_uid(),
        user_name=_uname(),
    )
    return jsonify({"ok": True, "rows": rows})


@crm_api_bp.route("/conversations/<int:conversation_id>/link", methods=["POST"])
@login_required
def conversation_link(conversation_id: int):
    """Link a WhatsApp conversation: customer, lead, keep unlinked, or ignore."""
    conv = CommunicationService().get_conversation(conversation_id)
    if not conv:
        return jsonify({"ok": False, "error": "Conversation not found"}), 404
    payload = request.get_json(silent=True) or {}
    action = (payload.get("action") or "").strip().lower()
    mobile = conv.get("ContactMobile") or conv.get("LeadMobile") or ""
    display = (
        (payload.get("full_name") or "").strip()
        or conv.get("CustomerName")
        or conv.get("Subject")
        or f"WhatsApp {str(mobile)[-10:]}"
    )
    link = CustomerLinkService()
    previous_customer_id = int(conv["CustomerID"]) if conv.get("CustomerID") else None

    if action == "ignore":
        CommunicationService().update_conversation(
            conversation_id,
            status="Closed",
            match_status="Unknown",
            assigned_by_user_id=_uid(),
            assigned_by_name=_uname(),
        )
        AuditService().log(
            action_name="UnknownContactIgnored",
            entity_type="CrmConversation",
            entity_id=conversation_id,
            user_id=_uid(),
            user_name=_uname(),
        )
        return jsonify({"ok": True, "action": "ignore"})

    if action == "keep_unlinked":
        CommunicationService().update_conversation(
            conversation_id,
            customer_id=None,
            customer_set=True,
            match_status="Unlinked",
            subject="Unlinked WhatsApp Contact",
            assigned_by_user_id=_uid(),
            assigned_by_name=_uname(),
        )
        AuditService().log(
            action_name="WhatsAppKeepUnlinked",
            entity_type="CrmConversation",
            entity_id=conversation_id,
            old_value=previous_customer_id,
            user_id=_uid(),
            user_name=_uname(),
        )
        return jsonify({"ok": True, "action": "keep_unlinked"})

    if action == "create_lead":
        result = CrmLeadService().create_lead(
            source="WhatsApp",
            request_type="WhatsApp",
            full_name=display,
            mobile=mobile or None,
            message=conv.get("LastMessagePreview"),
            priority=conv.get("Priority") or "Normal",
            user_id=_uid(),
            user_name=_uname(),
        )
        lead_id = int(result.get("lead_id") or result.get("LeadID") or 0)
        CommunicationService().update_conversation(
            conversation_id,
            lead_id=lead_id,
            match_status="Linked",
            subject=display,
            assigned_by_user_id=_uid(),
            assigned_by_name=_uname(),
        )
        link.upsert_whatsapp_mapping(
            mobile,
            lead_id=lead_id,
            conversation_id=conversation_id,
            confirmed=True,
            user_id=_uid(),
            overwrite=True,
        )
        AuditService().log(
            action_name="LeadCreatedFromWhatsApp",
            entity_type="CrmLead",
            entity_id=lead_id,
            user_id=_uid(),
            user_name=_uname(),
        )
        return jsonify({"ok": True, "action": "create_lead", "lead_id": lead_id})

    if action in {"create_customer", "link_customer"}:
        customer_id = payload.get("customer_id")
        matches = link.find_customers_by_mobile(mobile) if mobile else []
        if action == "link_customer":
            if not customer_id:
                return jsonify(
                    {
                        "ok": False,
                        "error": "Select a customer to link. Multiple Customer Master records may share this mobile.",
                        "candidates": matches,
                    }
                ), 400
            customer_id = int(customer_id)
            if matches and not any(int(c["CustomerID"]) == customer_id for c in matches):
                return jsonify({"ok": False, "error": "Selected customer does not match this WhatsApp number."}), 400
        elif not customer_id:
            if len(matches) > 1:
                return jsonify(
                    {
                        "ok": False,
                        "error": "Multiple customers share this mobile. Select one to link.",
                        "ambiguous": True,
                        "candidates": matches,
                    }
                ), 409
            if len(matches) == 1:
                customer_id = int(matches[0]["CustomerID"])
            else:
                from app.repositories.customer_repository import CustomerRepository

                repo = CustomerRepository()
                digits = "".join(ch for ch in str(mobile or "") if ch.isdigit())
                mobile_10 = digits[-10:] if len(digits) >= 10 else digits
                record = repo.save_full(
                    {
                        "customer_group": CrmLeadService()._resolve_customer_group(),
                        "customer_type": "Individual",
                        "customer_name": display if display not in {"Unknown WhatsApp Contact", "Multiple Customers Found"} else f"WhatsApp {mobile_10}",
                        "mobile_number": mobile_10 or None,
                        "whatsapp_number": mobile_10 or mobile or None,
                        "customer_status": "Active",
                        "remarks": "Source: WhatsApp",
                    }
                )
                customer_id = int(record["customer_id"])
        else:
            customer_id = int(customer_id)

        selected = next((c for c in matches if int(c["CustomerID"]) == int(customer_id)), None)
        subject = (selected or {}).get("CustomerName") or display
        CommunicationService().update_conversation(
            conversation_id,
            customer_id=int(customer_id),
            customer_set=True,
            match_status="Linked",
            subject=subject,
            assigned_by_user_id=_uid(),
            assigned_by_name=_uname(),
        )
        link.upsert_whatsapp_mapping(
            mobile,
            customer_id=int(customer_id),
            conversation_id=conversation_id,
            confirmed=True,
            user_id=_uid(),
            overwrite=True,
        )
        TimelineService().reassign_conversation(
            conversation_id,
            customer_id=int(customer_id),
        )
        AuditService().log(
            action_name="CustomerLinkedFromWhatsApp" if previous_customer_id else "CustomerCreatedFromWhatsApp",
            entity_type="CustomerMaster",
            entity_id=int(customer_id),
            old_value=previous_customer_id,
            new_value=int(customer_id),
            user_id=_uid(),
            user_name=_uname(),
        )
        TimelineService().add_event(
            event_type="CustomerLinked",
            title="Customer linked from WhatsApp",
            customer_id=int(customer_id),
            entity_type="CrmConversation",
            entity_id=conversation_id,
            user_id=_uid(),
            user_name=_uname(),
        )
        return jsonify({"ok": True, "action": action, "customer_id": int(customer_id)})

    return jsonify(
        {
            "ok": False,
            "error": "Unknown action. Use create_lead, create_customer, link_customer, keep_unlinked, or ignore.",
        }
    ), 400


@crm_api_bp.route("/whatsapp/simulate-inbound", methods=["POST"])
@login_required
@require_crm_capability("crm.reply")
def whatsapp_simulate_inbound():
    payload = request.get_json(silent=True) or {}
    mobile = (payload.get("mobile") or "").strip()
    body = (payload.get("body") or "").strip()
    if not mobile or not body:
        return jsonify({"ok": False, "error": "mobile and body are required"}), 400
    external_id = (payload.get("external_message_id") or "").strip() or (
        f"TEST-IN-{mobile[-10:]}-{int(datetime.utcnow().timestamp())}"
    )
    result = WhatsAppWebhookService().ingest_inbound(
        mobile=mobile,
        body=body,
        display_name=(payload.get("display_name") or "").strip() or None,
        external_message_id=external_id,
        is_test=True,
    )
    return jsonify(result)


@crm_api_bp.route("/whatsapp/simulate-status", methods=["POST"])
@login_required
@require_crm_capability("crm.reply")
def whatsapp_simulate_status():
    payload = request.get_json(silent=True) or {}
    external_id = (payload.get("external_message_id") or "").strip()
    status = (payload.get("status") or "").strip()
    if not external_id or not status:
        return jsonify({"ok": False, "error": "external_message_id and status are required"}), 400
    ok = CommunicationService().update_delivery_status(
        external_message_id=external_id,
        status=status,
        error_detail=payload.get("error_detail"),
    )
    AuditService().log(
        action_name="MessageStatusChanged",
        entity_type="CrmMessage",
        new_value={"external_message_id": external_id, "status": status, "simulated": True},
        user_id=_uid(),
        user_name=_uname(),
    )
    return jsonify({"ok": ok})


@crm_api_bp.route("/whatsapp/test-mode", methods=["GET"])
@login_required
def whatsapp_test_mode():
    svc = MetaWhatsAppService()
    return jsonify(
        {
            "ok": True,
            "test_mode": svc.is_test_mode(),
            "configured": svc.is_configured(),
        }
    )


@crm_api_bp.route("/tasks", methods=["GET"])
@login_required
def tasks_list():
    return jsonify(
        {
            "ok": True,
            **CrmTaskService().list_tasks(
                status=request.args.get("status"),
                customer_id=int(request.args["customer_id"]) if request.args.get("customer_id") else None,
                page=int(request.args.get("page") or 1),
            ),
        }
    )


@crm_api_bp.route("/tasks", methods=["POST"])
@login_required
def tasks_create():
    payload = request.get_json(silent=True) or {}
    try:
        result = CrmTaskService().create_task(
            title=payload.get("title") or "",
            description=payload.get("description"),
            priority=payload.get("priority") or "Normal",
            deadline=_parse_dt(payload.get("deadline")),
            customer_id=payload.get("customer_id"),
            lead_id=payload.get("lead_id"),
            assigned_user_id=payload.get("assigned_user_id"),
            assigned_user_name=payload.get("assigned_user_name"),
            user_id=_uid(),
            user_name=_uname(),
            conversation_id=payload.get("conversation_id"),
            source=payload.get("source") or ("WhatsApp" if payload.get("conversation_id") else None),
        )
        return jsonify({"ok": True, "task_id": _entity_id(result, "TaskID") or _entity_id(result, "task_id"), "result": result}), 201
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@crm_api_bp.route("/tasks/<int:task_id>", methods=["PATCH"])
@login_required
def tasks_update(task_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        CrmTaskService().update_task(
            task_id,
            title=payload.get("title"),
            description=payload.get("description"),
            priority=payload.get("priority"),
            status=payload.get("status"),
            progress=payload.get("progress"),
            deadline=_parse_dt(payload.get("deadline")) if payload.get("deadline") else None,
            assigned_user_id=payload.get("assigned_user_id"),
            assigned_user_name=payload.get("assigned_user_name"),
            assign_set="assigned_user_id" in payload,
            user_id=_uid(),
            user_name=_uname(),
        )
        return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@crm_api_bp.route("/tasks/<int:task_id>/complete", methods=["POST"])
@login_required
def tasks_complete(task_id: int):
    try:
        CrmTaskService().complete_task(task_id, user_id=_uid(), user_name=_uname())
        return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@crm_api_bp.route("/followups", methods=["GET"])
@login_required
def followups_list():
    return jsonify(
        {
            "ok": True,
            **CrmFollowUpService().list_followups(
                status=request.args.get("status"),
                followup_type=request.args.get("followup_type"),
                due_filter=request.args.get("due_filter") or request.args.get("filter"),
                customer_id=int(request.args["customer_id"]) if request.args.get("customer_id") else None,
                page=int(request.args.get("page") or 1),
            ),
        }
    )


@crm_api_bp.route("/followups", methods=["POST"])
@login_required
def followups_create():
    payload = request.get_json(silent=True) or {}
    try:
        due_at = _parse_dt(payload.get("due_at"))
        if not due_at:
            raise ValueError("due_at is required")
        result = CrmFollowUpService().create_followup(
            followup_type=payload.get("followup_type") or "Reminder",
            due_at=due_at,
            subject=payload.get("subject"),
            notes=payload.get("notes"),
            priority=payload.get("priority") or "Normal",
            customer_id=payload.get("customer_id"),
            lead_id=payload.get("lead_id"),
            assigned_user_id=payload.get("assigned_user_id"),
            assigned_user_name=payload.get("assigned_user_name"),
            user_id=_uid(),
            user_name=_uname(),
            conversation_id=payload.get("conversation_id"),
        )
        return jsonify(
            {
                "ok": True,
                "followup_id": _entity_id(result, "FollowUpID") or _entity_id(result, "followup_id"),
                "result": result,
            }
        ), 201
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@crm_api_bp.route("/followups/<int:followup_id>/complete", methods=["POST"])
@login_required
def followups_complete(followup_id: int):
    try:
        CrmFollowUpService().complete_followup(followup_id, user_id=_uid(), user_name=_uname())
        return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@crm_api_bp.route("/timeline", methods=["GET"])
@login_required
def timeline_list():
    data = TimelineService().list_events(
        customer_id=int(request.args["customer_id"]) if request.args.get("customer_id") else None,
        lead_id=int(request.args["lead_id"]) if request.args.get("lead_id") else None,
        page=int(request.args.get("page") or 1),
        page_size=int(request.args.get("page_size") or 50),
    )
    return jsonify({"ok": True, **data})


@crm_api_bp.route("/documents", methods=["GET"])
@login_required
def documents_list():
    customer_id = request.args.get("customer_id")
    if not customer_id:
        return jsonify({"ok": False, "error": "customer_id required"}), 400
    rows = DocumentService().list_documents(
        customer_id=int(customer_id),
        folder_type=request.args.get("folder"),
    )
    return jsonify({"ok": True, "rows": rows})


@crm_api_bp.route("/documents/upload", methods=["POST"])
@login_required
def documents_upload():
    customer_id = request.form.get("customer_id")
    folder = request.form.get("folder_type") or "Others"
    title = request.form.get("title") or ""
    file = request.files.get("file")
    if not customer_id or not file:
        return jsonify({"ok": False, "error": "customer_id and file required"}), 400
    try:
        result = DocumentService().upload(
            customer_id=int(customer_id),
            folder_type=folder,
            title=title or file.filename,
            file=file,
            remarks=request.form.get("remarks"),
            user_id=_uid(),
            user_name=_uname(),
        )
        return jsonify(
            {
                "ok": True,
                "document_id": _entity_id(result, "DocumentID") or _entity_id(result, "document_id"),
                "result": result,
            }
        ), 201
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@crm_api_bp.route("/documents/<int:document_id>/versions", methods=["GET"])
@login_required
def documents_versions(document_id: int):
    return jsonify({"ok": True, "rows": DocumentService().list_versions(document_id)})


@crm_api_bp.route("/documents/<int:document_id>", methods=["DELETE"])
@login_required
def documents_delete(document_id: int):
    DocumentService().soft_delete(document_id, user_id=_uid(), user_name=_uname())
    return jsonify({"ok": True})


@crm_api_bp.route("/documents/<int:document_id>/download", methods=["GET"])
@login_required
def documents_download(document_id: int):
    from flask import abort, current_app, send_from_directory
    from pathlib import Path

    doc = DocumentService().get_document(document_id)
    if not doc or not doc.get("IsActive", True):
        abort(404)
    stored = (doc.get("StoredPath") or "").replace("\\", "/").lstrip("/")
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    full = (upload_root / stored).resolve()
    if not str(full).startswith(str(upload_root)) or not full.is_file():
        abort(404)
    return send_from_directory(
        full.parent,
        full.name,
        as_attachment=True,
        download_name=doc.get("FileName") or full.name,
    )


@crm_api_bp.route("/workflow/instances", methods=["GET"])
@login_required
def workflow_list():
    return jsonify({"ok": True, **WorkflowService().list_instances(page=int(request.args.get("page") or 1))})


@crm_api_bp.route("/workflow/start", methods=["POST"])
@login_required
def workflow_start():
    payload = request.get_json(silent=True) or {}
    try:
        result = WorkflowService().start_instance(
            definition_code=payload.get("definition_code") or "website_lead",
            customer_id=payload.get("customer_id"),
            lead_id=payload.get("lead_id"),
            user_id=_uid(),
        )
        return jsonify(
            {
                "ok": True,
                "instance_id": _entity_id(result, "InstanceID") or _entity_id(result, "instance_id"),
                "result": result,
            }
        ), 201
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@crm_api_bp.route("/workflow/<int:instance_id>/advance", methods=["POST"])
@login_required
def workflow_advance(instance_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        WorkflowService().advance_instance(
            instance_id,
            user_id=_uid(),
            notes=payload.get("notes"),
        )
        return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@crm_api_bp.route("/calendar/events", methods=["GET"])
@login_required
def calendar_events():
    try:
        rows = CalendarService().list_events(
            from_date=_parse_dt(request.args.get("from")),
            to_date=_parse_dt(request.args.get("to")),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "rows": rows})


@crm_api_bp.route("/customer-360/<int:customer_id>", methods=["GET"])
@login_required
def customer_360_api(customer_id: int):
    try:
        data = Customer360Service().get(customer_id)
        profile = data.get("profile") or {}
        data["wa_url"] = wa_me_url(profile.get("whatsapp_number") or profile.get("mobile_number"))
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@crm_api_bp.route("/audit", methods=["GET"])
@login_required
def audit_list():
    return jsonify(
        {
            "ok": True,
            **AuditService().list_logs(
                entity_type=request.args.get("entity_type"),
                entity_id=int(request.args["entity_id"]) if request.args.get("entity_id") else None,
                page=int(request.args.get("page") or 1),
            ),
        }
    )


@crm_api_bp.route("/ai/draft", methods=["POST"])
@login_required
def ai_draft():
    payload = request.get_json(silent=True) or {}
    context = payload.get("context")
    if isinstance(context, str):
        context = {"subject": context}
    result = AiDraftService().draft_reply(
        channel=payload.get("channel") or "Email",
        context=context if isinstance(context, dict) else {},
    )
    return jsonify(result)


# ---------------------------------------------------------------------------
# Quick replies / templates / call logs / email / Phase 2 stubs
# ---------------------------------------------------------------------------


@crm_api_bp.route("/quick-replies", methods=["GET"])
@login_required
def quick_replies_list():
    return jsonify(
        {
            "ok": True,
            "rows": TemplateService().list_quick_replies(channel=request.args.get("channel")),
        }
    )


@crm_api_bp.route("/quick-replies", methods=["POST"])
@login_required
@require_crm_capability("crm.templates")
def quick_replies_create():
    payload = request.get_json(silent=True) or {}
    try:
        qid = TemplateService().create_quick_reply(
            title=payload.get("title") or "",
            body=payload.get("body") or "",
            channel=payload.get("channel"),
            shortcut=payload.get("shortcut"),
            sort_order=int(payload.get("sort_order") or 0),
            user_id=_uid(),
        )
        return jsonify({"ok": True, "quick_reply_id": qid}), 201
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@crm_api_bp.route("/templates", methods=["GET"])
@login_required
def templates_list():
    return jsonify(
        {
            "ok": True,
            "rows": TemplateService().list_templates(channel=request.args.get("channel")),
        }
    )


@crm_api_bp.route("/templates", methods=["POST"])
@login_required
@require_crm_capability("crm.templates")
def templates_create():
    payload = request.get_json(silent=True) or {}
    try:
        tid = TemplateService().create_template(
            name=payload.get("name") or "",
            body=payload.get("body") or "",
            channel=payload.get("channel") or "WhatsApp",
            subject=payload.get("subject"),
            external_template_name=payload.get("external_template_name"),
            language_code=payload.get("language_code"),
            user_id=_uid(),
        )
        return jsonify({"ok": True, "template_id": tid}), 201
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@crm_api_bp.route("/call-logs", methods=["GET"])
@login_required
@require_crm_capability("crm.call_logs")
def call_logs_list():
    return jsonify(
        {
            "ok": True,
            **CallLogService().list_logs(
                customer_id=int(request.args["customer_id"]) if request.args.get("customer_id") else None,
                lead_id=int(request.args["lead_id"]) if request.args.get("lead_id") else None,
                page=int(request.args.get("page") or 1),
            ),
        }
    )


@crm_api_bp.route("/call-logs", methods=["POST"])
@login_required
@require_crm_capability("crm.call_logs")
def call_logs_create():
    payload = request.get_json(silent=True) or {}
    result = CallLogService().create(
        direction=payload.get("direction") or "Outgoing",
        call_status=payload.get("call_status") or "Completed",
        phone_number=payload.get("phone_number"),
        customer_id=payload.get("customer_id"),
        lead_id=payload.get("lead_id"),
        duration_seconds=payload.get("duration_seconds"),
        recording_url=payload.get("recording_url"),
        notes=payload.get("notes"),
        next_follow_up_at=_parse_dt(payload.get("next_follow_up_at")),
        called_at=_parse_dt(payload.get("called_at")),
        user_id=_uid(),
        user_name=_uname(),
    )
    return jsonify({"ok": True, **result}), 201


@crm_api_bp.route("/email/sync", methods=["POST"])
@login_required
@require_crm_capability("crm.email_sync")
def email_sync():
    limit = int((request.get_json(silent=True) or {}).get("limit") or request.args.get("limit") or 30)
    return jsonify(EmailChannelService().sync_inbox(limit=limit))


@crm_api_bp.route("/sms/send", methods=["POST"])
@login_required
def sms_send_stub():
    return jsonify(SmsGatewayProvider().send_sms("", ""))


@crm_api_bp.route("/broadcast", methods=["POST"])
@login_required
def broadcast_stub():
    return jsonify(BroadcastStub().create_broadcast())


@crm_api_bp.route("/schedule", methods=["POST"])
@login_required
def schedule_stub():
    return jsonify(BroadcastStub().schedule_message())


@crm_api_bp.route("/ai/suggest", methods=["POST"])
@login_required
def ai_suggest_stub():
    payload = request.get_json(silent=True) or {}
    return jsonify(
        AiChatbotStub().suggest_replies(
            int(payload.get("conversation_id") or 0),
            payload.get("last_message"),
        )
    )


@crm_api_bp.route("/opportunities", methods=["GET"])
@login_required
def opportunities_list_stub():
    return jsonify(OpportunityStub().list_opportunities())


@crm_api_bp.route("/export", methods=["POST"])
@login_required
def export_stub():
    return jsonify({"ok": False, "error": "Phase 2 — Export PDF/Excel not enabled"})


# ---------------------------------------------------------------------------
# Notifications + global search
# ---------------------------------------------------------------------------


@notification_api_bp.route("/unread", methods=["GET"])
@login_required
def notifications_unread():
    svc = NotificationService()
    uid = _uid()
    notif_count = svc.unread_count(uid)
    msg_count = CommunicationService().unread_message_count()
    return jsonify(
        {
            "ok": True,
            "unread_count": int(notif_count) + int(msg_count),
            "unread_notifications": int(notif_count),
            "rows": svc.list_for_user(uid, unread_only=False, page=1, page_size=8).get("rows", []),
            "unread_messages": int(msg_count),
        }
    )


@notification_api_bp.route("", methods=["GET"])
@login_required
def notifications_list():
    data = NotificationService().list_for_user(
        _uid(),
        include_archived=request.args.get("archived") == "1",
        unread_only=request.args.get("unread") == "1",
        page=int(request.args.get("page") or 1),
    )
    return jsonify({"ok": True, **data})


@notification_api_bp.route("/<int:notification_id>/read", methods=["POST"])
@login_required
def notifications_read(notification_id: int):
    NotificationService().mark_read(notification_id, _uid())
    return jsonify({"ok": True})


@notification_api_bp.route("/read-all", methods=["POST"])
@login_required
def notifications_read_all():
    NotificationService().mark_all_read(_uid())
    return jsonify({"ok": True})


@notification_api_bp.route("/<int:notification_id>/archive", methods=["POST"])
@login_required
def notifications_archive(notification_id: int):
    NotificationService().archive(notification_id, _uid())
    return jsonify({"ok": True})


@search_api_bp.route("/search", methods=["GET"])
@login_required
def global_search():
    return jsonify({"ok": True, **GlobalSearchService().search(request.args.get("q") or "")})


# ---------------------------------------------------------------------------
# Public website intake
# ---------------------------------------------------------------------------


@public_intake_bp.route("/intake", methods=["POST"])
def website_intake():
    expected = (current_app.config.get("WEBSITE_INTAKE_API_KEY") or "").strip()
    provided = (
        request.headers.get("X-API-Key")
        or request.headers.get("X-Website-Api-Key")
        or (request.get_json(silent=True) or {}).get("api_key")
        or ""
    ).strip()
    if not expected or provided != expected:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    request_type = (payload.get("request_type") or payload.get("type") or "Contact").strip()
    if request_type.lower() in ("consultation", "consultation request"):
        request_type = "Consultation"
    elif request_type.lower() in ("service", "service request"):
        request_type = "Service"
    else:
        request_type = "Contact"

    try:
        result = CrmLeadService().create_lead(
            source="Website",
            request_type=request_type,
            full_name=payload.get("full_name") or payload.get("name") or "",
            mobile=payload.get("mobile") or payload.get("phone"),
            email=payload.get("email"),
            business_name=payload.get("business_name") or payload.get("company"),
            message=payload.get("message") or payload.get("details"),
            priority=payload.get("priority") or "Normal",
            idempotency_key=payload.get("idempotency_key") or request.headers.get("Idempotency-Key"),
            user_name="Website",
        )
        lead_id = _entity_id(result, "lead_id")
        try:
            WorkflowService().start_instance(
                definition_code="website_lead",
                lead_id=lead_id,
                user_id=None,
            )
        except Exception:
            pass
        return jsonify({"ok": True, "lead_id": lead_id, "duplicate": bool((result or {}).get("duplicate"))}), 201
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
