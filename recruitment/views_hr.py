"""HR Employee Master, offer and appointment letters — admin only."""

from __future__ import annotations

from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from recruitment.applications import change_status
from recruitment.audit import write_audit
from recruitment.emailer import send_mail, smtp_configured
from recruitment.extensions import db
from recruitment.hr import (
    convert_to_employee,
    employee_doc_dir,
    hr_letter_dir,
    recruitment_history,
    resolve_stored,
    store_hr_bytes,
    update_employee_status,
)
from recruitment.hr_letters import build_appointment_pdf, build_offer_pdf, letter_sections, template_version
from recruitment.models import (
    EMPLOYEE_DOCUMENT_TYPES,
    EMPLOYEE_STATUSES,
    EMPLOYMENT_TYPES,
    OFFER_ACCEPTANCE_METHODS,
    OFFER_STATUSES,
    SALARY_FREQUENCIES,
    AppointmentLetter,
    Department,
    Designation,
    Employee,
    EmployeeDocument,
    JobApplication,
    LetterTemplate,
    OfferLetter,
    utcnow,
)

hr_bp = Blueprint("hr", __name__, url_prefix="/recruitment/admin")


def write_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.can_write():
            abort(403)
        return fn(*args, **kwargs)

    return wrapped


def _parse_date(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    return datetime.strptime(raw, "%Y-%m-%d").date()


def _employee_or_404(employee_id: int) -> Employee:
    return db.session.get(Employee, employee_id) or abort(404)


@hr_bp.post("/applications/<int:application_id>/convert")
@write_required
def convert_application(application_id: int):
    application = db.session.get(JobApplication, application_id) or abort(404)
    try:
        employee = convert_to_employee(application, current_user.email)
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("admin.application_detail", application_id=application_id))
    flash(f"Employee created: {employee.employee_code}", "success")
    return redirect(url_for("hr.employee_detail", employee_id=employee.employee_id))


@hr_bp.get("/employees")
@login_required
def employees():
    q = Employee.query.order_by(Employee.created_at.desc())
    status = (request.args.get("status") or "").strip()
    if status:
        q = q.filter_by(employment_status=status)
    rows = q.all()
    return render_template(
        "admin/employees.html",
        employees=rows,
        statuses=EMPLOYEE_STATUSES,
        filters=request.args,
    )


@hr_bp.get("/employees/<int:employee_id>")
@login_required
def employee_detail(employee_id: int):
    employee = _employee_or_404(employee_id)
    return render_template(
        "admin/employee_detail.html",
        employee=employee,
        departments=Department.query.filter_by(is_active=True).order_by(Department.name).all(),
        designations=Designation.query.filter_by(is_active=True).order_by(Designation.name).all(),
        employment_types=EMPLOYMENT_TYPES,
        employee_statuses=EMPLOYEE_STATUSES,
        salary_frequencies=SALARY_FREQUENCIES,
        offer_statuses=OFFER_STATUSES,
        acceptance_methods=OFFER_ACCEPTANCE_METHODS,
        document_types=EMPLOYEE_DOCUMENT_TYPES,
        history=recruitment_history(employee.application),
        latest_offer=employee.offers[0] if employee.offers else None,
        latest_appointment=employee.appointments[0] if employee.appointments else None,
        smtp_ready=smtp_configured(),
    )


@hr_bp.post("/employees/<int:employee_id>")
@write_required
def employee_update(employee_id: int):
    employee = _employee_or_404(employee_id)
    employee.joining_date = _parse_date(request.form.get("joining_date"))
    employee.department_id = int(request.form["department_id"]) if request.form.get("department_id") else None
    employee.designation_id = int(request.form["designation_id"]) if request.form.get("designation_id") else None
    employee.reporting_manager = (request.form.get("reporting_manager") or "").strip()[:200] or None
    employee.employment_type = (request.form.get("employment_type") or "").strip()[:80] or None
    employee.work_location = (request.form.get("work_location") or "").strip()[:200] or None
    employee.probation_period = (request.form.get("probation_period") or "").strip()[:80] or None
    employee.probation_end_date = _parse_date(request.form.get("probation_end_date"))
    employee.salary_ctc = (request.form.get("salary_ctc") or "").strip()[:80] or None
    employee.salary_frequency = (request.form.get("salary_frequency") or "").strip()[:40] or None
    employee.basic_salary = (request.form.get("basic_salary") or "").strip()[:80] or None
    employee.hra = (request.form.get("hra") or "").strip()[:80] or None
    employee.allowances = (request.form.get("allowances") or "").strip()[:200] or None
    employee.other_compensation = (request.form.get("other_compensation") or "").strip()[:200] or None
    employee.compensation_effective_date = _parse_date(request.form.get("compensation_effective_date"))
    new_status = (request.form.get("employment_status") or "").strip()
    if new_status in EMPLOYEE_STATUSES:
        update_employee_status(employee, new_status, current_user.email)
    employee.updated_at = utcnow()
    write_audit(
        "EMPLOYEE_UPDATED",
        "Employee master updated",
        candidate_id=employee.candidate_id,
        application_id=employee.application_id,
        details=employee.employee_code,
        actor_type="admin",
        actor_name=current_user.email,
    )
    db.session.commit()
    flash("Employee details saved.", "success")
    return redirect(url_for("hr.employee_detail", employee_id=employee.employee_id))


