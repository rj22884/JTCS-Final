"""Recruitment data models. Audit rows are append-only from application code."""

from __future__ import annotations

from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from recruitment.extensions import db

APPLICATION_STATUSES = (
    "New",
    "Under Review",
    "Shortlisted",
    "Interview Scheduled",
    "Interviewed",
    "Selected",
    "Offer Issued",
    "Offer Accepted",
    "Appointment Issued",
    "Rejected",
    "On Hold",
)

EVENT_TYPES = (
    "SALES_EXECUTIVE_CTA_CLICK",
    "JOB_PAGE_VIEW",
    "APPLICATION_STARTED",
    "APPLICATION_SUBMITTED",
    "RESUME_UPLOADED",
    "APPLICATION_UPDATED",
    "APPLICATION_STATUS_CHANGED",
    "APPLICATION_VIEWED",
    "APPLICATION_REJECTED",
    "APPLICATION_SHORTLISTED",
    "INTERVIEW_SCHEDULED",
    "CANDIDATE_SELECTED",
    "ADMIN_LOGIN",
    "ADMIN_LOGIN_FAILED",
    "ADMIN_LOGOUT",
    "RESUME_DOWNLOADED",
    "AUDIT_EXPORTED",
    "SETTINGS_UPDATED",
    "JOB_UPDATED",
    "INTERNAL_NOTE_ADDED",
    "INTERVIEW_UPDATED",
    "APPLICATIONS_EXPORTED",
    "BULK_STATUS_CHANGED",
    "RESUME_VIEWED",
    "APPLICATION_ATTEMPTED_AFTER_DEADLINE",
    "APPLICATION_PDF_DOWNLOADED",
    "APPLICATION_PDF_GENERATED",
    "EMPLOYEE_CREATED",
    "EMPLOYEE_UPDATED",
    "OFFER_LETTER_GENERATED",
    "OFFER_STATUS_CHANGED",
    "OFFER_ACCEPTED",
    "OFFER_DECLINED",
    "APPOINTMENT_LETTER_GENERATED",
    "EMPLOYEE_STATUS_CHANGED",
    "DOCUMENT_UPLOADED",
    "DOCUMENT_VIEWED",
    "DOCUMENT_DOWNLOADED",
    "HR_LETTER_EMAILED",
)

EMPLOYEE_STATUSES = (
    "Selected",
    "Offer Pending",
    "Offer Accepted",
    "Appointment Issued",
    "Probation",
    "Active",
    "On Hold",
)
OFFER_STATUSES = ("Pending", "Accepted", "Declined", "Expired")
EMPLOYMENT_TYPES = ("Full-time", "Part-time", "Contract", "Probation")
SALARY_FREQUENCIES = ("Monthly", "Annual")
EMPLOYEE_DOCUMENT_TYPES = (
    "Resume",
    "Offer Letter",
    "Appointment Letter",
    "Educational Documents",
    "Identity Documents",
    "Address Proof",
    "Other Documents",
)
OFFER_ACCEPTANCE_METHODS = ("In person", "Email", "Phone", "Other")

INTERVIEW_MODES = ("Office", "Phone", "Video Call")
INTERVIEW_RESULTS = ("Pending", "Recommended", "Not Recommended", "Further Review")

ADMIN_ROLES = ("admin", "recruiter", "viewer")

