"""HR module routes — integrated into the existing ERP on port 8000."""

from __future__ import annotations

from datetime import date

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from app.decorators import admin_required, login_required
from app.services import hr_service as hr
from app.services import recruitment_applications_service as rec
from app.services.hr_letters import resolve_stored_file
from app.services.menu_service import MenuService

bp = Blueprint("hr", __name__, url_prefix="/hr")


def _breadcrumb(path: str):
    return MenuService().get_breadcrumb(path, session.get("role"))


def _page(template: str, title: str, path: str, **context):
    hr.bootstrap()
    return render_template(
        template,
        page_title=title,
        breadcrumb=_breadcrumb(path),
        **context,
    )


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def index():
    return redirect(url_for("hr.dashboard"))


@bp.route("/dashboard", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def dashboard():
    return _page("hr/dashboard.html", "HR Dashboard", "/hr/dashboard", kpis=hr.dashboard_kpis())


@bp.route("/jobs", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def jobs():
    error = None
    rows = []
    try:
        rows = rec.list_jobs()
    except Exception as exc:
        error = str(exc)
    return _page("hr/jobs.html", "Job Openings", "/hr/jobs", rows=rows, error=error)


@bp.route("/applications", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def applications():
    search = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    error = None
    rows = []
    try:
        rows = hr.list_enriched_applications(search=search, status=status)
    except Exception as exc:
        error = str(exc)
    return _page(
        "hr/applications.html",
        "Applications",
        "/hr/applications",
        rows=rows,
        error=error,
        search=search,
        status=status,
        statuses=hr.WEBSITE_STATUSES,
    )


@bp.route("/applications/<int:application_id>", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def application_detail(application_id: int):
    row = hr.get_enriched_application(application_id)
    if row is None:
        abort(404)
    return _page(
        "hr/application_detail.html",
        row.get("application_number") or "Application",
        "/hr/applications",
        app=row,
        statuses=hr.WEBSITE_STATUSES,
        modes=hr.INTERVIEW_MODES,
        results=hr.INTERVIEW_RESULTS,
    )


@bp.route("/applications/<int:application_id>/status", methods=["POST"], strict_slashes=False)
@login_required
@admin_required
def application_status(application_id: int):
    payload = request.get_json(silent=True) or request.form
    try:
        hr.set_application_status(
            application_id,
            payload.get("status") or "",
            payload.get("reason") or "",
        )
        if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return {"ok": True}
        flash("Application status updated.", "success")
    except Exception as exc:
        if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return {"ok": False, "error": str(exc)}, 400
        flash(str(exc), "danger")
    return redirect(url_for("hr.application_detail", application_id=application_id))


@bp.route("/applications/<int:application_id>/convert", methods=["POST"], strict_slashes=False)
@login_required
@admin_required
def convert_employee(application_id: int):
    try:
        employee = hr.convert_to_employee(application_id)
        flash(f"Employee created: {employee.EmployeeCode}", "success")
        return redirect(url_for("hr.employee_profile", employee_id=employee.EmployeeID))
    except Exception as exc:
        flash(str(exc), "danger")
        return redirect(url_for("hr.application_detail", application_id=application_id))


@bp.route("/applications/<int:application_id>/resume", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def application_resume(application_id: int):
    resolved = rec.resolve_resume(application_id)
    if resolved is None:
        abort(404)
    path, name, mime = resolved
    hr.mark_document_access(application_id, "DOCUMENT_DOWNLOADED")
    return send_file(path, mimetype=mime, as_attachment=True, download_name=name)


@bp.route("/applications/<int:application_id>/pdf", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def application_pdf(application_id: int):
    resolved = rec.resolve_application_pdf(application_id)
    if resolved is None:
        abort(404)
    path, name, mime = resolved
    hr.mark_document_access(application_id, "DOCUMENT_VIEWED")
    return send_file(path, mimetype=mime, as_attachment=True, download_name=name)


@bp.route("/pipeline", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def pipeline():
    error = None
    grouped = {stage: [] for stage in hr.PIPELINE_STAGES}
    try:
        for row in hr.list_enriched_applications():
            stage = row["pipeline_stage"]
            grouped.setdefault(stage, [])
            if stage in grouped:
                grouped[stage].append(row)
    except Exception as exc:
        error = str(exc)
    return _page(
        "hr/pipeline.html",
        "Recruitment Pipeline",
        "/hr/pipeline",
        grouped=grouped,
        stages=hr.PIPELINE_STAGES,
        error=error,
    )


@bp.route("/interviews", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def interviews():
    rows = hr.list_interviews()
    if request.args.get("date") == "today":
        rows = [row for row in rows if row.InterviewDate == date.today()]
    return _page("hr/interviews.html", "Interviews", "/hr/interviews", rows=rows)


@bp.route("/interviews/new", methods=["GET", "POST"], strict_slashes=False)
@login_required
@admin_required
def interview_new():
    application_id = request.values.get("application_id", type=int)
    if request.method == "POST":
        try:
            row = hr.save_interview(request.form)
            flash("Interview saved.", "success")
            return redirect(url_for("hr.interview_edit", interview_id=row.InterviewID))
        except Exception as exc:
            flash(str(exc), "danger")
    application = hr.get_enriched_application(application_id) if application_id else None
    return _page(
        "hr/interview_form.html",
        "Schedule Interview",
        "/hr/interviews",
        interview=None,
        application=application,
        modes=hr.INTERVIEW_MODES,
        results=hr.INTERVIEW_RESULTS,
    )


@bp.route("/interviews/<int:interview_id>", methods=["GET", "POST"], strict_slashes=False)
@login_required
@admin_required
def interview_edit(interview_id: int):
    from app.models.hr import HrInterview

    interview = HrInterview.query.get(interview_id)
    if interview is None:
        abort(404)
    if request.method == "POST":
        try:
            interview = hr.save_interview(request.form, interview_id=interview_id)
            flash("Interview updated.", "success")
        except Exception as exc:
            flash(str(exc), "danger")
    application = hr.get_enriched_application(interview.ApplicationID)
    return _page(
        "hr/interview_form.html",
        "Interview",
        "/hr/interviews",
        interview=interview,
        application=application,
        modes=hr.INTERVIEW_MODES,
        results=hr.INTERVIEW_RESULTS,
    )


@bp.route("/selected", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def selected():
    error = None
    rows = []
    try:
        rows = [
            row
            for row in hr.list_enriched_applications()
            if row["effective_status"] == "Selected" or row["pipeline_stage"] == "Selected"
        ]
    except Exception as exc:
        error = str(exc)
    return _page("hr/selected.html", "Selected Candidates", "/hr/selected", rows=rows, error=error)


@bp.route("/employees", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def employees():
    return _page("hr/employees.html", "Employee Master", "/hr/employees", rows=hr.list_employees())


@bp.route("/employees/directory", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def directory():
    return _page(
        "hr/directory.html",
        "Employee Directory",
        "/hr/employees/directory",
        rows=hr.list_employees(),
    )


@bp.route("/employees/documents", methods=["GET", "POST"], strict_slashes=False)
@login_required
@admin_required
def documents():
    if request.method == "POST":
        try:
            hr.upload_employee_document(
                int(request.form.get("employee_id") or 0),
                request.form.get("document_type") or "Other Documents",
                request.files.get("file"),
            )
            flash("Document uploaded.", "success")
        except Exception as exc:
            flash(str(exc), "danger")
        return redirect(url_for("hr.documents"))
    return _page(
        "hr/documents.html",
        "Employee Documents",
        "/hr/employees/documents",
        rows=hr.list_employees(),
        document_types=hr.DOCUMENT_TYPES,
    )


@bp.route("/employees/timeline", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def timelines():
    rows = [{"employee": emp, "events": hr.employee_timeline(emp["EmployeeID"])} for emp in hr.list_employees()]
    return _page("hr/timelines.html", "Employee Timeline", "/hr/employees/timeline", rows=rows)


@bp.route("/employees/probation", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def probation():
    return _page(
        "hr/probation.html",
        "Probation Tracker",
        "/hr/employees/probation",
        rows=hr.probation_rows(),
    )


@bp.route("/employees/<int:employee_id>", methods=["GET", "POST"], strict_slashes=False)
@login_required
@admin_required
def employee_profile(employee_id: int):
    if request.method == "POST":
        try:
            hr.update_employee(employee_id, request.form)
            flash("Employee updated.", "success")
        except Exception as exc:
            flash(str(exc), "danger")
        return redirect(url_for("hr.employee_profile", employee_id=employee_id))
    employee = hr.employee_detail(employee_id)
    if employee is None:
        abort(404)
    application = None
    if employee.get("ApplicationID"):
        application = hr.get_enriched_application(employee["ApplicationID"])
    return _page(
        "hr/employee_profile.html",
        employee.get("EmployeeCode") or "Employee",
        "/hr/employees",
        employee=employee,
        application=application,
        timeline=hr.employee_timeline(employee_id),
        masters=hr.masters(),
        statuses=hr.EMPLOYMENT_STATUSES,
        document_types=hr.DOCUMENT_TYPES,
    )


@bp.route("/employees/<int:employee_id>/offer", methods=["POST"], strict_slashes=False)
@login_required
@admin_required
def employee_offer(employee_id: int):
    try:
        hr.generate_offer(employee_id)
        flash("Offer letter generated.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hr.employee_profile", employee_id=employee_id))


@bp.route("/employees/<int:employee_id>/appointment", methods=["POST"], strict_slashes=False)
@login_required
@admin_required
def employee_appointment(employee_id: int):
    try:
        hr.generate_appointment(employee_id)
        flash("Appointment letter generated.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("hr.employee_profile", employee_id=employee_id))


@bp.route("/letters/offers", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def offers():
    from app.models.hr import HrOfferLetter

    status = (request.args.get("status") or "").strip()
    q = HrOfferLetter.query.order_by(HrOfferLetter.OfferID.desc())
    if status:
        q = q.filter(HrOfferLetter.OfferStatus == status)
    return _page(
        "hr/offers.html",
        "Offer Letters",
        "/hr/letters/offers",
        rows=q.all(),
        status=status,
        statuses=hr.OFFER_STATUSES,
    )


@bp.route("/letters/offers/<int:offer_id>/status", methods=["POST"], strict_slashes=False)
@login_required
@admin_required
def offer_status(offer_id: int):
    try:
        hr.set_offer_status(offer_id, request.form.get("status") or "")
        flash("Offer status updated.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(request.referrer or url_for("hr.offers"))


@bp.route("/letters/offers/<int:offer_id>/download", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def offer_download(offer_id: int):
    from app.models.hr import HrOfferLetter

    row = HrOfferLetter.query.get(offer_id)
    if row is None:
        abort(404)
    path = resolve_stored_file(row.StoredName or "")
    if path is None:
        abort(404)
    hr.mark_document_access(offer_id, "DOCUMENT_DOWNLOADED")
    return send_file(path, mimetype="application/pdf", as_attachment=True, download_name=row.OriginalName)


@bp.route("/letters/offers/<int:offer_id>/email", methods=["POST"], strict_slashes=False)
@login_required
@admin_required
def offer_email(offer_id: int):
    ok, message = hr.send_letter_email(kind="offer", row_id=offer_id)
    flash(message, "success" if ok else "danger")
    return redirect(request.referrer or url_for("hr.offers"))


@bp.route("/letters/appointments", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def appointments():
    from app.models.hr import HrAppointmentLetter

    return _page(
        "hr/appointments.html",
        "Appointment Letters",
        "/hr/letters/appointments",
        rows=HrAppointmentLetter.query.order_by(HrAppointmentLetter.AppointmentID.desc()).all(),
        employees=hr.list_employees(),
    )


@bp.route("/letters/appointments/<int:appointment_id>/download", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def appointment_download(appointment_id: int):
    from app.models.hr import HrAppointmentLetter

    row = HrAppointmentLetter.query.get(appointment_id)
    if row is None:
        abort(404)
    path = resolve_stored_file(row.StoredName or "")
    if path is None:
        abort(404)
    hr.mark_document_access(appointment_id, "DOCUMENT_DOWNLOADED")
    return send_file(path, mimetype="application/pdf", as_attachment=True, download_name=row.OriginalName)


@bp.route("/letters/appointments/<int:appointment_id>/email", methods=["POST"], strict_slashes=False)
@login_required
@admin_required
def appointment_email(appointment_id: int):
    ok, message = hr.send_letter_email(kind="appointment", row_id=appointment_id)
    flash(message, "success" if ok else "danger")
    return redirect(request.referrer or url_for("hr.appointments"))


@bp.route("/letters/templates", methods=["GET", "POST"], strict_slashes=False)
@login_required
@admin_required
def templates():
    if request.method == "POST":
        try:
            hr.save_letter_template(
                int(request.form.get("template_id") or 0),
                request.form.get("title") or "",
                request.form.get("body") or "",
                request.form.get("is_active") == "1",
            )
            flash("Template updated.", "success")
        except Exception as exc:
            flash(str(exc), "danger")
        return redirect(url_for("hr.templates"))
    return _page(
        "hr/templates.html",
        "Letter Templates",
        "/hr/letters/templates",
        rows=hr.letter_templates(),
    )


@bp.route("/masters/<kind>", methods=["GET", "POST"], strict_slashes=False)
@login_required
@admin_required
def masters_page(kind: str):
    titles = {
        "departments": "Department",
        "designations": "Designation",
        "employment-types": "Employment Type",
        "work-locations": "Work Location",
    }
    if kind not in titles:
        abort(404)
    if request.method == "POST":
        try:
            hr.save_master(
                kind,
                request.form.get("name") or "",
                request.form.get("row_id", type=int),
                request.form.get("is_active", default="1") == "1",
            )
            flash("Master saved.", "success")
        except Exception as exc:
            flash(str(exc), "danger")
        return redirect(url_for("hr.masters_page", kind=kind))
    return _page(
        "hr/masters.html",
        titles[kind],
        f"/hr/masters/{kind}",
        kind=kind,
        rows=hr.list_master(kind) or [],
    )


@bp.route("/reports/<kind>", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def reports(kind: str):
    headers: list[str] = []
    rows: list[list] = []
    title = "HR Report"
    if kind == "recruitment":
        title = "Recruitment Report"
        headers = ["Application Number", "Name", "Job", "Status", "Source", "Submitted"]
        try:
            for row in hr.list_enriched_applications():
                rows.append(
                    [
                        row.get("application_number"),
                        row.get("name"),
                        row.get("job_title"),
                        row.get("effective_status"),
                        row.get("source"),
                        row.get("submitted_at"),
                    ]
                )
        except Exception:
            rows = []
    elif kind == "employees":
        title = "Employee Report"
        headers = ["Employee Code", "Name", "Department", "Designation", "Joining", "Status"]
        for row in hr.list_employees():
            rows.append(
                [
                    row.get("EmployeeCode"),
                    row.get("Name"),
                    row.get("department_name"),
                    row.get("designation_name"),
                    row.get("JoiningDate"),
                    row.get("EmploymentStatus"),
                ]
            )
    elif kind == "interviews":
        title = "Interview Report"
        headers = ["Application", "Candidate", "Date", "Mode", "Result"]
        for row in hr.list_interviews():
            rows.append(
                [
                    row.ApplicationNumber,
                    row.CandidateName,
                    row.InterviewDate,
                    row.InterviewMode,
                    row.InterviewResult,
                ]
            )
    elif kind == "letters":
        title = "Offer & Appointment Report"
        headers = ["Type", "Number", "Employee ID", "Status/Date"]
        from app.models.hr import HrAppointmentLetter, HrOfferLetter

        for row in HrOfferLetter.query.all():
            rows.append(["Offer", row.OfferNumber, row.EmployeeID, row.OfferStatus])
        for row in HrAppointmentLetter.query.all():
            rows.append(["Appointment", row.AppointmentNumber, row.EmployeeID, row.AppointmentDate])
    else:
        abort(404)
    if request.args.get("export") == "csv":
        csv_text = hr.export_csv(headers, rows)
        return Response(
            csv_text,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=hr_{kind}.csv"},
        )
    return _page(
        "hr/report.html",
        title,
        f"/hr/reports/{kind}",
        headers=headers,
        rows=rows,
        kind=kind,
    )


@bp.route("/actions", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def actions():
    return _page("hr/actions.html", "HR Actions", "/hr/actions", items=hr.action_items())


@bp.route("/documents/<int:document_id>/download", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def document_download(document_id: int):
    from app.models.hr import HrEmployeeDocument

    row = HrEmployeeDocument.query.get(document_id)
    if row is None:
        abort(404)
    path = resolve_stored_file(row.StoredName)
    if path is None:
        abort(404)
    hr.mark_document_access(document_id, "DOCUMENT_DOWNLOADED")
    return send_file(
        path,
        mimetype=row.MimeType or "application/octet-stream",
        as_attachment=True,
        download_name=row.OriginalName,
    )