@hr_bp.post("/employees/<int:employee_id>/offer")
@write_required
def generate_offer(employee_id: int):
    employee = _employee_or_404(employee_id)
    if employee.application.application_status not in {"Selected", "Offer Issued", "Offer Accepted", "Appointment Issued"}:
        flash("Mark the application as Selected before generating an offer letter.", "warning")
        return redirect(url_for("hr.employee_detail", employee_id=employee.employee_id))
    version = (max((o.version for o in employee.offers), default=0) + 1)
    offer = OfferLetter(
        employee_id=employee.employee_id,
        application_id=employee.application_id,
        offer_number=f"{employee.employee_code}-OFF-{version:02d}",
        version=version,
        offer_date=utcnow().date(),
        joining_date=employee.joining_date,
        salary_ctc=employee.salary_ctc,
        probation_period=employee.probation_period,
        offer_status="Pending",
        generated_by=current_user.email,
    )
    pdf = build_offer_pdf(employee, offer)
    offer.pdf_stored_name = store_hr_bytes(hr_letter_dir(), pdf, f"{offer.offer_number}.pdf")
    offer.pdf_original_name = f"{offer.offer_number}-Offer-Letter.pdf"
    db.session.add(offer)
    employee.employment_status = "Offer Pending"
    change_status(employee.application, "Offer Issued", current_user.email, "Offer letter generated", commit=False)
    write_audit(
        "OFFER_LETTER_GENERATED",
        "Offer letter generated",
        candidate_id=employee.candidate_id,
        application_id=employee.application_id,
        details=offer.offer_number,
        actor_type="admin",
        actor_name=current_user.email,
    )
    db.session.commit()
    flash("Offer letter generated.", "success")
    return redirect(url_for("hr.employee_detail", employee_id=employee.employee_id))


@hr_bp.post("/employees/<int:employee_id>/offer-status")
@write_required
def offer_status(employee_id: int):
    employee = _employee_or_404(employee_id)
    offer = employee.offers[0] if employee.offers else None
    if offer is None:
        flash("Generate an offer letter first.", "warning")
        return redirect(url_for("hr.employee_detail", employee_id=employee.employee_id))
    status = (request.form.get("offer_status") or "").strip()
    if status not in OFFER_STATUSES:
        abort(400)
    offer.offer_status = status
    if status == "Accepted":
        offer.accepted_at = utcnow()
        offer.acceptance_method = (request.form.get("acceptance_method") or "").strip()[:80] or "Other"
        offer.recorded_by = current_user.email
        employee.employment_status = "Offer Accepted"
        change_status(employee.application, "Offer Accepted", current_user.email, "Offer accepted", commit=False)
        event = "OFFER_ACCEPTED"
    elif status == "Declined":
        event = "OFFER_DECLINED"
    else:
        event = "OFFER_STATUS_CHANGED"
    write_audit(
        event,
        f"Offer status set to {status}",
        candidate_id=employee.candidate_id,
        application_id=employee.application_id,
        details=f"{offer.offer_number}; {status}",
        actor_type="admin",
        actor_name=current_user.email,
    )
    db.session.commit()
    flash("Offer status updated.", "success")
    return redirect(url_for("hr.employee_detail", employee_id=employee.employee_id))


@hr_bp.get("/employees/<int:employee_id>/offer.pdf")
@write_required
def download_offer(employee_id: int):
    employee = _employee_or_404(employee_id)
    offer = next((o for o in employee.offers if o.offer_id == int(request.args.get("offer_id") or 0)), None) if request.args.get("offer_id") else (employee.offers[0] if employee.offers else None)
    if offer is None:
        abort(404)
    path = resolve_stored(hr_letter_dir(), offer.pdf_stored_name)
    if path is None:
        abort(404)
    write_audit(
        "DOCUMENT_DOWNLOADED" if request.args.get("view") != "1" else "DOCUMENT_VIEWED",
        "Offer letter accessed",
        candidate_id=employee.candidate_id,
        application_id=employee.application_id,
        details=offer.offer_number,
        actor_type="admin",
        actor_name=current_user.email,
    )
    db.session.commit()
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=request.args.get("view") != "1",
        download_name=offer.pdf_original_name or f"{offer.offer_number}.pdf",
    )