SOURCE_OPTIONS = (
    "JTCS Xpert Website",
    "LinkedIn",
    "Facebook",
    "WhatsApp",
    "Referral",
    "Other",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Job(db.Model):
    __tablename__ = "jobs"

    job_id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    job_title = db.Column(db.String(200), nullable=False)
    department = db.Column(db.String(120))
    location = db.Column(db.String(200))
    employment_type = db.Column(db.String(80))
    description = db.Column(db.Text)
    about_company = db.Column(db.Text)
    responsibilities = db.Column(db.Text)
    required_skills = db.Column(db.Text)
    experience_required = db.Column(db.String(200))
    qualification_required = db.Column(db.String(200))
    salary_ctc = db.Column(db.String(200))
    benefits = db.Column(db.Text)
    application_instructions = db.Column(db.Text)
    status = db.Column(db.String(40), default="open", index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    closing_date = db.Column(db.Date)
    closing_time = db.Column(db.String(8), default="23:59:59")
    timezone = db.Column(db.String(80), default="Asia/Kolkata")

    applications = db.relationship("JobApplication", back_populates="job")


class Candidate(db.Model):
    __tablename__ = "candidates"

    candidate_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    father_name = db.Column(db.String(200), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(30), nullable=False)
    mobile = db.Column(db.String(20), nullable=False, index=True)
    email = db.Column(db.String(254), nullable=False, index=True)
    address = db.Column(db.Text, nullable=False)
    city = db.Column(db.String(120), nullable=False, index=True)
    state = db.Column(db.String(120), nullable=False)
    pin_code = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    education = db.relationship("CandidateEducation", back_populates="candidate", cascade="all, delete-orphan")
    experience = db.relationship("CandidateExperience", back_populates="candidate", cascade="all, delete-orphan")
    skills = db.relationship("CandidateSkill", back_populates="candidate", cascade="all, delete-orphan")
    applications = db.relationship("JobApplication", back_populates="candidate")


class CandidateEducation(db.Model):
    __tablename__ = "candidate_education"

    education_id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    education_type = db.Column(db.String(40), nullable=False, default="highest")
    qualification = db.Column(db.String(200), nullable=False)
    university_board = db.Column(db.String(200))
    passing_year = db.Column(db.Integer)
    percentage_cgpa = db.Column(db.String(40))

    candidate = db.relationship("Candidate", back_populates="education")


class CandidateExperience(db.Model):
    __tablename__ = "candidate_experience"

    experience_id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    sales_experience_years = db.Column(db.Integer, nullable=False, default=0)
    sales_experience_months = db.Column(db.Integer, default=0)
    previous_company = db.Column(db.String(200))
    previous_designation = db.Column(db.String(200))
    responsibilities = db.Column(db.Text)
    total_work_experience = db.Column(db.String(80))
    software_sales_experience = db.Column(db.String(200))
    b2b_sales_experience = db.Column(db.String(200))
    tax_accounting_erp_sales_experience = db.Column(db.String(200))

    candidate = db.relationship("Candidate", back_populates="experience")


class CandidateSkill(db.Model):
    __tablename__ = "candidate_skills"

    skill_id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    communication_skills = db.Column(db.String(40))
    computer_knowledge = db.Column(db.String(40))
    ms_excel_knowledge = db.Column(db.String(40))
    crm_erp_knowledge = db.Column(db.String(40))
    digital_marketing_knowledge = db.Column(db.String(40))
    other_skills = db.Column(db.Text)

    candidate = db.relationship("Candidate", back_populates="skills")


class JobApplication(db.Model):
    __tablename__ = "job_applications"

    application_id = db.Column(db.Integer, primary_key=True)
    application_number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.job_id"), nullable=False, index=True)
    application_status = db.Column(db.String(40), default="New", nullable=False, index=True)
    source = db.Column(db.String(80))
    visitor_id = db.Column(db.String(64), index=True)
    session_id = db.Column(db.String(64), index=True)
    expected_salary = db.Column(db.String(80))
    notice_period = db.Column(db.String(80))
    current_employment_status = db.Column(db.String(80))
    willing_to_work_haldwani = db.Column(db.Boolean)
    willing_to_travel = db.Column(db.Boolean)
    about_candidate = db.Column(db.Text)
    suitability_answer = db.Column(db.Text)
    resume_original_name = db.Column(db.String(255))
    resume_stored_name = db.Column(db.String(255))
    resume_file_reference = db.Column(db.String(64))
    resume_file_type = db.Column(db.String(80))
    resume_file_size = db.Column(db.Integer)
    resume_uploaded_at = db.Column(db.DateTime)
    application_pdf_stored_name = db.Column(db.String(255))
    application_pdf_original_name = db.Column(db.String(255))
    application_pdf_generated_at = db.Column(db.DateTime)
    declaration_accepted = db.Column(db.Boolean, default=False, nullable=False)
    interview_scheduled_at = db.Column(db.DateTime)
    interview_mode = db.Column(db.String(40))
    interview_location = db.Column(db.String(200))
    interview_notes = db.Column(db.Text)
    interview_interviewer = db.Column(db.String(200))
    interview_result = db.Column(db.String(40))
    submitted_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    candidate = db.relationship("Candidate", back_populates="applications")
    job = db.relationship("Job", back_populates="applications")
    status_history = db.relationship(
        "ApplicationStatusHistory",
        back_populates="application",
        order_by="ApplicationStatusHistory.changed_at.asc()",
    )
    notes = db.relationship(
        "ApplicationNote",
        back_populates="application",
        order_by="ApplicationNote.created_at.desc()",
    )
    employee = db.relationship("Employee", back_populates="application", uselist=False)


class ApplicationStatusHistory(db.Model):
    __tablename__ = "application_status_history"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(
        db.Integer, db.ForeignKey("job_applications.application_id"), nullable=False, index=True
    )
    old_status = db.Column(db.String(40))
    new_status = db.Column(db.String(40), nullable=False)
    changed_by = db.Column(db.String(200))
    change_reason = db.Column(db.String(500))
    changed_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    application = db.relationship("JobApplication", back_populates="status_history")


class ApplicationNote(db.Model):
    """Internal recruiter notes — never shown to candidates."""

    __tablename__ = "application_notes"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(
        db.Integer, db.ForeignKey("job_applications.application_id"), nullable=False, index=True
    )
    note = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    application = db.relationship("JobApplication", back_populates="notes")


class RecruitmentAuditLog(db.Model):
    """Immutable from the normal admin UI. Rows are insert-only."""

    __tablename__ = "recruitment_audit_log"

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(80), nullable=False, index=True)
    event_name = db.Column(db.String(200), nullable=False)
    candidate_id = db.Column(db.Integer, index=True)
    application_id = db.Column(db.Integer, index=True)
    session_id = db.Column(db.String(64), index=True)
    visitor_id = db.Column(db.String(64), index=True)
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(500))
    device_type = db.Column(db.String(40))
    browser = db.Column(db.String(80))
    operating_system = db.Column(db.String(80))
    referrer = db.Column(db.String(500))
    page_url = db.Column(db.String(500))
    actor_type = db.Column(db.String(20))
    actor_name = db.Column(db.String(200))
    details = db.Column(db.Text)
    event_timestamp = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class ApplicationNumberSequence(db.Model):
    __tablename__ = "application_number_sequences"
    __table_args__ = (db.UniqueConstraint("prefix", "year", name="uq_app_seq_prefix_year"),)

    id = db.Column(db.Integer, primary_key=True)
    prefix = db.Column(db.String(40), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    last_number = db.Column(db.Integer, nullable=False, default=0)


class AdminUser(UserMixin, db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(40), nullable=False, default="recruiter")
    is_active_flag = db.Column("is_active", db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime)

    @property
    def is_active(self) -> bool:
        return bool(self.is_active_flag)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def can_write(self) -> bool:
        return self.role in {"admin", "recruiter"}

    def can_manage_settings(self) -> bool:
        return self.role == "admin"


class RecruitmentSetting(db.Model):
    __tablename__ = "recruitment_settings"

    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text)


