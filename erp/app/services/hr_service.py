"""HR business logic — reads existing applications and syncs status back to the website store."""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from flask import current_app, session
from sqlalchemy import func
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.hr import (
    HrApplicationState,
    HrAppointmentLetter,
    HrDepartment,
    HrDesignation,
    HrEmployee,
    HrEmployeeDocument,
    HrEmployeeNumberSequence,
    HrEmploymentType,
    HrInterview,
    HrLetterTemplate,
    HrOfferLetter,
    HrWorkLocation,
)
from app.modules.shared.audit_service import AuditService
from app.services import recruitment_applications_service as rec
from app.services.email_service import EmailService
from app.services.hr_letters import build_letter_pdf, resolve_stored_file, save_pdf_bytes, storage_root
from app.services.hr_schema import ensure_hr_schema

PIPELINE_STAGES = (
    "New",
    "Under Review",
    "Shortlisted",
    "Interview",
    "Selected",
    "Offer",
    "Appointment",
    "Employee",
)
WEBSITE_STATUSES = (
    "New",
    "Under Review",
    "Shortlisted",
    "Interview Scheduled",
    "Interviewed",
    "Selected",
    "Rejected",
    "On Hold",
    "Offer",
    "Appointment",
    "Employee",
)
INTERVIEW_MODES = ("Office", "Phone", "Video Call")
INTERVIEW_RESULTS = ("Pending", "Recommended", "Not Recommended", "Further Review")
OFFER_STATUSES = ("Pending", "Accepted", "Declined", "Expired")
EMPLOYMENT_STATUSES = ("Active", "Probation", "Inactive")
DOCUMENT_TYPES = (
    "Resume",
    "Application PDF",
    "Offer Letter",
    "Appointment Letter",
    "Educational Documents",
    "Identity Documents",
    "Address Proof",
    "Other Documents",
)
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def bootstrap() -> None:
    ensure_hr_schema()


def actor_name() -> str:
    return (session.get("user_name") or "HR Admin").strip() or "HR Admin"