@hr_bp.post("/employees/<int:employee_id>/appointment")
@write_required
def generate_appointment(employee_id: int):
    employee = _employee_or_404(employee_id)
    latest = employee.offers[0] if employee.offers else None
    if latest is None or latest.offer_status != "Accepted":
        flash("Record offer acceptance before generating an appointment letter.", "warning")
        return redirect(url_for("hr.employee_detail", employee_id=employee.employee_id))
    version = max((a.version for a in employee.appointments), default=0) + 1
    letter = AppointmentLetter(
        employee_id=employee.employee_id,
        appointment_number=f"{employee.employee_code}-APT-{version:02d}",
        version=version,
        template_version=template_version("appointment"),
        appointment_date=utcnow().date(),
        joining_date=employee.joining_date,
        issued_by=current_user.email,
    )
    pdf = build_appointment_pdf(employee, letter)
    letter.pdf_stored_name = store_hr_bytes(hr_letter_dir(), pdf, f"{letter.appointment_number}.pdf")
    letter.pdf_original_name = f"{letter.appointment_number}-Appointment-Letter.pdf"
    db.session.add(letter)
    employee.employment_status = "Appointment Issued"
    change_status(employee.application, "Appointment Issued", current_user.email, "Appointment letter issued", commit=False)
    write_audit(
        "APPOINTMENT_LETTER_GENERATED",
        "Appointment letter generated",
        candidate_id=employee.candidate_id,
        application_id=employee.application_id,
        details=letter.appointment_number,
        actor_type="admin",
        actor_name=current_user.email,
    )
    db.session.commit()
    flash("Appointment letter generated.", "success")
    return redirect(url_for("hr.employee_detail", employee_id=employee.employee_id))


@hr_bp.get("/employees/<int:employee_id>/appointment.pdf")
@write_required
def download_appointment(employee_id: int):
    employee = _employee_or_404(employee_id)
    letter = next((a for a in employee.appointments if a.appointment_id == int(request.args.get("appointment_id") or 0)), None) if request.args.get("appointment_id") else (employee.appointments[0] if employee.appointments else None)
    if letter is None:
        abort(404)
    path = resolve_stored(hr_letter_dir(), letter.pdf_stored_name)
    if path is None:
        abort(404)
    write_audit(
        "DOCUMENT_DOWNLOADED" if request.args.get("view") != "1" else "DOCUMENT_VIEWED",
        "Appointment letter accessed",
        candidate_id=employee.candidate_id,
        application_id=employee.application_id,
        details=letter.appointment_number,
        actor_type="admin",
        actor_name=current_user.email,
    )
    db.session.commit()
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=request.args.get("view") != "1",
        download_name=letter.pdf_original_name or f"{letter.appointment_number}.pdf",
    )


def _email_letter(to_email: str, subject: str, filename: str, path: Path) -> bool:
    return send_mail(
        to_email,
        subject,
        f"Please find attached {filename}.\n\nJTCS Xpert\nHaldwani, Uttarakhand",
        None,
        attachments=[(filename, path.read_bytes(), "application/pdf")],
    )


@hr_bp.post("/employees/<int:employee_id>/offer/email")
@write_required
def email_offer(employee_id: int):
    employee = _employee_or_404(employee_id)
    offer = employee.offers[0] if employee.offers else None
    if offer is None:
        abort(404)
    path = resolve_stored(hr_letter_dir(), offer.pdf_stored_name)
    if path is None:
        flash("Offer PDF is not available.", "warning")
        return redirect(url_for("hr.employee_detail", employee_id=employee.employee_id))
    ok = _email_letter(employee.email, f"Offer Letter – {employee.employee_code} – JTCS Xpert", offer.pdf_original_name, path)
    offer.emailed_at = utcnow()
    offer.emailed_to = employee.email
    offer.email_status = "sent" if ok else "failed"
    write_audit(
        "HR_LETTER_EMAILED",
        "Offer letter emailed" if ok else "Offer letter email failed",
        candidate_id=employee.candidate_id,
        application_id=employee.application_id,
        details=f"{offer.offer_number}; {employee.email}; {offer.email_status}",
        actor_type="admin",
        actor_name=current_user.email,
    )
    db.session.commit()
    flash("Offer letter emailed." if ok else "Email could not be sent. Check SMTP settings.", "success" if ok else "warning")
    return redirect(url_for("hr.employee_detail", employee_id=employee.employee_id))


