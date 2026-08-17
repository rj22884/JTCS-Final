"""Admin recruitment console — authentication and RBAC required."""

from __future__ import annotations

from datetime import datetime
from functools import wraps
from io import BytesIO

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_

from recruitment.admin_queries import education_map, experience_label, filter_options, filtered_applications
from recruitment.analytics import analytics_payload, dashboard_stats
from recruitment.applications import change_status
from recruitment.audit import write_audit
from recruitment.exports import (
    export_applications_csv,
    export_applications_pdf,
    export_applications_xlsx,
    export_csv,
    export_pdf,
    export_xlsx,
)
from recruitment.extensions import db, limiter
from recruitment.models import (
    ADMIN_ROLES,
    APPLICATION_STATUSES,
    EVENT_TYPES,
    INTERVIEW_MODES,
    INTERVIEW_RESULTS,
    AdminUser,
    ApplicationNote,
    Candidate,
    Job,
    JobApplication,
    RecruitmentAuditLog,
    RecruitmentSetting,
    utcnow,
)
from recruitment.application_pdf import resolve_application_pdf, store_final_pdf
from recruitment.sso import read_sso_token
from recruitment.uploads import resolve_resume_path

admin_bp = Blueprint("admin", __name__, url_prefix="/recruitment/admin")


def _roles(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)

        return wrapped

    return decorator


def write_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.can_write():
            abort(403)
        return fn(*args, **kwargs)

    return wrapped


@admin_bp.get("/sso")
@limiter.limit("20 per minute")
def sso_login():
    token = (request.args.get("token") or "").strip()
    try:
        payload = read_sso_token(token, current_app.config.get("SSO_SECRET") or "")
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("admin.login"))
    user = AdminUser.query.filter_by(email=payload["email"]).first()
    if user is None:
        user = AdminUser(
            name=payload["name"][:120],
            email=payload["email"],
            role=payload["role"],
            is_active_flag=True,
        )
        user.set_password(f"sso-only-{utcnow().timestamp()}")
        db.session.add(user)
    elif not user.is_active:
        flash("This recruitment admin account is inactive.", "danger")
        return redirect(url_for("admin.login"))
    else:
        user.name = payload["name"][:120]
        if payload["role"] == "admin":
            user.role = "admin"
    login_user(user, remember=False)
    user.last_login_at = utcnow()
    write_audit("ADMIN_LOGIN", "Admin signed in via ERP SSO", actor_type="admin", actor_name=user.email)
    db.session.commit()
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = AdminUser.query.filter_by(email=email).first()
        if user and user.is_active and user.check_password(password):
            login_user(user, remember=False)
            user.last_login_at = utcnow()
            write_audit("ADMIN_LOGIN", "Admin signed in", actor_type="admin", actor_name=user.email)
            db.session.commit()
            return redirect(request.args.get("next") or url_for("admin.dashboard"))
        write_audit(
            "ADMIN_LOGIN_FAILED",
            "Failed admin login",
            details=f"email={email}",
            actor_type="visitor",
        )
        db.session.commit()
        flash("Invalid email or password.", "danger")
    return render_template("admin/login.html")


@admin_bp.post("/logout")
@login_required
def logout():
    write_audit("ADMIN_LOGOUT", "Admin signed out", actor_type="admin", actor_name=current_user.email)
    db.session.commit()
    logout_user()
    return redirect(url_for("admin.login"))


@admin_bp.get("/")
@login_required
def dashboard():
    return render_template("admin/dashboard.html", stats=dashboard_stats(), data=analytics_payload())


@admin_bp.get("/jobs")
@login_required
def jobs():
    return render_template("admin/jobs.html", jobs=Job.query.order_by(Job.created_at.desc()).all())


