"""Public careers pages — no account required to view the job."""

from __future__ import annotations

import hmac
from hashlib import sha256

from io import BytesIO

from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_wtf.csrf import generate_csrf

from recruitment.application_pdf import (
    build_pdf,
    payload_from_form,
    resolve_application_pdf,
    store_final_pdf,
)
from recruitment.applications import (
    DUPLICATE_EMAIL_MESSAGE,
    DUPLICATE_FORM_MESSAGE,
    DUPLICATE_MOBILE_MESSAGE,
    DuplicateApplicationError,
    find_duplicate_fields,
    submit_application,
)
from recruitment.audit import write_audit
from recruitment.candidate_status import GENERIC_VERIFY_ERROR, public_status_payload, verify_application
from recruitment.extensions import csrf, db, limiter
from recruitment.job_window import CLOSED_MESSAGE, is_job_application_open, job_window_payload, last_date_label
from recruitment.models import Job, JobApplication
from recruitment.uploads import UploadError, validate_resume
from recruitment.validation import (
    EMPLOYMENT_STATUSES,
    GENDERS,
    INDIAN_STATES,
    NOTICE_PERIODS,
    QUALIFICATIONS,
    SKILL_LEVELS,
    SOURCE_OPTIONS,
    validate_application,
)

public_bp = Blueprint("public", __name__)

WEBSITE_JOB_PATH = "/pages/careers-sales-executive.html"


def website_base() -> str:
    """Public JTCS website origin. Job listing lives there, not on the apply backend."""
    if current_app.config.get("TESTING"):
        return ""
    configured = (current_app.config.get("PUBLIC_SITE_URL") or "").strip().rstrip("/")
    ref = request.referrer or ""
    if ref:
        parsed = urlparse(ref)
        if parsed.scheme and parsed.netloc:
            origin = f"{parsed.scheme}://{parsed.netloc}"
            host = (parsed.hostname or "").lower()
            port = parsed.port
            if host in {"localhost", "127.0.0.1", "0.0.0.0"} and port in {5000, 5500}:
                return origin
            if host.endswith("jtcsxpert.com"):
                return origin
    if configured:
        return configured
    return "http://127.0.0.1:5500"


def website_job_url() -> str:
    return website_base() + WEBSITE_JOB_PATH


def website_applied_url(application_number: str, token: str) -> str:
    return url_for("public.confirmation", number=application_number, t=token)


def _job(slug: str) -> Job | None:
    job = Job.query.filter_by(slug=slug).first()
    if job is None or (job.status or "").lower() == "draft":
        return None
    return job


def _apply_context(job: Job, values=None, errors=None) -> dict:
    return {
        "job": job,
        "window": job_window_payload(job),
        "applications_open": is_job_application_open(job),
        "last_date_label": last_date_label(job),
        "csrf_token": generate_csrf(),
        "genders": GENDERS,
        "states": INDIAN_STATES,
        "qualifications": QUALIFICATIONS,
        "skill_levels": SKILL_LEVELS,
        "employment_statuses": EMPLOYMENT_STATUSES,
        "notice_periods": NOTICE_PERIODS,
        "sources": SOURCE_OPTIONS,
        "values": values or {},
        "errors": errors or {},
        "duplicate": ((errors or {}).get("email") == DUPLICATE_EMAIL_MESSAGE)
        or ((errors or {}).get("mobile") == DUPLICATE_MOBILE_MESSAGE),
    }


def _wants_json() -> bool:
    requested = (request.headers.get("X-Requested-With") or "").lower()
    if requested == "xmlhttprequest":
        return True
    return request.accept_mimetypes.best == "application/json"


def _resume_from_request():
    for item in request.files.getlist("resume"):
        if item and (item.filename or "").strip():
            return item
    resume = request.files.get("resume")
    if resume and (resume.filename or "").strip():
        return resume
    return None


def _apply_fail(job: Job, data: dict, errors: dict, status: int):
    ctx = _apply_context(job, data, errors)
    if _wants_json():
        return jsonify({"ok": False, "errors": errors, "duplicate": bool(ctx.get("duplicate"))}), status
    return render_template("public/apply.html", **ctx), status