class Department(db.Model):
    __tablename__ = "hr_departments"

    department_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


class Designation(db.Model):
    __tablename__ = "hr_designations"

    designation_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


class EmployeeNumberSequence(db.Model):
    __tablename__ = "hr_employee_number_sequences"
    __table_args__ = (db.UniqueConstraint("prefix", "year", name="uq_emp_seq_prefix_year"),)

    id = db.Column(db.Integer, primary_key=True)
    prefix = db.Column(db.String(40), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    last_number = db.Column(db.Integer, nullable=False, default=0)


class Employee(db.Model):
    __tablename__ = "hr_employees"

    employee_id = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.candidate_id"), nullable=False, index=True)
    application_id = db.Column(db.Integer, db.ForeignKey("job_applications.application_id"), unique=True, nullable=False, index=True)
    application_number = db.Column(db.String(40), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    father_name = db.Column(db.String(200))
    dob = db.Column(db.Date)
    gender = db.Column(db.String(40))
    mobile = db.Column(db.String(20))
    email = db.Column(db.String(254))
    address = db.Column(db.Text)
    city = db.Column(db.String(120))
    state = db.Column(db.String(120))
    pin_code = db.Column(db.String(10))
    highest_qualification = db.Column(db.String(200))
    last_qualification = db.Column(db.String(200))
    university_board = db.Column(db.String(200))
    passing_year = db.Column(db.String(20))
    percentage_cgpa = db.Column(db.String(40))
    sales_experience = db.Column(db.String(80))
    total_work_experience = db.Column(db.String(80))
    previous_company = db.Column(db.String(200))
    previous_designation = db.Column(db.String(200))
    responsibilities = db.Column(db.Text)
    software_sales_experience = db.Column(db.String(200))
    b2b_sales_experience = db.Column(db.String(200))
    tax_accounting_erp_sales_experience = db.Column(db.String(200))
    joining_date = db.Column(db.Date)
    department_id = db.Column(db.Integer, db.ForeignKey("hr_departments.department_id"))
    designation_id = db.Column(db.Integer, db.ForeignKey("hr_designations.designation_id"))
    reporting_manager = db.Column(db.String(200))
    employment_type = db.Column(db.String(80))
    work_location = db.Column(db.String(200))
    probation_period = db.Column(db.String(80))
    probation_end_date = db.Column(db.Date)
    employment_status = db.Column(db.String(40), default="Selected", nullable=False, index=True)
    salary_ctc = db.Column(db.String(80))
    salary_frequency = db.Column(db.String(40))
    basic_salary = db.Column(db.String(80))
    hra = db.Column(db.String(80))
    allowances = db.Column(db.String(200))
    other_compensation = db.Column(db.String(200))
    compensation_effective_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    candidate = db.relationship("Candidate")
    application = db.relationship("JobApplication", back_populates="employee")
    department = db.relationship("Department")
    designation = db.relationship("Designation")
    documents = db.relationship("EmployeeDocument", back_populates="employee", order_by="EmployeeDocument.uploaded_at.desc()")
    offers = db.relationship("OfferLetter", back_populates="employee", order_by="OfferLetter.generated_at.desc()")
    appointments = db.relationship("AppointmentLetter", back_populates="employee", order_by="AppointmentLetter.issued_at.desc()")


class EmployeeDocument(db.Model):
    __tablename__ = "hr_employee_documents"

    document_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("hr_employees.employee_id"), nullable=False, index=True)
    document_type = db.Column(db.String(80), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    uploaded_by = db.Column(db.String(200))
    uploaded_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    employee = db.relationship("Employee", back_populates="documents")


class OfferLetter(db.Model):
    __tablename__ = "hr_offer_letters"

    offer_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("hr_employees.employee_id"), nullable=False, index=True)
    application_id = db.Column(db.Integer, db.ForeignKey("job_applications.application_id"), nullable=False, index=True)
    offer_number = db.Column(db.String(40), unique=True, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    offer_date = db.Column(db.Date)
    joining_date = db.Column(db.Date)
    salary_ctc = db.Column(db.String(80))
    probation_period = db.Column(db.String(80))
    offer_status = db.Column(db.String(40), default="Pending", nullable=False, index=True)
    pdf_stored_name = db.Column(db.String(255))
    pdf_original_name = db.Column(db.String(255))
    generated_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    generated_by = db.Column(db.String(200))
    accepted_at = db.Column(db.DateTime)
    acceptance_method = db.Column(db.String(80))
    recorded_by = db.Column(db.String(200))
    emailed_at = db.Column(db.DateTime)
    emailed_to = db.Column(db.String(254))
    email_status = db.Column(db.String(40))

    employee = db.relationship("Employee", back_populates="offers")


class AppointmentLetter(db.Model):
    __tablename__ = "hr_appointment_letters"

    appointment_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("hr_employees.employee_id"), nullable=False, index=True)
    appointment_number = db.Column(db.String(40), unique=True, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    template_version = db.Column(db.String(40))
    appointment_date = db.Column(db.Date)
    joining_date = db.Column(db.Date)
    pdf_stored_name = db.Column(db.String(255))
    pdf_original_name = db.Column(db.String(255))
    issued_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    issued_by = db.Column(db.String(200))
    emailed_at = db.Column(db.DateTime)
    emailed_to = db.Column(db.String(254))
    email_status = db.Column(db.String(40))

    employee = db.relationship("Employee", back_populates="appointments")


class LetterTemplate(db.Model):
    __tablename__ = "hr_letter_templates"

    template_id = db.Column(db.Integer, primary_key=True)
    letter_type = db.Column(db.String(40), nullable=False, index=True)
    section_key = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