@admin_bp.route("/jobs/<int:job_id>", methods=["GET", "POST"])
@login_required
def job_edit(job_id: int):
    job = db.session.get(Job, job_id) or abort(404)
    if request.method == "POST":
        if not current_user.can_write():
            abort(403)
        for field in (
            "job_title", "department", "location", "employment_type", "description",
            "about_company", "responsibilities", "required_skills", "experience_required",
            "qualification_required", "salary_ctc", "benefits", "application_instructions",
            "status",
        ):
            if field in request.form:
                setattr(job, field, (request.form.get(field) or "").strip() or None)
        closing = (request.form.get("closing_date") or "").strip()
        job.closing_date = datetime.strptime(closing, "%Y-%m-%d").date() if closing else None
        job.closing_time = (request.form.get("closing_time") or "23:59:59").strip() or "23:59:59"
        job.timezone = (request.form.get("timezone") or "Asia/Kolkata").strip() or "Asia/Kolkata"
        write_audit("JOB_UPDATED", f"Job updated: {job.job_title}", details=f"job_id={job.job_id}")
        db.session.commit()
        flash("Job updated.", "success")
        return redirect(url_for("admin.jobs"))
    return render_template("admin/job_form.html", job=job)


def _per_page() -> int:
    allowed = {10, 25, 50, 100}
    try:
        value = int(request.args.get("per_page") or 25)
    except ValueError:
        value = 25
    return value if value in allowed else 25


@admin_bp.get("/applications")
@login_required
def applications():
    q = filtered_applications(request)
    page = max(int(request.args.get("page") or 1), 1)
    per_page = _per_page()
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    options = filter_options()
    showing_from = ((pagination.page - 1) * pagination.per_page) + 1 if pagination.total else 0
    showing_to = min(pagination.total, pagination.page * pagination.per_page)
    return render_template(
        "admin/applications.html",
        pagination=pagination,
        showing_from=showing_from,
        showing_to=showing_to,
        statuses=APPLICATION_STATUSES,
        cities=options["cities"],
        sources=options["sources"],
        qualifications=options["qualifications"],
        filters=request.args,
        education_map=education_map,
        experience_label=experience_label,
        per_page=per_page,
    )


@admin_bp.get("/applications/<int:application_id>")
@login_required
def application_detail(application_id: int):
    application = db.session.get(JobApplication, application_id) or abort(404)
    write_audit(
        "APPLICATION_VIEWED",
        "Application viewed",
        candidate_id=application.candidate_id,
        application_id=application.application_id,
        details=application.application_number,
    )
    db.session.commit()
    logs = (
        RecruitmentAuditLog.query.filter(
            or_(
                RecruitmentAuditLog.application_id == application.application_id,
                RecruitmentAuditLog.visitor_id == application.visitor_id,
            )
        )
        .order_by(RecruitmentAuditLog.event_timestamp.asc())
        .all()
    )
    return render_template(
        "admin/application_detail.html",
        application=application,
        statuses=APPLICATION_STATUSES,
        logs=logs,
        edu=education_map(application.candidate),
        exp_label=experience_label(application.candidate.experience[0] if application.candidate.experience else None),
        interview_modes=INTERVIEW_MODES,
        interview_results=INTERVIEW_RESULTS,
        employee=application.employee,
    )


@admin_bp.post("/applications/<int:application_id>/status")
@write_required
def application_status(application_id: int):
    application = db.session.get(JobApplication, application_id) or abort(404)
    new_status = (request.form.get("status") or "").strip()
    if new_status not in APPLICATION_STATUSES:
        abort(400)
    reason = (request.form.get("reason") or "").strip()[:500]
    change_status(application, new_status, current_user.email, reason)
    flash("Status updated.", "success")
    return redirect(url_for("admin.application_detail", application_id=application.application_id))


@admin_bp.post("/applications/<int:application_id>/notes")
@write_required
def add_note(application_id: int):
    application = db.session.get(JobApplication, application_id) or abort(404)
    note = (request.form.get("note") or "").strip()[:2000]
    if not note:
        flash("Please enter a note.", "warning")
        return redirect(url_for("admin.application_detail", application_id=application.application_id))
    db.session.add(ApplicationNote(application_id=application.application_id, note=note, created_by=current_user.email))
    write_audit(
        "INTERNAL_NOTE_ADDED",
        "Internal note added",
        candidate_id=application.candidate_id,
        application_id=application.application_id,
        details=application.application_number,
    )
    db.session.commit()
    flash("Note saved. Candidates cannot see internal notes.", "success")
    return redirect(url_for("admin.application_detail", application_id=application.application_id))