def _audit(action: str, entity_type: str, entity_id: int | None, old=None, new=None) -> None:
    try:
        AuditService().log(
            action_name=action[:100],
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old,
            new_value=new,
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception("HR audit write failed for %s", action)


def _parse_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _parse_money(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def masters() -> dict:
    bootstrap()
    return {
        "departments": HrDepartment.query.order_by(HrDepartment.Name).all(),
        "designations": HrDesignation.query.order_by(HrDesignation.Name).all(),
        "employment_types": HrEmploymentType.query.order_by(HrEmploymentType.Name).all(),
        "work_locations": HrWorkLocation.query.order_by(HrWorkLocation.Name).all(),
    }


def list_master(kind: str):
    bootstrap()
    model = {
        "departments": HrDepartment,
        "designations": HrDesignation,
        "employment-types": HrEmploymentType,
        "work-locations": HrWorkLocation,
    }.get(kind)
    if model is None:
        return None
    return model.query.order_by(model.Name).all()


def save_master(kind: str, name: str, row_id: int | None = None, is_active: bool = True):
    bootstrap()
    model = {
        "departments": HrDepartment,
        "designations": HrDesignation,
        "employment-types": HrEmploymentType,
        "work-locations": HrWorkLocation,
    }[kind]
    name = (name or "").strip()
    if not name:
        raise ValueError("Name is required.")
    row = model.query.get(row_id) if row_id else model()
    row.Name = name
    row.IsActive = bool(is_active)
    db.session.add(row)
    db.session.commit()
    return row


def overlay_map() -> dict[int, HrApplicationState]:
    bootstrap()
    return {row.ApplicationID: row for row in HrApplicationState.query.all()}


def employee_by_application() -> dict[int, HrEmployee]:
    bootstrap()
    return {row.ApplicationID: row for row in HrEmployee.query.filter(HrEmployee.ApplicationID.isnot(None)).all()}


def latest_interview_map() -> dict[int, HrInterview]:
    bootstrap()
    rows = HrInterview.query.order_by(HrInterview.InterviewID.desc()).all()
    out: dict[int, HrInterview] = {}
    for row in rows:
        out.setdefault(row.ApplicationID, row)
    return out


def latest_offer_map() -> dict[int, HrOfferLetter]:
    bootstrap()
    rows = HrOfferLetter.query.order_by(HrOfferLetter.OfferID.desc()).all()
    out: dict[int, HrOfferLetter] = {}
    for row in rows:
        if row.ApplicationID is not None:
            out.setdefault(row.ApplicationID, row)
    return out


def latest_appointment_map() -> dict[int, HrAppointmentLetter]:
    bootstrap()
    rows = HrAppointmentLetter.query.order_by(HrAppointmentLetter.AppointmentID.desc()).all()
    out: dict[int, HrAppointmentLetter] = {}
    for row in rows:
        if row.ApplicationID is not None:
            out.setdefault(row.ApplicationID, row)
    return out


def website_status_to_pipeline(status: str | None) -> str:
    raw = (status or "New").strip()
    mapping = {
        "New": "New",
        "Under Review": "Under Review",
        "Shortlisted": "Shortlisted",
        "Interview Scheduled": "Interview",
        "Interview": "Interview",
        "Interviewed": "Interview",
        "Selected": "Selected",
        "Offer": "Offer",
        "Offer Issued": "Offer",
        "Offer Accepted": "Offer",
        "Appointment": "Appointment",
        "Appointment Issued": "Appointment",
        "Employee": "Employee",
        "Rejected": "Rejected",
    }
    return mapping.get(raw, raw or "New")


def push_status_to_website(application_id: int, status: str, reason: str = "") -> None:
    """Keep the public application-status page in sync with HR overlay."""
    try:
        rec.update_application_status(
            application_id,
            status,
            changed_by=actor_name(),
            reason=reason,
        )
    except Exception:
        current_app.logger.exception(
            "Could not sync website application status for application_id=%s",
            application_id,
        )


def _touch_overlay(application_id: int, application_number: str | None, status: str) -> None:
    overlay = HrApplicationState.query.get(application_id)
    if overlay is None:
        overlay = HrApplicationState(
            ApplicationID=application_id,
            ApplicationNumber=application_number,
        )
    overlay.ApplicationNumber = application_number
    overlay.OverlayStatus = status
    overlay.UpdatedDate = datetime.utcnow()
    overlay.UpdatedBy = actor_name()
    db.session.add(overlay)


def effective_status(application: dict, overlay: HrApplicationState | None) -> str:
    if overlay and overlay.OverlayStatus:
        return overlay.OverlayStatus
    return application.get("application_status") or "New"


def pipeline_stage(
    application: dict,
    overlay: HrApplicationState | None,
    employee: HrEmployee | None,
    offer: HrOfferLetter | None,
    appointment: HrAppointmentLetter | None,
) -> str:
    if appointment:
        return "Employee"
    if offer:
        return "Offer"
    status = website_status_to_pipeline(effective_status(application, overlay))
    if employee and status == "Selected":
        return "Selected"
    return status


def enrich_application(row: dict) -> dict:
    overlays = overlay_map()
    employees = employee_by_application()
    interviews = latest_interview_map()
    offers = latest_offer_map()
    appointments = latest_appointment_map()
    return _enrich_one(row, overlays, employees, interviews, offers, appointments)


def _enrich_one(
    row: dict,
    overlays,
    employees,
    interviews,
    offers,
    appointments,
) -> dict:
    app_id = int(row["application_id"])
    overlay = overlays.get(app_id)
    employee = employees.get(app_id)
    interview = interviews.get(app_id)
    offer = offers.get(app_id)
    appointment = appointments.get(app_id)
    data = dict(row)
    data["website_status"] = row.get("application_status")
    data["effective_status"] = effective_status(row, overlay)
    data["pipeline_stage"] = pipeline_stage(row, overlay, employee, offer, appointment)
    data["employee"] = employee
    data["employee_code"] = employee.EmployeeCode if employee else None
    data["interview"] = interview
    data["interview_status"] = interview.InterviewResult if interview else None
    data["offer"] = offer
    data["offer_status"] = offer.OfferStatus if offer else None
    data["appointment"] = appointment
    data["employee_status"] = employee.EmploymentStatus if employee else None
    data["can_convert"] = data["effective_status"] == "Selected" and employee is None
    return data


def list_enriched_applications(search: str = "", status: str = "") -> list[dict]:
    bootstrap()
    available, message = rec.store_available()
    if not available:
        raise rec.RecruitmentStoreError(message)
    rows = rec.list_applications(search=search, status="")
    overlays = overlay_map()
    employees = employee_by_application()
    interviews = latest_interview_map()
    offers = latest_offer_map()
    appointments = latest_appointment_map()
    enriched = []
    for row in rows:
        item = _enrich_one(row, overlays, employees, interviews, offers, appointments)
        enriched.append(_heal_website_status(row, item))
    if status:
        status_l = status.strip().lower()
        enriched = [
            row
            for row in enriched
            if (row["effective_status"] or "").lower() == status_l
            or (row["pipeline_stage"] or "").lower() == status_l
        ]
    return enriched


def _heal_website_status(row: dict, enriched: dict) -> dict:
    desired = rec.preferred_website_status(
        enriched.get("effective_status"),
        enriched.get("pipeline_stage"),
    )
    if not rec.website_needs_status_sync(row.get("application_status"), desired):
        return enriched
    push_status_to_website(
        int(row["application_id"]),
        desired,
        "Synced from HR overlay",
    )
    enriched["website_status"] = rec.website_status_for_store(desired)
    return enriched


def get_enriched_application(application_id: int) -> dict | None:
    bootstrap()
    raw = rec.get_application(application_id)
    if raw is None:
        return None
    enriched = enrich_application(raw)
    before = raw.get("application_status")
    enriched = _heal_website_status(raw, enriched)
    if enriched.get("website_status") != before:
        raw = rec.get_application(application_id) or raw
        return enrich_application(raw)
    return enriched


def set_application_status(application_id: int, new_status: str, reason: str = "") -> dict:
    bootstrap()
    raw = rec.get_application(application_id)
    if raw is None:
        raise ValueError("Application not found.")
    new_status = (new_status or "").strip()
    if new_status not in WEBSITE_STATUSES and new_status not in PIPELINE_STAGES:
        raise ValueError("Invalid application status.")
    if new_status == "Interview":
        new_status = "Interview Scheduled"
    overlay = HrApplicationState.query.get(application_id)
    old = overlay.OverlayStatus if overlay else raw.get("application_status")
    if overlay is None:
        overlay = HrApplicationState(
            ApplicationID=application_id,
            ApplicationNumber=raw.get("application_number"),
        )
    overlay.ApplicationNumber = raw.get("application_number")
    overlay.OverlayStatus = new_status
    overlay.UpdatedDate = datetime.utcnow()
    overlay.UpdatedBy = actor_name()
    db.session.add(overlay)
    db.session.commit()
    push_status_to_website(application_id, new_status, reason or "Updated from HR")
    action = "CANDIDATE_SELECTED" if new_status == "Selected" else "APPLICATION_STATUS_CHANGED"
    _audit(
        action,
        "HrApplication",
        application_id,
        old={"status": old, "reason": reason},
        new={"status": new_status, "application_number": raw.get("application_number")},
    )
    return get_enriched_application(application_id) or {}


def next_employee_code() -> str:
    bootstrap()
    year = date.today().year
    row = (
        HrEmployeeNumberSequence.query.filter_by(Prefix="EMP", Year=year)
        .with_for_update()
        .first()
    )
    if row is None:
        row = HrEmployeeNumberSequence(Prefix="EMP", Year=year, LastNumber=0)
        db.session.add(row)
        db.session.flush()
    row.LastNumber = int(row.LastNumber or 0) + 1
    db.session.flush()
    return f"EMP-{year}-{row.LastNumber:05d}"


def _education_snapshot(application: dict) -> dict:
    rows = application.get("education") or []
    highest = next((r for r in rows if (r.get("education_type") or "").lower() == "highest"), None)
    last = next((r for r in rows if (r.get("education_type") or "").lower() == "last"), None)
    pick = highest or last or (rows[0] if rows else {})
    return {
        "HighestQualification": (highest or pick).get("qualification") if (highest or pick) else None,
        "LastQualification": (last or pick).get("qualification") if (last or pick) else None,
        "Degree": (pick or {}).get("qualification"),
        "UniversityBoard": (pick or {}).get("university_board"),
        "PassingYear": str((pick or {}).get("passing_year") or "") or None,
        "PercentageCgpa": (pick or {}).get("percentage_cgpa"),
    }


def _experience_snapshot(application: dict) -> dict:
    exp = application.get("experience") or {}
    years = exp.get("sales_experience_years")
    months = exp.get("sales_experience_months")
    sales = None
    if years not in (None, "") or months not in (None, ""):
        sales = f"{years or 0} years {months or 0} months"
    return {
        "TotalExperience": exp.get("total_work_experience"),
        "SalesExperience": sales,
        "PreviousCompany": exp.get("previous_company"),
        "PreviousDesignation": exp.get("previous_designation"),
        "PreviousResponsibilities": exp.get("responsibilities"),
        "OtherExperience": " · ".join(
            part
            for part in (
                f"Software sales: {exp.get('software_sales_experience')}"
                if exp.get("software_sales_experience")
                else "",
                f"B2B: {exp.get('b2b_sales_experience')}" if exp.get("b2b_sales_experience") else "",
                f"Tax/ERP: {exp.get('tax_accounting_erp_sales_experience')}"
                if exp.get("tax_accounting_erp_sales_experience")
                else "",
            )
            if part
        )
        or None,
    }


def convert_to_employee(application_id: int) -> HrEmployee:
    bootstrap()
    application = rec.get_application(application_id)
    if application is None:
        raise ValueError("Application not found.")
    existing = HrEmployee.query.filter_by(ApplicationID=application_id).first()
    if existing:
        return existing
    edu = _education_snapshot(application)
    exp = _experience_snapshot(application)
    employee = HrEmployee(
        EmployeeCode=next_employee_code(),
        ApplicationID=application_id,
        ApplicationNumber=application.get("application_number"),
        CandidateID=application.get("candidate_id"),
        Name=application.get("name") or "Candidate",
        FatherName=application.get("father_name"),
        DateOfBirth=_parse_date(application.get("dob")),
        Gender=application.get("gender"),
        Mobile=application.get("mobile"),
        Email=application.get("email"),
        Address=application.get("address"),
        City=application.get("city"),
        State=application.get("state"),
        PinCode=application.get("pin_code"),
        EmploymentStatus="Active",
        CreatedBy=actor_name(),
        **edu,
        **exp,
    )
    db.session.add(employee)
    overlay = HrApplicationState.query.get(application_id)
    if overlay is None:
        overlay = HrApplicationState(
            ApplicationID=application_id,
            ApplicationNumber=application.get("application_number"),
            OverlayStatus="Selected",
            UpdatedBy=actor_name(),
        )
        db.session.add(overlay)
    db.session.commit()
    push_status_to_website(application_id, "Selected", "Converted to employee")
    _audit(
        "EMPLOYEE_CREATED",
        "HrEmployee",
        employee.EmployeeID,
        new={
            "employee_code": employee.EmployeeCode,
            "application_number": employee.ApplicationNumber,
            "application_id": application_id,
        },
    )
    return employee


def employee_detail(employee_id: int) -> dict | None:
    bootstrap()
    employee = HrEmployee.query.get(employee_id)
    if employee is None:
        return None
    return decorate_employee(employee)


def decorate_employee(employee: HrEmployee) -> dict:
    data = {col.name: getattr(employee, col.name) for col in employee.__table__.columns}
    for key in ("DateOfBirth", "JoiningDate", "ProbationEndDate"):
        value = data.get(key)
        if hasattr(value, "strftime"):
            data[key] = value.strftime("%Y-%m-%d")
    dept = HrDepartment.query.get(employee.DepartmentID) if employee.DepartmentID else None
    desig = HrDesignation.query.get(employee.DesignationID) if employee.DesignationID else None
    emp_type = HrEmploymentType.query.get(employee.EmploymentTypeID) if employee.EmploymentTypeID else None
    loc = HrWorkLocation.query.get(employee.WorkLocationID) if employee.WorkLocationID else None
    data["department_name"] = dept.Name if dept else None
    data["designation_name"] = desig.Name if desig else None
    data["employment_type_name"] = emp_type.Name if emp_type else None
    data["location_name"] = loc.Name if loc else None
    data["offers"] = (
        HrOfferLetter.query.filter_by(EmployeeID=employee.EmployeeID)
        .order_by(HrOfferLetter.OfferID.desc())
        .all()
    )
    data["appointments"] = (
        HrAppointmentLetter.query.filter_by(EmployeeID=employee.EmployeeID)
        .order_by(HrAppointmentLetter.AppointmentID.desc())
        .all()
    )
    data["documents"] = (
        HrEmployeeDocument.query.filter_by(EmployeeID=employee.EmployeeID)
        .order_by(HrEmployeeDocument.UploadedAt.desc())
        .all()
    )
    data["latest_offer"] = data["offers"][0] if data["offers"] else None
    data["latest_appointment"] = data["appointments"][0] if data["appointments"] else None
    return data


def list_employees() -> list[dict]:
    bootstrap()
    return [decorate_employee(row) for row in HrEmployee.query.order_by(HrEmployee.EmployeeID.desc()).all()]


def update_employee(employee_id: int, form: dict) -> HrEmployee:
    bootstrap()
    employee = HrEmployee.query.get(employee_id)
    if employee is None:
        raise ValueError("Employee not found.")
    old = {"EmploymentStatus": employee.EmploymentStatus, "DepartmentID": employee.DepartmentID}
    employee.FatherName = (form.get("father_name") or employee.FatherName or "").strip() or employee.FatherName
    employee.DateOfBirth = _parse_date(form.get("date_of_birth")) or employee.DateOfBirth
    employee.Gender = (form.get("gender") or employee.Gender or "").strip() or employee.Gender
    employee.Mobile = (form.get("mobile") or employee.Mobile or "").strip() or employee.Mobile
    employee.Email = (form.get("email") or employee.Email or "").strip() or employee.Email
    employee.Address = (form.get("address") or employee.Address or "").strip() or employee.Address
    employee.City = (form.get("city") or employee.City or "").strip() or employee.City
    employee.State = (form.get("state") or employee.State or "").strip() or employee.State
    employee.PinCode = (form.get("pin_code") or employee.PinCode or "").strip() or employee.PinCode
    employee.JoiningDate = _parse_date(form.get("joining_date"))
    employee.DepartmentID = int(form["department_id"]) if form.get("department_id") else None
    employee.DesignationID = int(form["designation_id"]) if form.get("designation_id") else None
    employee.ReportingManager = (form.get("reporting_manager") or "").strip() or None
    employee.EmploymentTypeID = int(form["employment_type_id"]) if form.get("employment_type_id") else None
    employee.WorkLocationID = int(form["work_location_id"]) if form.get("work_location_id") else None
    employee.ProbationPeriod = (form.get("probation_period") or "").strip() or None
    employee.ProbationEndDate = _parse_date(form.get("probation_end_date"))
    if not employee.ProbationEndDate and employee.JoiningDate and employee.ProbationPeriod:
        employee.ProbationEndDate = _guess_probation_end(employee.JoiningDate, employee.ProbationPeriod)
    status = (form.get("employment_status") or employee.EmploymentStatus or "Active").strip()
    if status not in EMPLOYMENT_STATUSES:
        status = employee.EmploymentStatus
    employee.EmploymentStatus = status
    employee.SalaryCtc = _parse_money(form.get("salary_ctc"))
    employee.SalaryFrequency = (form.get("salary_frequency") or "").strip() or None
    employee.UpdatedDate = datetime.utcnow()
    employee.UpdatedBy = actor_name()
    db.session.commit()
    _audit("EMPLOYEE_UPDATED", "HrEmployee", employee.EmployeeID, old=old, new=form)
    if old.get("EmploymentStatus") != employee.EmploymentStatus:
        _audit(
            "EMPLOYEE_STATUS_CHANGED",
            "HrEmployee",
            employee.EmployeeID,
            old={"status": old.get("EmploymentStatus")},
            new={"status": employee.EmploymentStatus},
        )
    return employee


def _guess_probation_end(joining: date, period: str) -> date | None:
    text = period.lower()
    months = 6
    match = re.search(r"(\d+)", text)
    if match:
        months = int(match.group(1))
        if "year" in text:
            months *= 12
        elif "week" in text:
            return joining + timedelta(weeks=months)
        elif "day" in text:
            return joining + timedelta(days=months)
    year = joining.year + ((joining.month - 1 + months) // 12)
    month = (joining.month - 1 + months) % 12 + 1
    day = min(joining.day, 28)
    return date(year, month, day)


def save_interview(form: dict, interview_id: int | None = None) -> HrInterview:
    bootstrap()
    application_id = int(form.get("application_id") or 0)
    application = rec.get_application(application_id)
    if application is None:
        raise ValueError("Application not found.")
    result = (form.get("interview_result") or "Pending").strip()
    if result not in INTERVIEW_RESULTS:
        result = "Pending"
    mode = (form.get("interview_mode") or "").strip()
    if mode and mode not in INTERVIEW_MODES:
        raise ValueError("Invalid interview mode.")
    row = HrInterview.query.get(interview_id) if interview_id else HrInterview(CreatedBy=actor_name())
    created = interview_id is None
    row.ApplicationID = application_id
    row.ApplicationNumber = application.get("application_number")
    row.CandidateName = application.get("name")
    row.InterviewDate = _parse_date(form.get("interview_date"))
    row.InterviewTime = (form.get("interview_time") or "").strip() or None
    row.InterviewMode = mode or None
    row.Interviewer = (form.get("interviewer") or "").strip() or None
    row.InterviewLocation = (form.get("interview_location") or "").strip() or None
    row.MeetingLink = (form.get("meeting_link") or "").strip() or None
    row.InterviewNotes = (form.get("interview_notes") or "").strip() or None
    row.InterviewResult = result
    row.UpdatedDate = datetime.utcnow()
    row.UpdatedBy = actor_name()
    db.session.add(row)
    website_push = None
    if created:
        set_quietly = HrApplicationState.query.get(application_id)
        if set_quietly is None:
            db.session.add(
                HrApplicationState(
                    ApplicationID=application_id,
                    ApplicationNumber=application.get("application_number"),
                    OverlayStatus="Interview Scheduled",
                    UpdatedBy=actor_name(),
                )
            )
        elif website_status_to_pipeline(set_quietly.OverlayStatus) in {"New", "Under Review", "Shortlisted"}:
            set_quietly.OverlayStatus = "Interview Scheduled"
            set_quietly.UpdatedDate = datetime.utcnow()
            set_quietly.UpdatedBy = actor_name()
        website_push = ("Interview Scheduled", "Interview scheduled from HR")
    elif result in {"Recommended", "Not Recommended", "Further Review"}:
        overlay = HrApplicationState.query.get(application_id)
        stage = website_status_to_pipeline(overlay.OverlayStatus if overlay else None)
        if stage in {"New", "Under Review", "Shortlisted", "Interview"}:
            if overlay is None:
                _touch_overlay(application_id, application.get("application_number"), "Interviewed")
            else:
                overlay.OverlayStatus = "Interviewed"
                overlay.UpdatedDate = datetime.utcnow()
                overlay.UpdatedBy = actor_name()
            website_push = ("Interviewed", "Interview result recorded")
    db.session.commit()
    if website_push:
        push_status_to_website(application_id, website_push[0], website_push[1])
    _audit(
        "INTERVIEW_CREATED" if created else "INTERVIEW_UPDATED",
        "HrInterview",
        row.InterviewID,
        new={
            "application_number": row.ApplicationNumber,
            "result": row.InterviewResult,
            "date": str(row.InterviewDate or ""),
        },
    )
    return row


def list_interviews() -> list[HrInterview]:
    bootstrap()
    return HrInterview.query.order_by(HrInterview.InterviewDate.desc(), HrInterview.InterviewID.desc()).all()


def generate_offer(employee_id: int) -> HrOfferLetter:
    bootstrap()
    employee = employee_detail(employee_id)
    if employee is None:
        raise ValueError("Employee not found.")
    version = (
        db.session.query(func.coalesce(func.max(HrOfferLetter.Version), 0))
        .filter(HrOfferLetter.EmployeeID == employee_id)
        .scalar()
        or 0
    ) + 1
    offer_number = f"OFF-{employee['EmployeeCode']}-{version:02d}"
    stored = f"offer_{employee_id}_{version}_{uuid.uuid4().hex[:8]}.pdf"
    pdf = build_letter_pdf(title="OFFER LETTER", employee=employee, letter_type="offer")
    save_pdf_bytes(stored, pdf)
    row = HrOfferLetter(
        EmployeeID=employee_id,
        ApplicationID=employee.get("ApplicationID"),
        ApplicationNumber=employee.get("ApplicationNumber"),
        OfferNumber=offer_number,
        Version=version,
        OfferDate=date.today(),
        JoiningDate=employee.get("JoiningDate"),
        SalaryCtc=employee.get("SalaryCtc"),
        ProbationPeriod=employee.get("ProbationPeriod"),
        OfferStatus="Pending",
        StoredName=stored,
        OriginalName=f"{offer_number}.pdf",
        GeneratedBy=actor_name(),
    )
    db.session.add(row)
    application_id = employee.get("ApplicationID")
    if application_id:
        _touch_overlay(int(application_id), employee.get("ApplicationNumber"), "Offer Issued")
    db.session.commit()
    if application_id:
        push_status_to_website(int(application_id), "Offer Issued", "Offer letter generated")
    _audit(
        "OFFER_LETTER_GENERATED",
        "HrOfferLetter",
        row.OfferID,
        new={"offer_number": offer_number, "employee_code": employee["EmployeeCode"]},
    )
    return row


def set_offer_status(offer_id: int, status: str) -> HrOfferLetter:
    bootstrap()
    row = HrOfferLetter.query.get(offer_id)
    if row is None:
        raise ValueError("Offer letter not found.")
    status = (status or "").strip()
    if status not in OFFER_STATUSES:
        raise ValueError("Invalid offer status.")
    old = row.OfferStatus
    row.OfferStatus = status
    if status == "Accepted":
        row.AcceptedAt = datetime.utcnow()
        if row.ApplicationID:
            _touch_overlay(int(row.ApplicationID), row.ApplicationNumber, "Offer Accepted")
    elif status == "Declined" and row.ApplicationID:
        _touch_overlay(int(row.ApplicationID), row.ApplicationNumber, "Rejected")
    db.session.commit()
    if row.ApplicationID:
        if status == "Accepted":
            push_status_to_website(int(row.ApplicationID), "Offer Accepted", "Offer accepted")
        elif status == "Declined":
            push_status_to_website(int(row.ApplicationID), "Rejected", "Offer declined")
    _audit("OFFER_STATUS_CHANGED", "HrOfferLetter", row.OfferID, old={"status": old}, new={"status": status})
    if status == "Accepted":
        _audit("OFFER_ACCEPTED", "HrOfferLetter", row.OfferID, new={"offer_number": row.OfferNumber})
    elif status == "Declined":
        _audit("OFFER_DECLINED", "HrOfferLetter", row.OfferID, new={"offer_number": row.OfferNumber})
    return row


def generate_appointment(employee_id: int) -> HrAppointmentLetter:
    bootstrap()
    employee = employee_detail(employee_id)
    if employee is None:
        raise ValueError("Employee not found.")
    latest = employee.get("latest_offer")
    if latest is None or latest.OfferStatus != "Accepted":
        raise ValueError("Appointment letter can be generated only after the offer is accepted.")
    version = (
        db.session.query(func.coalesce(func.max(HrAppointmentLetter.Version), 0))
        .filter(HrAppointmentLetter.EmployeeID == employee_id)
        .scalar()
        or 0
    ) + 1
    number = f"APT-{employee['EmployeeCode']}-{version:02d}"
    stored = f"appointment_{employee_id}_{version}_{uuid.uuid4().hex[:8]}.pdf"
    pdf = build_letter_pdf(title="APPOINTMENT LETTER", employee=employee, letter_type="appointment")
    save_pdf_bytes(stored, pdf)
    row = HrAppointmentLetter(
        EmployeeID=employee_id,
        ApplicationID=employee.get("ApplicationID"),
        ApplicationNumber=employee.get("ApplicationNumber"),
        AppointmentNumber=number,
        Version=version,
        AppointmentDate=date.today(),
        JoiningDate=employee.get("JoiningDate"),
        StoredName=stored,
        OriginalName=f"{number}.pdf",
        IssuedBy=actor_name(),
    )
    db.session.add(row)
    if employee.get("ApplicationID"):
        _touch_overlay(
            int(employee["ApplicationID"]),
            employee.get("ApplicationNumber"),
            "Appointment Issued",
        )
    db.session.commit()
    if employee.get("ApplicationID"):
        push_status_to_website(
            int(employee["ApplicationID"]),
            "Appointment Issued",
            "Appointment letter generated",
        )
    _audit(
        "APPOINTMENT_LETTER_GENERATED",
        "HrAppointmentLetter",
        row.AppointmentID,
        new={"appointment_number": number, "employee_code": employee["EmployeeCode"]},
    )
    return row


def send_letter_email(*, kind: str, row_id: int) -> tuple[bool, str]:
    bootstrap()
    if kind == "offer":
        row = HrOfferLetter.query.get(row_id)
        employee = employee_detail(row.EmployeeID) if row else None
        title = "Offer Letter"
    else:
        row = HrAppointmentLetter.query.get(row_id)
        employee = employee_detail(row.EmployeeID) if row else None
        title = "Appointment Letter"
    if row is None or employee is None:
        return False, "Letter not found."
    to_email = (employee.get("Email") or "").strip()
    if not to_email:
        return False, "Employee email is missing."
    path = resolve_stored_file(row.StoredName or "")
    if path is None:
        return False, "Letter PDF is not available."
    ok, err = EmailService().send_html(
        to_email,
        f"JTCS Xpert — {title} — {employee.get('EmployeeCode')}",
        f"<p>Dear {employee.get('Name')},</p><p>Please find attached your {title.lower()} from JTCS Xpert.</p>",
        attachments=[(row.OriginalName or path.name, path.read_bytes(), "application/pdf")],
    )
    row.EmailedAt = datetime.utcnow()
    row.EmailedTo = to_email
    row.EmailStatus = "Sent" if ok else "Failed"
    db.session.commit()
    return ok, err or ("Sent" if ok else "Unable to send email.")


def upload_employee_document(employee_id: int, document_type: str, file_storage) -> HrEmployeeDocument:
    bootstrap()
    employee = HrEmployee.query.get(employee_id)
    if employee is None:
        raise ValueError("Employee not found.")
    if document_type not in DOCUMENT_TYPES:
        document_type = "Other Documents"
    if not file_storage or not file_storage.filename:
        raise ValueError("Choose a file to upload.")
    original = secure_filename(file_storage.filename) or "document.bin"
    stored = f"doc_{employee_id}_{uuid.uuid4().hex}_{SAFE_NAME_RE.sub('_', original)[:80]}"
    target = storage_root() / stored
    file_storage.save(target)
    row = HrEmployeeDocument(
        EmployeeID=employee_id,
        ApplicationID=employee.ApplicationID,
        DocumentType=document_type,
        OriginalName=original,
        StoredName=stored,
        MimeType=file_storage.mimetype,
        FileSizeBytes=target.stat().st_size,
        UploadedBy=actor_name(),
    )
    db.session.add(row)
    db.session.commit()
    _audit(
        "DOCUMENT_UPLOADED",
        "HrEmployeeDocument",
        row.DocumentID,
        new={"employee_id": employee_id, "type": document_type, "name": original},
    )
    return row


def mark_document_access(document_id: int, action: str) -> None:
    _audit(action, "HrEmployeeDocument", document_id, new={"access": action})


def employee_timeline(employee_id: int) -> list[dict]:
    bootstrap()
    employee = HrEmployee.query.get(employee_id)
    if employee is None:
        return []
    events: list[dict] = []
    application = None
    if employee.ApplicationID:
        try:
            application = rec.get_application(employee.ApplicationID)
        except rec.RecruitmentStoreError:
            application = None
    if application and application.get("submitted_at"):
        events.append(
            {
                "at": application.get("submitted_at"),
                "title": "Application Submitted",
                "detail": application.get("application_number"),
            }
        )
        for item in application.get("history") or []:
            label = {
                "Shortlisted": "Shortlisted",
                "Interview Scheduled": "Interview Scheduled",
                "Selected": "Selected",
            }.get(item.get("new_status"))
            if label:
                events.append({"at": item.get("changed_at"), "title": label, "detail": item.get("change_reason")})
    for interview in HrInterview.query.filter_by(ApplicationID=employee.ApplicationID).all():
        if interview.InterviewDate:
            events.append(
                {
                    "at": datetime.combine(interview.InterviewDate, datetime.min.time()),
                    "title": "Interview Scheduled",
                    "detail": f"{interview.InterviewMode or ''} {interview.InterviewResult}",
                }
            )
        if interview.InterviewResult and interview.InterviewResult != "Pending":
            events.append(
                {
                    "at": interview.UpdatedDate or interview.CreatedDate,
                    "title": "Interview Completed",
                    "detail": interview.InterviewResult,
                }
            )
    events.append(
        {
            "at": employee.CreatedDate,
            "title": "Employee Created",
            "detail": employee.EmployeeCode,
        }
    )
    for offer in HrOfferLetter.query.filter_by(EmployeeID=employee_id).all():
        events.append({"at": offer.GeneratedAt, "title": "Offer Generated", "detail": offer.OfferNumber})
        if offer.OfferStatus == "Accepted" and offer.AcceptedAt:
            events.append({"at": offer.AcceptedAt, "title": "Offer Accepted", "detail": offer.OfferNumber})
    for appt in HrAppointmentLetter.query.filter_by(EmployeeID=employee_id).all():
        events.append({"at": appt.IssuedAt, "title": "Appointment Letter Issued", "detail": appt.AppointmentNumber})
    events = [e for e in events if e.get("at")]
    events.sort(key=lambda item: str(item["at"]))
    return events


def dashboard_kpis() -> dict:
    bootstrap()
    applications: list[dict] = []
    jobs: list[dict] = []
    source_rows: list[dict] = []
    store_ok, store_message = rec.store_available()
    if store_ok:
        try:
            applications = list_enriched_applications()
            jobs = rec.list_jobs()
            source_rows = rec.source_counts()
        except Exception as exc:
            store_message = str(exc)
    interviews = list_interviews()
    employees = HrEmployee.query.all()
    offers = HrOfferLetter.query.all()
    appointments = HrAppointmentLetter.query.all()
    open_jobs = sum(1 for job in jobs if (job.get("status") or "").lower() == "open")
    selected = sum(1 for row in applications if row["pipeline_stage"] == "Selected" or row["effective_status"] == "Selected")
    funnel_counts = {stage: 0 for stage in PIPELINE_STAGES}
    for row in applications:
        stage = row["pipeline_stage"]
        if stage in funnel_counts:
            funnel_counts[stage] += 1
    total_apps = len(applications)
    funnel = []
    previous = total_apps
    for stage in ("New", "Shortlisted", "Interview", "Selected", "Offer", "Appointment", "Employee"):
        count = funnel_counts.get(stage, 0)
        if stage == "New":
            count = total_apps
        pct = round((count / previous) * 100, 1) if previous else None
        funnel.append({"stage": stage, "count": count, "conversion": pct})
        previous = count or previous
    return {
        "store_ok": store_ok,
        "store_message": store_message,
        "open_jobs": open_jobs,
        "applications": total_apps,
        "interviews": len(interviews),
        "selected": selected,
        "offers_pending": sum(1 for row in offers if row.OfferStatus == "Pending"),
        "employees": len(employees),
        "appointments_issued": len(appointments),
        "funnel": funnel,
        "funnel_counts": funnel_counts,
        "sources": source_rows,
        "source_conversion": _source_conversion(applications),
    }


def _source_conversion(applications: list[dict]) -> list[dict]:
    buckets: dict[str, dict[str, int]] = {}
    for row in applications:
        source = (row.get("source") or "Other").strip() or "Other"
        bucket = buckets.setdefault(source, {"source": source, "applications": 0, "interview": 0, "selected": 0})
        bucket["applications"] += 1
        if row["pipeline_stage"] in {"Interview", "Selected", "Offer", "Appointment", "Employee"}:
            bucket["interview"] += 1
        if row["pipeline_stage"] in {"Selected", "Offer", "Appointment", "Employee"} or row["effective_status"] == "Selected":
            bucket["selected"] += 1
    return list(buckets.values())


def action_items() -> list[dict]:
    bootstrap()
    items = []
    today = date.today()
    interviews_today = [
        row
        for row in list_interviews()
        if row.InterviewDate == today
    ]
    items.append(
        {
            "tone": "danger",
            "title": "Interviews Today",
            "count": len(interviews_today),
            "url": "/hr/interviews?date=today",
        }
    )
    pending_review = []
    try:
        pending_review = [
            row
            for row in list_enriched_applications()
            if row["effective_status"] in {"New", "Under Review"}
        ]
    except rec.RecruitmentStoreError:
        pending_review = []
    items.append(
        {
            "tone": "warning",
            "title": "Applications Pending Review",
            "count": len(pending_review),
            "url": "/hr/applications?status=New",
        }
    )
    pending_offers = HrOfferLetter.query.filter_by(OfferStatus="Pending").count()
    items.append(
        {
            "tone": "warning",
            "title": "Offers Awaiting Acceptance",
            "count": pending_offers,
            "url": "/hr/letters/offers?status=Pending",
        }
    )
    accepted_no_appt = 0
    for offer in HrOfferLetter.query.filter_by(OfferStatus="Accepted").all():
        if not HrAppointmentLetter.query.filter_by(EmployeeID=offer.EmployeeID).first():
            accepted_no_appt += 1
    items.append(
        {
            "tone": "warning",
            "title": "Appointment Letters Pending",
            "count": accepted_no_appt,
            "url": "/hr/letters/appointments",
        }
    )
    missing_docs = 0
    for employee in HrEmployee.query.all():
        if not HrEmployeeDocument.query.filter_by(EmployeeID=employee.EmployeeID).first():
            missing_docs += 1
    items.append(
        {
            "tone": "warning",
            "title": "Employee Documents Pending",
            "count": missing_docs,
            "url": "/hr/employees/documents",
        }
    )
    return items


def probation_rows() -> list[dict]:
    bootstrap()
    today = date.today()
    rows = []
    for employee in HrEmployee.query.order_by(HrEmployee.Name).all():
        if not employee.ProbationEndDate:
            continue
        remaining = (employee.ProbationEndDate - today).days
        if remaining < 0:
            status = "Probation Ended"
        elif remaining <= 15:
            status = "Review Due Soon"
        else:
            status = "On Probation"
        rows.append(
            {
                "employee": decorate_employee(employee),
                "days_remaining": remaining,
                "status": status,
            }
        )
    return rows


def list_calendar_events(start: datetime, end: datetime) -> list[dict]:
    bootstrap()
    events = []
    for row in HrInterview.query.all():
        if not row.InterviewDate:
            continue
        at = datetime.combine(row.InterviewDate, datetime.min.time())
        if start <= at <= end:
            events.append(
                {
                    "event_type": "hr_interview",
                    "event_id": row.InterviewID,
                    "title": f"Interview — {row.CandidateName or row.ApplicationNumber}",
                    "starts_at": at,
                    "status": row.InterviewResult,
                    "url": f"/hr/interviews/{row.InterviewID}",
                }
            )
    for employee in HrEmployee.query.all():
        for label, value, key in (
            ("Joining Date", employee.JoiningDate, "joining"),
            ("Probation End Date", employee.ProbationEndDate, "probation"),
        ):
            if not value:
                continue
            at = datetime.combine(value, datetime.min.time())
            if start <= at <= end:
                events.append(
                    {
                        "event_type": f"hr_{key}",
                        "event_id": employee.EmployeeID,
                        "title": f"{label} — {employee.Name}",
                        "starts_at": at,
                        "status": employee.EmploymentStatus,
                        "url": f"/hr/employees/{employee.EmployeeID}",
                    }
                )
    for offer in HrOfferLetter.query.all():
        if offer.OfferDate:
            at = datetime.combine(offer.OfferDate + timedelta(days=14), datetime.min.time())
            if start <= at <= end and offer.OfferStatus == "Pending":
                events.append(
                    {
                        "event_type": "hr_offer_expiry",
                        "event_id": offer.OfferID,
                        "title": f"Offer Expiry — {offer.OfferNumber}",
                        "starts_at": at,
                        "status": offer.OfferStatus,
                        "url": "/hr/letters/offers",
                    }
                )
    for appt in HrAppointmentLetter.query.all():
        if not appt.AppointmentDate:
            continue
        at = datetime.combine(appt.AppointmentDate, datetime.min.time())
        if start <= at <= end:
            events.append(
                {
                    "event_type": "hr_appointment",
                    "event_id": appt.AppointmentID,
                    "title": f"Appointment — {appt.AppointmentNumber}",
                    "starts_at": at,
                    "status": "Issued",
                    "url": "/hr/letters/appointments",
                }
            )
    return events


def export_csv(headers: list[str], rows: list[list]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue()


def letter_templates() -> list[HrLetterTemplate]:
    bootstrap()
    return HrLetterTemplate.query.order_by(
        HrLetterTemplate.LetterType, HrLetterTemplate.SortOrder, HrLetterTemplate.TemplateID
    ).all()


def save_letter_template(template_id: int, title: str, body: str, is_active: bool) -> HrLetterTemplate:
    bootstrap()
    row = HrLetterTemplate.query.get(template_id)
    if row is None:
        raise ValueError("Template not found.")
    row.Title = (title or row.Title).strip()
    row.Body = body or row.Body
    row.IsActive = bool(is_active)
    db.session.commit()
    return row