@hr_bp.post("/employees/<int:employee_id>/appointment/email")
@write_required
def email_appointment(employee_id: int):
    employee = _employee_or_404(employee_id)
    letter = employee.appointments[0] if employee.appointments else None
    if letter is None:
        abort(404)
    path = resolve_stored(hr_letter_dir(), letter.pdf_stored_name)
    if path is None:
        flash("Appointment PDF is not available.", "warning")
        return redirect(url_for("hr.employee_detail", employee_id=employee.employee_id))
    ok = _email_letter(employee.email, f"Appointment Letter – {employee.employee_code} – JTCS Xpert", letter.pdf_original_name, path)
    letter.emailed_at = utcnow()
    letter.emailed_to = employee.email
    letter.email_status = "sent" if ok else "failed"
    write_audit(
        "HR_LETTER_EMAILED",
        "Appointment letter emailed" if ok else "Appointment letter email failed",
        candidate_id=employee.candidate_id,
        application_id=employee.application_id,
        details=f"{letter.appointment_number}; {employee.email}; {letter.email_status}",
        actor_type="admin",
        actor_name=current_user.email,
    )
    db.session.commit()
    flash("Appointment letter emailed." if ok else "Email could not be sent. Check SMTP settings.", "success" if ok else "warning")
    return redirect(url_for("hr.employee_detail", employee_id=employee.employee_id))


@hr_bp.post("/employees/<int:employee_id>/documents")
@write_required
def upload_document(employee_id: int):
    employee = _employee_or_404(employee_id)
    uploaded = request.files.get("document")
    doc_type = (request.form.get("document_type") or "Other Documents").strip()
    if doc_type not in EMPLOYEE_DOCUMENT_TYPES:
        doc_type = "Other Documents"
    if not uploaded or not uploaded.filename:
        flash("Choose a file to upload.", "warning")
        return redirect(url_for("hr.employee_detail", employee_id=employee.employee_id))
    data = uploaded.read()
    stored = store_hr_bytes(employee_doc_dir(), data, uploaded.filename)
    db.session.add(
        EmployeeDocument(
            employee_id=employee.employee_id,
            document_type=doc_type,
            original_name=uploaded.filename[:255],
            stored_name=stored,
            uploaded_by=current_user.email,
        )
    )
    write_audit(
        "DOCUMENT_UPLOADED",
        "Employee document uploaded",
        candidate_id=employee.candidate_id,
        application_id=employee.application_id,
        details=f"{employee.employee_code}; {doc_type}",
        actor_type="admin",
        actor_name=current_user.email,
    )
    db.session.commit()
    flash("Document uploaded.", "success")
    return redirect(url_for("hr.employee_detail", employee_id=employee.employee_id))


@hr_bp.get("/employees/<int:employee_id>/documents/<int:document_id>")
@write_required
def download_document(employee_id: int, document_id: int):
    employee = _employee_or_404(employee_id)
    doc = db.session.get(EmployeeDocument, document_id) or abort(404)
    if doc.employee_id != employee.employee_id:
        abort(404)
    path = resolve_stored(employee_doc_dir(), doc.stored_name)
    if path is None:
        abort(404)
    write_audit(
        "DOCUMENT_DOWNLOADED",
        "Employee document downloaded",
        candidate_id=employee.candidate_id,
        application_id=employee.application_id,
        details=f"{employee.employee_code}; {doc.document_type}",
        actor_type="admin",
        actor_name=current_user.email,
    )
    db.session.commit()
    return send_file(path, as_attachment=True, download_name=doc.original_name)


@hr_bp.get("/letter-templates")
@login_required
def letter_templates():
    if not current_user.can_manage_settings():
        abort(403)
    return render_template(
        "admin/letter_templates.html",
        templates=LetterTemplate.query.order_by(LetterTemplate.letter_type, LetterTemplate.sort_order).all(),
    )


@hr_bp.post("/letter-templates/<int:template_id>")
@write_required
def save_letter_template(template_id: int):
    if not current_user.can_manage_settings():
        abort(403)
    row = db.session.get(LetterTemplate, template_id) or abort(404)
    row.title = (request.form.get("title") or row.title).strip()[:200]
    row.body = (request.form.get("body") or row.body).strip()
    row.is_active = request.form.get("is_active") == "1"
    db.session.commit()
    flash("Template updated.", "success")
    return redirect(url_for("hr.letter_templates"))