def _apply_ok(url: str):
    if _wants_json():
        return jsonify({"ok": True, "redirect": url})
    return redirect(url)


@public_bp.get("/careers/")
def careers_index():
    jobs = Job.query.filter(Job.status != "draft").order_by(Job.created_at.desc()).all()
    return render_template("public/careers.html", jobs=jobs)


@public_bp.get("/careers/<slug>")
def job_page(slug: str):
    if slug in {"application-status", "apply", "confirmation"}:
        return render_template("public/closed.html"), 404
    job = _job(slug)
    if job is None:
        return render_template("public/closed.html"), 404
    write_audit("JOB_PAGE_VIEW", "Job page viewed", details=f"job={job.slug}")
    db.session.commit()
    return redirect(website_job_url())


@public_bp.route("/careers/apply/<slug>", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def apply(slug: str):
    job = _job(slug)
    if job is None:
        return render_template("public/closed.html"), 404

    if request.method == "GET":
        if is_job_application_open(job):
            write_audit("APPLICATION_STARTED", "Application form opened", details=f"job={job.slug}")
        else:
            write_audit(
                "APPLICATION_ATTEMPTED_AFTER_DEADLINE",
                "Application page opened after deadline",
                details=f"job={job.slug}",
            )
        db.session.commit()
        return render_template("public/apply.html", **_apply_context(job))

    if not is_job_application_open(job):
        write_audit(
            "APPLICATION_ATTEMPTED_AFTER_DEADLINE",
            "Application submitted after deadline",
            details=f"job={job.slug}",
        )
        db.session.commit()
        return _apply_fail(job, request.form.to_dict(), {"form": CLOSED_MESSAGE}, 403)

    data = request.form.to_dict()
    resume = _resume_from_request()
    errors = {}
    payload = None
    try:
        if resume is not None:
            payload = validate_resume(resume, current_app.config["MAX_RESUME_MB"])
    except UploadError as exc:
        errors["resume"] = str(exc)

    clean, field_errors = validate_application(data, has_resume=payload is not None)
    errors.update(field_errors)
    duplicates = find_duplicate_fields(job.job_id, clean.get("email") or "", clean.get("mobile") or "")
    if duplicates.get("email") and "email" not in field_errors:
        errors["email"] = duplicates["email"]
    if duplicates.get("mobile") and "mobile" not in field_errors:
        errors["mobile"] = duplicates["mobile"]
    if errors:
        if duplicates and (errors.get("email") in duplicates.values() or errors.get("mobile") in duplicates.values()):
            errors["form"] = errors.get("form") or DUPLICATE_FORM_MESSAGE
            status = 409
        else:
            errors["form"] = errors.get("form") or "Please correct the highlighted fields, then submit again."
            status = 400
        return _apply_fail(job, data, errors, status)

    try:
        application = submit_application(job, clean, payload, resume.filename)
    except DuplicateApplicationError as exc:
        return _apply_fail(job, data, {"form": str(exc), **exc.fields}, 409)
    except ValueError as exc:
        flash(str(exc), "warning")
        return _apply_fail(job, data, {"form": str(exc)}, 409)

    return _apply_ok(website_applied_url(application.application_number, _pdf_token(application)))


def _pdf_token(application: JobApplication) -> str:
    raw = f"{application.application_id}:{application.application_number}".encode()
    return hmac.new(str(current_app.config["SECRET_KEY"]).encode(), raw, sha256).hexdigest()[:32]


@public_bp.post("/careers/apply/<slug>/preview-pdf")
@limiter.limit("20 per hour")
def preview_pdf(slug: str):
    job = _job(slug)
    if job is None:
        return "Not found.", 404
    resume = request.files.get("resume")
    resume_name = resume.filename if resume and resume.filename else (request.form.get("resume_name") or "")
    payload = payload_from_form(request.form.to_dict(), job, resume_name)
    data = build_pdf(payload)
    return send_file(
        BytesIO(data),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="JTCS-Sales-Executive-Application-PREVIEW.pdf",
    )


@public_bp.route("/careers/application-status", methods=["GET", "POST"])
@limiter.limit("8 per 15 minutes", methods=["POST"])
def application_status():
    result = None
    error = None
    number = (request.values.get("application_number") or "").strip()
    mobile = (request.values.get("mobile") or "").strip()
    email = (request.values.get("email") or "").strip()
    if request.method == "POST":
        application = verify_application(number, mobile, email)
        if application is None:
            error = GENERIC_VERIFY_ERROR
        else:
            result = public_status_payload(application)
            result["download_token"] = _pdf_token(application)
    return render_template(
        "public/application_status.html",
        result=result,
        error=error,
        values={"application_number": number, "mobile": mobile, "email": email},
        csrf_token=generate_csrf(),
    )


@public_bp.post("/careers/application-status/pdf")
@limiter.limit("8 per 15 minutes")
def application_status_pdf():
    application = verify_application(
        request.form.get("application_number") or "",
        request.form.get("mobile") or "",
        request.form.get("email") or "",
    )
    if application is None:
        flash(GENERIC_VERIFY_ERROR, "warning")
        return redirect(url_for("public.application_status"))
    path = resolve_application_pdf(application)
    if path is None:
        try:
            store_final_pdf(application)
            db.session.commit()
            path = resolve_application_pdf(application)
        except Exception:
            path = None
    if path is None:
        flash("Your application is saved, but the PDF is not available yet. Please try again shortly.", "warning")
        return redirect(url_for("public.application_status"))
    write_audit(
        "APPLICATION_PDF_DOWNLOADED",
        "Candidate downloaded application PDF",
        application_id=application.application_id,
        candidate_id=application.candidate_id,
        details=application.application_number,
    )
    db.session.commit()
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=application.application_pdf_original_name or f"{application.application_number}-Application.pdf",
    )