@admin_bp.post("/applications/<int:application_id>/interview")
@write_required
def save_interview(application_id: int):
    application = db.session.get(JobApplication, application_id) or abort(404)
    date_val = (request.form.get("interview_date") or "").strip()
    time_val = (request.form.get("interview_time") or "").strip()
    when = None
    if date_val and time_val:
        when = datetime.strptime(f"{date_val} {time_val}", "%Y-%m-%d %H:%M")
    elif date_val:
        when = datetime.strptime(date_val, "%Y-%m-%d")
    application.interview_scheduled_at = when
    mode = (request.form.get("interview_mode") or "").strip()
    application.interview_mode = mode if mode in INTERVIEW_MODES else (mode or None)
    application.interview_location = (request.form.get("interview_location") or "").strip()[:200] or None
    application.interview_interviewer = (request.form.get("interview_interviewer") or "").strip()[:200] or None
    application.interview_notes = (request.form.get("interview_notes") or "").strip()[:2000] or None
    result = (request.form.get("interview_result") or "").strip()
    application.interview_result = result if result in INTERVIEW_RESULTS else (result or None)
    write_audit(
        "INTERVIEW_UPDATED",
        "Interview information updated",
        candidate_id=application.candidate_id,
        application_id=application.application_id,
        details=application.application_number,
    )
    if when and application.application_status in {"New", "Under Review", "Shortlisted"}:
        change_status(application, "Interview Scheduled", current_user.email, "Interview scheduled", commit=False)
    if application.interview_result in {"Recommended", "Not Recommended", "Further Review"} and application.application_status == "Interview Scheduled":
        change_status(application, "Interviewed", current_user.email, "Interview result recorded", commit=False)
    db.session.commit()
    flash("Interview information saved.", "success")
    return redirect(url_for("admin.application_detail", application_id=application.application_id))


@admin_bp.post("/applications/bulk")
@write_required
def applications_bulk():
    action = (request.form.get("action") or "").strip()
    ids = [int(x) for x in request.form.getlist("application_ids") if str(x).isdigit()]
    if not ids:
        flash("Select at least one application.", "warning")
        return redirect(url_for("admin.applications"))
    apps = JobApplication.query.filter(JobApplication.application_id.in_(ids)).all()
    if action == "export":
        data = export_applications_xlsx(apps, detailed=current_user.can_write())
        write_audit("APPLICATIONS_EXPORTED", "Selected applications exported", details=f"count={len(apps)}")
        db.session.commit()
        return send_file(
            BytesIO(data),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="selected-applications.xlsx",
        )
    status_map = {
        "under_review": "Under Review",
        "shortlist": "Shortlisted",
        "reject": "Rejected",
    }
    new_status = status_map.get(action)
    if new_status not in APPLICATION_STATUSES:
        abort(400)
    for app in apps:
        change_status(app, new_status, current_user.email, "Bulk update", commit=False)
    write_audit(
        "BULK_STATUS_CHANGED",
        f"Bulk status change to {new_status}",
        details=f"count={len(apps)}; ids={','.join(str(i) for i in ids)}",
    )
    db.session.commit()
    flash(f"{len(apps)} application(s) updated to {new_status}.", "success")
    return redirect(url_for("admin.applications"))


@admin_bp.get("/applications/export/<fmt>")
@login_required
def applications_export(fmt: str):
    apps = filtered_applications(request).limit(5000).all()
    detailed = current_user.can_write() and request.args.get("detailed") == "1"
    write_audit("APPLICATIONS_EXPORTED", f"Applications exported as {fmt}", details=f"count={len(apps)}")
    db.session.commit()
    stamp = datetime.utcnow().strftime("%Y%m%d")
    if fmt == "csv":
        data, mime, name = export_applications_csv(apps, detailed), "text/csv", f"job-applications-{stamp}.csv"
    elif fmt == "xlsx":
        data, mime, name = (
            export_applications_xlsx(apps, detailed),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"job-applications-{stamp}.xlsx",
        )
    elif fmt == "pdf":
        data, mime, name = export_applications_pdf(apps, detailed), "application/pdf", f"job-applications-{stamp}.pdf"
    else:
        abort(404)
    return send_file(BytesIO(data), mimetype=mime, as_attachment=True, download_name=name)


