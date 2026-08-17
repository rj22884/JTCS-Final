"""Application number generation, duplicate checks, and submission."""

from __future__ import annotations

import logging
from datetime import datetime

from flask import current_app
from sqlalchemy import func

from recruitment.application_pdf import store_final_pdf
from recruitment.audit import write_audit
from recruitment.candidate_status import normalize_email, normalize_mobile, public_status
from recruitment.emailer import send_admin_notification, send_candidate_acknowledgement
from recruitment.notifications import notify_candidate_status
from recruitment.extensions import db
from recruitment.job_window import CLOSED_MESSAGE, is_job_application_open
from recruitment.models import (
    ApplicationNumberSequence,
    ApplicationStatusHistory,
    Candidate,
    CandidateEducation,
    CandidateExperience,
    CandidateSkill,
    Job,
    JobApplication,
    RecruitmentSetting,
    utcnow,
)
from recruitment.uploads import store_resume


def setting(key: str, default: str = "") -> str:
    row = db.session.get(RecruitmentSetting, key)
    if row and row.value is not None and str(row.value).strip() != "":
        return str(row.value)
    return default


def next_application_number(when: datetime | None = None) -> str:
    when = when or utcnow()
    prefix = setting("application_number_prefix", current_app.config["APPLICATION_NUMBER_PREFIX"])
    padding = int(setting("application_number_padding", str(current_app.config["APPLICATION_NUMBER_PADDING"])))
    year = when.year
    query = ApplicationNumberSequence.query.filter_by(prefix=prefix, year=year)
    bind = db.session.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        query = query.with_for_update()
    seq = query.first()
    if seq is None:
        seq = ApplicationNumberSequence(prefix=prefix, year=year, last_number=0)
        db.session.add(seq)
        db.session.flush()
        seq = ApplicationNumberSequence.query.filter_by(prefix=prefix, year=year).first()
    seq.last_number += 1
    db.session.flush()
    return f"{prefix}-{year}-{seq.last_number:0{padding}d}"


DUPLICATE_EMAIL_MESSAGE = (
    "This email address is already used in an application. "
    "Please check your application status instead of applying again."
)
DUPLICATE_MOBILE_MESSAGE = (
    "This mobile number is already used in an application. "
    "Please check your application status instead of applying again."
)
DUPLICATE_FORM_MESSAGE = (
    "An application with this mobile number or email address already exists. "
    "Please check your application status."
)


class DuplicateApplicationError(ValueError):
    def __init__(self, fields: dict[str, str]):
        self.fields = fields
        super().__init__(DUPLICATE_FORM_MESSAGE)


def find_duplicate_fields(job_id: int, email: str, mobile: str) -> dict[str, str]:
    email_n = normalize_email(email)
    mobile_n = normalize_mobile(mobile)
    errors: dict[str, str] = {}
    base = JobApplication.query.join(Candidate).filter(JobApplication.job_id == job_id)
    if email_n and base.filter(func.lower(Candidate.email) == email_n).first():
        errors["email"] = DUPLICATE_EMAIL_MESSAGE
    if mobile_n and base.filter(Candidate.mobile == mobile_n).first():
        errors["mobile"] = DUPLICATE_MOBILE_MESSAGE
    return errors


def find_duplicate(job_id: int, email: str, mobile: str) -> JobApplication | None:
    email_n = normalize_email(email)
    mobile_n = normalize_mobile(mobile)
    query = JobApplication.query.join(Candidate).filter(JobApplication.job_id == job_id)
    if email_n and mobile_n:
        query = query.filter((func.lower(Candidate.email) == email_n) | (Candidate.mobile == mobile_n))
    elif email_n:
        query = query.filter(func.lower(Candidate.email) == email_n)
    elif mobile_n:
        query = query.filter(Candidate.mobile == mobile_n)
    else:
        return None
    return query.order_by(JobApplication.submitted_at.desc()).first()


