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
from app.modules.communication.services import CommunicationService
from app.modules.crm.customer360_service import Customer360Service
from app.modules.crm.followup_service import CrmFollowUpService
from app.modules.crm.lead_service import CrmLeadService
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
    stats = CrmLeadService().dashboard_stats()
    unread_msgs = CommunicationService().unread_message_count()
    unread_notif = NotificationService().unread_count(_uid())
    tasks = CrmTaskService().list_tasks(status="Pending", page=1)
    followups = CrmFollowUpService().list_followups(status="Pending", page=1)
    return render_template(
        "crm/dashboard.html",
        page_title="CRM Dashboard",
        breadcrumb=_menu("/crm/dashboard"),
        stats=stats,
        unread_msgs=unread_msgs,
        unread_notif=unread_notif,
        pending_tasks=tasks.get("total", 0),
        pending_followups=followups.get("total", 0),
        poll_seconds=current_app.config.get("NOTIFICATION_POLL_SECONDS", 15),
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
    return render_template(
        "crm/inbox.html",
        page_title="Communication Center",
        breadcrumb=_menu("/crm/inbox"),
        poll_seconds=current_app.config.get("NOTIFICATION_POLL_SECONDS", 15),
        api={
            "list": url_for("crm_api.conversations_list"),
            "detail": url_for("crm_api.conversation_detail", conversation_id=0),
            "messages": url_for("crm_api.conversation_messages", conversation_id=0),
            "reply": url_for("crm_api.conversation_reply", conversation_id=0),
            "update": url_for("crm_api.conversation_update", conversation_id=0),
        },
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


@crm_api_bp.route("/conversations", methods=["GET"])
@login_required
def conversations_list():
    data = CommunicationService().list_conversations(
        status=request.args.get("status"),
        priority=request.args.get("priority"),
        search=request.args.get("search"),
        page=int(request.args.get("page") or 1),
    )
    for row in data.get("rows", []):
        mobile = row.get("WhatsAppNumber") or row.get("MobileNumber") or row.get("LeadMobile")
        row["wa_url"] = wa_me_url(mobile)
    return jsonify({"ok": True, **data})


@crm_api_bp.route("/conversations/<int:conversation_id>", methods=["GET"])
@login_required
def conversation_detail(conversation_id: int):
    row = CommunicationService().get_conversation(conversation_id)
    if not row:
        return jsonify({"ok": False, "error": "Not found"}), 404
    CommunicationService().mark_read(conversation_id)
    mobile = row.get("WhatsAppNumber") or row.get("MobileNumber") or row.get("LeadMobile")
    row["wa_url"] = wa_me_url(mobile)
    timeline = TimelineService().list_events(
        customer_id=row.get("CustomerID"),
        lead_id=row.get("LeadID"),
        page_size=20,
    )
    return jsonify({"ok": True, "conversation": row, "timeline": timeline.get("rows", [])})


@crm_api_bp.route("/conversations/<int:conversation_id>/messages", methods=["GET"])
@login_required
def conversation_messages(conversation_id: int):
    return jsonify({"ok": True, "rows": CommunicationService().list_messages(conversation_id)})


@crm_api_bp.route("/conversations/<int:conversation_id>/reply", methods=["POST"])
@login_required
def conversation_reply(conversation_id: int):
    payload = request.get_json(silent=True) or {}
    body = (payload.get("body") or "").strip()
    if not body:
        return jsonify({"ok": False, "error": "Message body required"}), 400
    channel = payload.get("channel") or "Internal"
    is_note = bool(payload.get("is_internal_note"))
    msg_id = CommunicationService().add_message(
        conversation_id,
        body=body,
        channel=channel,
        direction="Internal" if is_note else "Outbound",
        is_internal_note=is_note,
        user_id=_uid(),
        user_name=_uname(),
        bump_unread=False,
    )
    TimelineService().add_event(
        event_type="InternalNote" if is_note else "MessageSent",
        title="Internal note" if is_note else f"{channel} message sent",
        description=body[:500],
        customer_id=(CommunicationService().get_conversation(conversation_id) or {}).get("CustomerID"),
        lead_id=(CommunicationService().get_conversation(conversation_id) or {}).get("LeadID"),
        entity_type="CrmMessage",
        entity_id=msg_id,
        user_id=_uid(),
        user_name=_uname(),
    )
    return jsonify({"ok": True, "message_id": msg_id})


@crm_api_bp.route("/conversations/<int:conversation_id>", methods=["PATCH"])
@login_required
def conversation_update(conversation_id: int):
    payload = request.get_json(silent=True) or {}
    CommunicationService().update_conversation(
        conversation_id,
        status=payload.get("status"),
        priority=payload.get("priority"),
        assigned_user_id=payload.get("assigned_user_id"),
        assign_set="assigned_user_id" in payload,
    )
    return jsonify({"ok": True})


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
# Notifications + global search
# ---------------------------------------------------------------------------


@notification_api_bp.route("/unread", methods=["GET"])
@login_required
def notifications_unread():
    svc = NotificationService()
    uid = _uid()
    return jsonify(
        {
            "ok": True,
            "unread_count": svc.unread_count(uid),
            "rows": svc.list_for_user(uid, unread_only=False, page=1, page_size=8).get("rows", []),
            "unread_messages": CommunicationService().unread_message_count(),
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