@admin_bp.get("/applications/<int:application_id>/resume")
@login_required
def download_resume(application_id: int):
    if not current_user.is_authenticated:
        abort(401)
    if current_user.role == "viewer":
        abort(403)
    application = db.session.get(JobApplication, application_id) or abort(404)
    path = resolve_resume_path(current_app.config["UPLOAD_DIR"], application.resume_stored_name or "")
    if path is None:
        abort(404)
    inline = request.args.get("view") == "1"
    write_audit(
        "RESUME_VIEWED" if inline else "RESUME_DOWNLOADED",
        "Resume viewed" if inline else "Resume downloaded",
        candidate_id=application.candidate_id,
        application_id=application.application_id,
        details=application.application_number,
    )
    db.session.commit()
    return send_file(
        path,
        as_attachment=not inline,
        download_name=application.resume_original_name or "resume.pdf",
        mimetype=application.resume_file_type or "application/octet-stream",
    )


@admin_bp.get("/applications/<int:application_id>/pdf")
@login_required
def download_application_pdf(application_id: int):
    if current_user.role == "viewer":
        abort(403)
    application = db.session.get(JobApplication, application_id) or abort(404)
    path = resolve_application_pdf(application)
    if path is None:
        try:
            store_final_pdf(application)
            db.session.commit()
            path = resolve_application_pdf(application)
        except Exception:
            path = None
    if path is None:
        abort(404)
    write_audit(
        "APPLICATION_PDF_DOWNLOADED",
        "Admin downloaded application PDF",
        candidate_id=application.candidate_id,
        application_id=application.application_id,
        details=application.application_number,
        actor_type="admin",
        actor_name=current_user.email,
    )
    db.session.commit()
    inline = request.args.get("view") == "1"
    return send_file(
        path,
        as_attachment=not inline,
        download_name=application.application_pdf_original_name or f"{application.application_number}-Application.pdf",
        mimetype="application/pdf",
    )