def submit_application(job: Job, clean: dict, resume_payload: bytes, original_name: str) -> JobApplication:
    if not is_job_application_open(job):
        raise ValueError(CLOSED_MESSAGE)

    duplicates = find_duplicate_fields(job.job_id, clean["email"], clean["mobile"])
    if duplicates:
        raise DuplicateApplicationError(duplicates)

    candidate = Candidate.query.filter(func.lower(Candidate.email) == clean["email"]).first()
    if candidate is None:
        candidate = Candidate(
            name=clean["name"],
            father_name=clean["father_name"],
            dob=clean["dob"],
            gender=clean["gender"],
            mobile=clean["mobile"],
            email=clean["email"],
            address=clean["address"],
            city=clean["city"],
            state=clean["state"],
            pin_code=clean["pin_code"],
        )
        db.session.add(candidate)
        db.session.flush()
    else:
        candidate.name = clean["name"]
        candidate.father_name = clean["father_name"]
        candidate.dob = clean["dob"]
        candidate.gender = clean["gender"]
        candidate.mobile = clean["mobile"]
        candidate.address = clean["address"]
        candidate.city = clean["city"]
        candidate.state = clean["state"]
        candidate.pin_code = clean["pin_code"]
        candidate.updated_at = utcnow()
        CandidateEducation.query.filter_by(candidate_id=candidate.candidate_id).delete()
        CandidateExperience.query.filter_by(candidate_id=candidate.candidate_id).delete()
        CandidateSkill.query.filter_by(candidate_id=candidate.candidate_id).delete()

    db.session.add(
        CandidateEducation(
            candidate=candidate,
            education_type="highest",
            qualification=clean["highest_qualification"],
            university_board=clean["university_board"],
            passing_year=clean["passing_year"],
            percentage_cgpa=clean["percentage_cgpa"],
        )
    )
    if clean["last_qualification"] != clean["highest_qualification"]:
        db.session.add(
            CandidateEducation(
                candidate=candidate,
                education_type="last",
                qualification=clean["last_qualification"],
                university_board=clean["university_board"],
                passing_year=clean["passing_year"],
                percentage_cgpa=clean["percentage_cgpa"],
            )
        )

    db.session.add(
        CandidateExperience(
            candidate=candidate,
            sales_experience_years=clean["sales_experience_years"],
            sales_experience_months=clean["sales_experience_months"] or 0,
            previous_company=clean["previous_company"] or None,
            previous_designation=clean["previous_designation"] or None,
            responsibilities=clean["responsibilities"] or None,
            total_work_experience=clean["total_work_experience"] or None,
            software_sales_experience=clean["software_sales_experience"] or None,
            b2b_sales_experience=clean["b2b_sales_experience"] or None,
            tax_accounting_erp_sales_experience=clean["tax_accounting_erp_sales_experience"] or None,
        )
    )
    db.session.add(
        CandidateSkill(
            candidate=candidate,
            communication_skills=clean["communication_skills"],
            computer_knowledge=clean["computer_knowledge"],
            ms_excel_knowledge=clean["ms_excel_knowledge"],
            crm_erp_knowledge=clean["crm_erp_knowledge"],
            digital_marketing_knowledge=clean["digital_marketing_knowledge"],
            other_skills=clean["other_skills"] or None,
        )
    )

    meta = store_resume(resume_payload, original_name, current_app.config["UPLOAD_DIR"])
    number = next_application_number()
    application = JobApplication(
        application_number=number,
        candidate=candidate,
        job=job,
        application_status="New",
        source=clean["source"],
        visitor_id=clean.get("visitor_id") or None,
        session_id=clean.get("session_id") or None,
        expected_salary=clean["expected_salary"],
        notice_period=clean["notice_period"],
        current_employment_status=clean["current_employment_status"],
        willing_to_work_haldwani=clean["willing_to_work_haldwani"],
        willing_to_travel=clean["willing_to_travel"],
        about_candidate=clean["about_candidate"],
        suitability_answer=clean["suitability_answer"],
        declaration_accepted=True,
        resume_original_name=meta["resume_original_name"],
        resume_stored_name=meta["resume_stored_name"],
        resume_file_reference=meta["resume_file_reference"],
        resume_file_type=meta["resume_file_type"],
        resume_file_size=meta["resume_file_size"],
        resume_uploaded_at=utcnow(),
    )
    db.session.add(application)
    db.session.flush()
    db.session.add(
        ApplicationStatusHistory(
            application_id=application.application_id,
            old_status=None,
            new_status="New",
            changed_by="Applicant",
            change_reason="Application submitted",
        )
    )
    write_audit(
        "RESUME_UPLOADED",
        "Resume uploaded",
        candidate_id=candidate.candidate_id,
        application_id=application.application_id,
        visitor_id=application.visitor_id,
        session_id=application.session_id,
        details=f"type={meta['resume_file_type']}; size={meta['resume_file_size']}",
    )
    write_audit(
        "APPLICATION_SUBMITTED",
        "Application submitted",
        candidate_id=candidate.candidate_id,
        application_id=application.application_id,
        visitor_id=application.visitor_id,
        session_id=application.session_id,
        details=f"number={number}; job={job.slug}",
    )
    db.session.commit()

    pdf_bytes = None
    try:
        pdf_path = store_final_pdf(application)
        write_audit(
            "APPLICATION_PDF_GENERATED",
            "Application PDF generated",
            candidate_id=candidate.candidate_id,
            application_id=application.application_id,
            details=application.application_number,
        )
        db.session.commit()
        if pdf_path is not None:
            pdf_bytes = pdf_path.read_bytes()
    except Exception:
        logging.getLogger(__name__).exception("Application PDF generation failed after submit")

    submitted = application.submitted_at.strftime("%d %b %Y, %I:%M %p") + " IST"
    send_candidate_acknowledgement(
        candidate.name, candidate.email, number, job.job_title, submitted, pdf_bytes=pdf_bytes
    )
    send_admin_notification(number, job.job_title, application.source or "", submitted)
    return application


def change_status(application: JobApplication, new_status: str, changed_by: str, reason: str = "", commit: bool = True) -> None:
    old = application.application_status
    if old == new_status:
        return
    application.application_status = new_status
    application.updated_at = utcnow()
    db.session.add(
        ApplicationStatusHistory(
            application_id=application.application_id,
            old_status=old,
            new_status=new_status,
            changed_by=changed_by,
            change_reason=reason or None,
        )
    )
    event = "APPLICATION_STATUS_CHANGED"
    if new_status == "Rejected":
        event = "APPLICATION_REJECTED"
    elif new_status == "Shortlisted":
        event = "APPLICATION_SHORTLISTED"
    elif new_status == "Interview Scheduled":
        event = "INTERVIEW_SCHEDULED"
    elif new_status == "Selected":
        event = "CANDIDATE_SELECTED"
    write_audit(
        event,
        f"Status changed from {old} to {new_status}",
        candidate_id=application.candidate_id,
        application_id=application.application_id,
        visitor_id=application.visitor_id,
        session_id=application.session_id,
        details=reason or f"{old} → {new_status}",
        actor_type="admin",
        actor_name=changed_by,
    )
    if commit:
        db.session.commit()
        try:
            mapped = public_status(new_status)
            notify_candidate_status(application, mapped["label"], mapped["message"])
        except Exception:
            logging.getLogger(__name__).exception("Status update notification failed")
