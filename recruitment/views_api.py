"""Public JSON APIs for anonymous click / page tracking."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from recruitment.applications import find_duplicate_fields
from recruitment.audit import write_audit
from recruitment.extensions import csrf, db, limiter
from recruitment.candidate_status import GENERIC_VERIFY_ERROR, public_status_payload, verify_application
from recruitment.job_window import is_job_application_open, job_window_payload
from recruitment.models import Job
from recruitment.tracking import request_context

api_bp = Blueprint("api", __name__, url_prefix="/api/recruitment")

EVENT_MAP = {
    "cta-click": ("SALES_EXECUTIVE_CTA_CLICK", "Sales Executive CTA clicked"),
    "job-view": ("JOB_PAGE_VIEW", "Job page viewed"),
    "apply-started": ("APPLICATION_STARTED", "Application started"),
    "closed-attempt": ("APPLICATION_ATTEMPTED_AFTER_DEADLINE", "Application attempted after deadline"),
}


@api_bp.post("/events/<event_key>")
@csrf.exempt
@limiter.limit("60 per minute")
def record_event(event_key: str):
    mapped = EVENT_MAP.get(event_key)
    if not mapped:
        return jsonify({"ok": False, "error": "Unknown event"}), 404
    payload = request.get_json(silent=True) or {}
    if event_key == "cta-click":
        job = Job.query.filter_by(slug="sales-executive").first()
        if job is not None and not is_job_application_open(job):
            mapped = EVENT_MAP["closed-attempt"]
    ctx = request_context(request, payload)
    write_audit(
        mapped[0],
        mapped[1],
        payload=payload,
        details=str(payload.get("details") or "")[:500] or None,
        visitor_id=ctx["visitor_id"],
        session_id=ctx["session_id"],
    )
    db.session.commit()
    return jsonify({
        "ok": True,
        "visitor_id": ctx["visitor_id"],
        "session_id": ctx["session_id"],
        "event": mapped[0],
    })


@api_bp.get("/jobs/<slug>/status")
@csrf.exempt
@limiter.limit("120 per minute")
def job_status(slug: str):
    job = Job.query.filter_by(slug=slug).first()
    if job is None or (job.status or "").lower() == "draft":
        return jsonify({"ok": False, "error": "Job not found"}), 404
    return jsonify({"ok": True, **job_window_payload(job)})


@api_bp.post("/apply-check")
@csrf.exempt
@limiter.limit("20 per 15 minutes")
def apply_check():
    values = request.get_json(silent=True) or request.values
    slug = (values.get("slug") or "sales-executive").strip()
    job = Job.query.filter_by(slug=slug).first()
    if job is None or (job.status or "").lower() == "draft":
        return jsonify({"ok": False, "error": "Job not found"}), 404
    errors = find_duplicate_fields(job.job_id, values.get("email") or "", values.get("mobile") or "")
    return jsonify({"ok": True, "duplicate": bool(errors), "errors": errors})


@api_bp.route("/application-status", methods=["GET", "POST"])
@csrf.exempt
@limiter.limit("8 per 15 minutes")
def application_status():
    values = request.get_json(silent=True) or request.values
    application = verify_application(
        values.get("application_number") or "",
        values.get("mobile") or "",
        values.get("email") or "",
    )
    if application is None:
        return jsonify({"ok": False, "error": GENERIC_VERIFY_ERROR}), 404
    return jsonify({"ok": True, **public_status_payload(application)})