@admin_bp.get("/candidates")
@login_required
def candidates():
    q = Candidate.query
    search = (request.args.get("q") or "").strip()
    if search:
        like = f"%{search}%"
        q = q.filter(or_(Candidate.name.ilike(like), Candidate.email.ilike(like), Candidate.mobile.ilike(like)))
    page = max(int(request.args.get("page") or 1), 1)
    pagination = q.order_by(Candidate.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template(
        "admin/candidates.html",
        pagination=pagination,
        education_map=education_map,
    )


@admin_bp.get("/candidates/<int:candidate_id>")
@login_required
def candidate_detail(candidate_id: int):
    candidate = db.session.get(Candidate, candidate_id) or abort(404)
    return render_template("admin/candidate_detail.html", candidate=candidate)


@admin_bp.get("/audit")
@login_required
def audit():
    q = RecruitmentAuditLog.query
    event_type = (request.args.get("event_type") or "").strip()
    visitor = (request.args.get("visitor") or "").strip()
    device = (request.args.get("device") or "").strip()
    browser = (request.args.get("browser") or "").strip()
    application_number = (request.args.get("application_number") or request.args.get("application") or "").strip()
    candidate = (request.args.get("candidate") or "").strip()
    admin_user = (request.args.get("admin") or "").strip()
    date_from = (request.args.get("from") or "").strip()
    date_to = (request.args.get("to") or "").strip()
    if event_type:
        q = q.filter(RecruitmentAuditLog.event_type == event_type)
    if visitor:
        q = q.filter(RecruitmentAuditLog.visitor_id.ilike(f"%{visitor}%"))
    if device:
        q = q.filter(RecruitmentAuditLog.device_type == device)
    if browser:
        q = q.filter(RecruitmentAuditLog.browser.ilike(f"%{browser}%"))
    if date_from:
        q = q.filter(RecruitmentAuditLog.event_timestamp >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        q = q.filter(RecruitmentAuditLog.event_timestamp < datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59))
    if application_number:
        app = JobApplication.query.filter_by(application_number=application_number).first()
        q = q.filter(RecruitmentAuditLog.application_id == (app.application_id if app else -1))
    if candidate:
        matches = Candidate.query.filter(Candidate.name.ilike(f"%{candidate}%")).all()
        ids = [c.candidate_id for c in matches] or [-1]
        q = q.filter(RecruitmentAuditLog.candidate_id.in_(ids))
    if admin_user:
        q = q.filter(RecruitmentAuditLog.actor_name.ilike(f"%{admin_user}%"))
    q = q.order_by(RecruitmentAuditLog.event_timestamp.desc())
    page = max(int(request.args.get("page") or 1), 1)
    pagination = q.paginate(page=page, per_page=40, error_out=False)
    app_ids = {row.application_id for row in pagination.items if row.application_id}
    cand_ids = {row.candidate_id for row in pagination.items if row.candidate_id}
    app_map = {
        a.application_id: a
        for a in JobApplication.query.filter(JobApplication.application_id.in_(app_ids or [-1])).all()
    }
    cand_map = {
        c.candidate_id: c
        for c in Candidate.query.filter(Candidate.candidate_id.in_(cand_ids or [-1])).all()
    }
    return render_template(
        "admin/audit.html",
        pagination=pagination,
        event_types=EVENT_TYPES,
        filters=request.args,
        app_map=app_map,
        cand_map=cand_map,
    )


@admin_bp.get("/audit/export/<fmt>")
@login_required
def audit_export(fmt: str):
    logs = RecruitmentAuditLog.query.order_by(RecruitmentAuditLog.event_timestamp.desc()).limit(5000).all()
    write_audit("AUDIT_EXPORTED", f"Audit exported as {fmt}", details=f"count={len(logs)}")
    db.session.commit()
    stamp = datetime.utcnow().strftime("%Y%m%d")
    if fmt == "csv":
        data, mime, name = export_csv(logs), "text/csv", f"recruitment-audit-{stamp}.csv"
    elif fmt == "xlsx":
        data, mime, name = (
            export_xlsx(logs),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"recruitment-audit-{stamp}.xlsx",
        )
    elif fmt == "pdf":
        data, mime, name = export_pdf(logs), "application/pdf", f"recruitment-audit-{stamp}.pdf"
    else:
        abort(404)
    return send_file(BytesIO(data), mimetype=mime, as_attachment=True, download_name=name)


@admin_bp.get("/analytics")
@login_required
def analytics():
    return render_template("admin/analytics.html", data=analytics_payload())


@admin_bp.route("/settings", methods=["GET", "POST"])
@_roles("admin")
def settings():
    if request.method == "POST":
        for key in (
            "application_number_prefix",
            "application_number_padding",
            "store_ip_address",
            "max_resume_mb",
            "notify_admin_email",
        ):
            row = db.session.get(RecruitmentSetting, key) or RecruitmentSetting(key=key)
            row.value = (request.form.get(key) or "").strip()
            db.session.add(row)
        new_name = (request.form.get("new_user_name") or "").strip()
        new_email = (request.form.get("new_user_email") or "").strip().lower()
        new_password = request.form.get("new_user_password") or ""
        new_role = request.form.get("new_user_role") or "recruiter"
        if new_name and new_email and new_password:
            if new_role not in ADMIN_ROLES:
                new_role = "recruiter"
            if AdminUser.query.filter_by(email=new_email).first():
                flash("That admin email already exists.", "warning")
            else:
                user = AdminUser(name=new_name, email=new_email, role=new_role, is_active_flag=True)
                user.set_password(new_password)
                db.session.add(user)
                flash("Admin user created.", "success")
        write_audit("SETTINGS_UPDATED", "Recruitment settings updated")
        db.session.commit()
        flash("Settings saved.", "success")
        return redirect(url_for("admin.settings"))
    users = AdminUser.query.order_by(AdminUser.created_at.asc()).all()
    values = {row.key: row.value for row in RecruitmentSetting.query.all()}
    return render_template("admin/settings.html", settings=values, users=users, roles=ADMIN_ROLES)