@public_bp.get("/careers/confirmation/<number>")
def confirmation(number: str):
    application = JobApplication.query.filter_by(application_number=number).first()
    if application is None:
        return render_template("public/closed.html"), 404
    pdf_error = request.args.get("pdf") == "0"
    return render_template(
        "public/confirmation.html",
        application_number=application.application_number,
        job_title=application.job.job_title if application.job else "Sales Executive",
        pdf_token=_pdf_token(application),
        pdf_error=pdf_error,
        has_pdf=bool(getattr(application, "application_pdf_stored_name", None)),
    )


@public_bp.get("/careers/confirmation/<number>/pdf")
@limiter.limit("20 per hour")
def confirmation_pdf(number: str):
    application = JobApplication.query.filter_by(application_number=number).first()
    if application is None:
        return render_template("public/closed.html"), 404
    token = (request.args.get("t") or "").strip()
    if not token or not hmac.compare_digest(token, _pdf_token(application)):
        return ("Not found.", 404)
    path = resolve_application_pdf(application)
    if path is None:
        try:
            store_final_pdf(application)
            db.session.commit()
            path = resolve_application_pdf(application)
        except Exception:
            path = None
    if path is None:
        flash("Your application has been submitted successfully. However, the PDF could not be generated immediately. Please use the Download Application PDF option from your application status page.", "warning")
        return redirect(url_for("public.confirmation", number=number, pdf="0"))
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=application.application_pdf_original_name or f"{application.application_number}-Application.pdf",
    )


@public_bp.route("/api/careers/application-status", methods=["GET", "POST"])
@csrf.exempt
@limiter.limit("8 per 15 minutes")
def application_status_api_alias():
    values = request.get_json(silent=True) or request.values
    application = verify_application(
        values.get("application_number") or "",
        values.get("mobile") or "",
        values.get("email") or "",
    )
    if application is None:
        return jsonify({"ok": False, "error": GENERIC_VERIFY_ERROR}), 404
    return jsonify({"ok": True, **public_status_payload(application)})


@public_bp.get("/healthz")
@csrf.exempt
def healthz():
    return {"ok": True, "service": "jtcs-recruitment"}
