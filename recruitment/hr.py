"""Employee conversion, codes, and HR document storage — extends recruitment only."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from flask import current_app
from sqlalchemy import func

from recruitment.admin_queries import education_map
from recruitment.audit import write_audit
from recruitment.extensions import db
from recruitment.models import (
    Department,
    Designation,
    Employee,
    EmployeeNumberSequence,
    JobApplication,
    utcnow,
)


def next_employee_code(when: datetime | None = None) -> str:
    when = when or utcnow()
    prefix = current_app.config.get("EMPLOYEE_CODE_PREFIX") or "EMP"
    padding = int(current_app.config.get("EMPLOYEE_CODE_PADDING") or 5)
    year = when.year
    query = EmployeeNumberSequence.query.filter_by(prefix=prefix, year=year)
    bind = db.session.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        query = query.with_for_update()
    seq = query.first()
    if seq is None:
        seq = EmployeeNumberSequence(prefix=prefix, year=year, last_number=0)
        db.session.add(seq)
        db.session.flush()
        seq = EmployeeNumberSequence.query.filter_by(prefix=prefix, year=year).first()
    seq.last_number += 1
    db.session.flush()
    return f"{prefix}-{year}-{seq.last_number:0{padding}d}"


def hr_letter_dir() -> Path:
    folder = Path(current_app.config.get("HR_LETTER_DIR") or (Path(current_app.config["UPLOAD_DIR"]).parent / "hr_letters"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def employee_doc_dir() -> Path:
    folder = Path(current_app.config.get("EMPLOYEE_DOC_DIR") or (Path(current_app.config["UPLOAD_DIR"]).parent / "employee_docs"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def store_hr_bytes(folder: Path, data: bytes, original_name: str) -> str:
    stored = f"{uuid.uuid4().hex}.pdf" if original_name.lower().endswith(".pdf") else f"{uuid.uuid4().hex}{Path(original_name).suffix.lower()}"
    path = folder / stored
    path.write_bytes(data)
    return stored


def resolve_stored(folder: Path, stored_name: str | None) -> Path | None:
    if not stored_name:
        return None
    path = (folder / stored_name).resolve()
    try:
        path.relative_to(folder.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def convert_to_employee(application: JobApplication, created_by: str) -> Employee:
    if application.application_status != "Selected":
        raise ValueError("Only a Selected application can be converted to an employee.")
    existing = Employee.query.filter_by(application_id=application.application_id).first()
    if existing:
        return existing

    candidate = application.candidate
    edu = education_map(candidate)
    exp = candidate.experience[0] if candidate.experience else None
    last_edu = next((row for row in candidate.education if row.education_type == "last"), None)
    sales = ""
    if exp:
        sales = f"{exp.sales_experience_years or 0} years {exp.sales_experience_months or 0} months"

    sales_dept = Department.query.filter(func.lower(Department.name) == "sales").first()
    sales_desig = Designation.query.filter(func.lower(Designation.name) == "sales executive").first()
    job = application.job

    employee = Employee(
        employee_code=next_employee_code(),
        candidate_id=candidate.candidate_id,
        application_id=application.application_id,
        application_number=application.application_number,
        name=candidate.name,
        father_name=candidate.father_name,
        dob=candidate.dob,
        gender=candidate.gender,
        mobile=candidate.mobile,
        email=candidate.email,
        address=candidate.address,
        city=candidate.city,
        state=candidate.state,
        pin_code=candidate.pin_code,
        highest_qualification=edu.get("highest") or "",
        last_qualification=edu.get("last") or "",
        university_board=edu.get("university") or (last_edu.university_board if last_edu else ""),
        passing_year=str(edu.get("year") or ""),
        percentage_cgpa=edu.get("score") or "",
        sales_experience=sales,
        total_work_experience=(exp.total_work_experience if exp else "") or "",
        previous_company=(exp.previous_company if exp else "") or "",
        previous_designation=(exp.previous_designation if exp else "") or "",
        responsibilities=(exp.responsibilities if exp else "") or "",
        software_sales_experience=(exp.software_sales_experience if exp else "") or "",
        b2b_sales_experience=(exp.b2b_sales_experience if exp else "") or "",
        tax_accounting_erp_sales_experience=(exp.tax_accounting_erp_sales_experience if exp else "") or "",
        department_id=sales_dept.department_id if sales_dept else None,
        designation_id=sales_desig.designation_id if sales_desig else None,
        employment_type=(job.employment_type if job else None) or "Full-time",
        work_location=(job.location if job else None) or "Haldwani, Uttarakhand",
        employment_status="Selected",
        salary_ctc=application.expected_salary,
    )
    db.session.add(employee)
    db.session.flush()
    write_audit(
        "EMPLOYEE_CREATED",
        "Employee created from selected application",
        candidate_id=candidate.candidate_id,
        application_id=application.application_id,
        details=f"{employee.employee_code}; {application.application_number}",
        actor_type="admin",
        actor_name=created_by,
    )
    db.session.commit()
    return employee


def update_employee_status(employee: Employee, new_status: str, changed_by: str) -> None:
    old = employee.employment_status
    if old == new_status:
        return
    employee.employment_status = new_status
    employee.updated_at = utcnow()
    write_audit(
        "EMPLOYEE_STATUS_CHANGED",
        f"Employee status {old} → {new_status}",
        candidate_id=employee.candidate_id,
        application_id=employee.application_id,
        details=f"{employee.employee_code}; {old} → {new_status}",
        actor_type="admin",
        actor_name=changed_by,
    )


def recruitment_history(application: JobApplication) -> list[dict]:
    steps = [
        ("Application Submitted", True),
        ("Shortlisted", False),
        ("Interview Scheduled", False),
        ("Interviewed", False),
        ("Selected", False),
        ("Offer Generated", False),
        ("Offer Accepted", False),
        ("Employee Created", False),
        ("Appointment Letter Issued", False),
    ]
    seen = {row.new_status for row in (application.status_history or [])}
    seen.add(application.application_status)
    employee = getattr(application, "employee", None)
    flags = {
        "Shortlisted": "Shortlisted" in seen,
        "Interview Scheduled": "Interview Scheduled" in seen or bool(application.interview_scheduled_at),
        "Interviewed": "Interviewed" in seen or (application.interview_result and application.interview_result != "Pending"),
        "Selected": "Selected" in seen or application.application_status in {
            "Selected", "Offer Issued", "Offer Accepted", "Appointment Issued"
        },
        "Offer Generated": bool(employee and employee.offers),
        "Offer Accepted": bool(employee and any(o.offer_status == "Accepted" for o in employee.offers)),
        "Employee Created": bool(employee),
        "Appointment Letter Issued": bool(employee and employee.appointments) or application.application_status == "Appointment Issued",
    }
    out = []
    for label, always in steps:
        out.append({"label": label, "done": True if always else flags.get(label, False)})
    return out
