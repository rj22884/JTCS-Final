"""Default job, settings, and first admin account."""

from __future__ import annotations

import logging

from flask import current_app

from recruitment.extensions import db
from datetime import date

from recruitment.job_window import DEFAULT_CLOSING_TIME, DEFAULT_TIMEZONE, ensure_sales_executive_closing
from recruitment.models import AdminUser, Department, Designation, Job, LetterTemplate, RecruitmentSetting, utcnow

logger = logging.getLogger(__name__)

SALES_EXECUTIVE = {
    "slug": "sales-executive",
    "job_title": "Sales Executive",
    "department": "Sales",
    "location": "Haldwani, Uttarakhand (field travel as required)",
    "employment_type": "Full-time",
    "about_company": (
        "JTCS Xpert (Joshi Tax Consultancy & Services) is a premium Tax, Legal and Business "
        "Technology firm based in Haldwani, Uttarakhand. For 20+ years we have helped individuals, "
        "businesses, CAs, banks and government departments stay compliant and competitive — combining "
        "deep tax expertise with AI automation, ERP systems and custom software."
    ),
    "description": (
        "We are hiring a Sales Executive to grow JTCS Xpert relationships across Uttarakhand and "
        "nearby markets. You will present our tax, GST, accounting, DSC, compliance and business "
        "technology solutions to business owners and professionals, convert enquiries into clients, "
        "and represent JTCS with integrity."
    ),
    "responsibilities": (
        "Identify and meet prospective clients (businesses, CAs, advocates, institutions).\n"
        "Explain JTCS tax, GST, accounting, legal and technology offerings in clear language.\n"
        "Generate, qualify and close sales opportunities; maintain a daily activity record.\n"
        "Follow up on website, referral and field leads promptly.\n"
        "Coordinate with the delivery team so commitments are realistic and met.\n"
        "Travel within the assigned territory for meetings and relationship building.\n"
        "Uphold JTCS professional standards and client confidentiality."
    ),
    "required_skills": (
        "Clear spoken and written communication in Hindi and English.\n"
        "Comfort meeting business owners and professionals.\n"
        "Basic computer skills; willingness to use CRM / Excel.\n"
        "Self-driven, organised and target-oriented.\n"
        "Integrity and a professional appearance."
    ),
    "experience_required": "Freshers are welcome. Prior B2B, software, tax or accounting sales is an advantage.",
    "qualification_required": "Graduate in any discipline preferred. Diploma holders with strong communication may apply.",
    "salary_ctc": "As per interview and experience. Performance incentives may apply.",
    "benefits": (
        "Opportunity to learn tax, compliance and business technology products.\n"
        "Supportive team based in Haldwani.\n"
        "Performance-linked growth for consistent performers."
    ),
    "application_instructions": (
        "Applications are accepted only through this online application form. "
        "Please keep a PDF, DOC or DOCX resume ready (maximum 5 MB). "
        "You do not need to create an account to view this job or to apply."
    ),
    "status": "open",
    "closing_date": date(2026, 10, 31),
    "closing_time": DEFAULT_CLOSING_TIME,
    "timezone": DEFAULT_TIMEZONE,
}

DEFAULT_SETTINGS = {
    "application_number_prefix": "JTCS-SE",
    "application_number_padding": "5",
    "store_ip_address": "true",
    "max_resume_mb": "5",
    "notify_admin_email": "admin@jtcsxpert.com",
}


def seed_defaults() -> None:
    job = Job.query.filter_by(slug="sales-executive").first()
    if job is None:
        db.session.add(Job(**SALES_EXECUTIVE, created_at=utcnow()))
        logger.info("Seeded Sales Executive job")
    else:
        ensure_sales_executive_closing(job)

    for key, value in DEFAULT_SETTINGS.items():
        if db.session.get(RecruitmentSetting, key) is None:
            db.session.add(RecruitmentSetting(key=key, value=value))

    if AdminUser.query.count() == 0:
        email = (current_app.config.get("ADMIN_EMAIL") or "admin@jtcsxpert.com").lower()
        password = current_app.config.get("ADMIN_PASSWORD") or ""
        if not password:
            password = "ChangeMeNow!2026"
            logger.warning(
                "No RECRUITMENT_ADMIN_PASSWORD set. Created a temporary admin password. "
                "Change it immediately in Recruitment Settings."
            )
        admin = AdminUser(
            name=current_app.config.get("ADMIN_NAME") or "JTCS Admin",
            email=email,
            role="admin",
            is_active_flag=True,
        )
        admin.set_password(password)
        db.session.add(admin)
        logger.info("Seeded admin user %s", email)

    seed_hr_defaults()
    db.session.commit()


DEFAULT_DEPARTMENTS = ("Sales", "Accounts", "IT", "Administration")
DEFAULT_DESIGNATIONS = ("Sales Executive", "Senior Sales Executive", "Accountant", "Developer")
DEFAULT_LETTER_TEMPLATES = (
    ("offer", "intro", "Offer", 10, "We are pleased to offer you the position of {position} in the {department} department at JTCS Xpert, {location}."),
    ("offer", "joining", "Date of Joining", 20, "Your expected date of joining is {joining_date}. Please confirm your acceptance so that joining formalities can be completed."),
    ("offer", "compensation", "Compensation", 30, "Your compensation will be {salary_ctc}, subject to applicable statutory deductions and company policy."),
    ("offer", "probation", "Probation", 40, "You will be on probation for {probation}. Confirmation will depend on performance and company requirements."),
    ("offer", "terms", "General terms", 50, "The terms of employment shall be governed by applicable laws, rules, regulations and company policies, as amended from time to time. This letter is not legal advice."),
    ("offer", "acceptance", "Acceptance", 60, "Please confirm acceptance of this offer by the method advised by HR. This offer may be withdrawn if not accepted within the communicated period."),
    ("appointment", "intro", "Appointment", 10, "Further to your selection and accepted offer, you are appointed as {position} in {department} with effect from {joining_date}."),
    ("appointment", "work", "Place of work and hours", 20, "Your place of work is {location}. Working hours, weekly offs and holidays will follow applicable company policy as amended from time to time."),
    ("appointment", "probation", "Probation", 30, "Probation: {probation}. During probation, confirmation, extension or discontinuation will follow company policy."),
    ("appointment", "leave", "Leave and holidays", 40, "Leave and holiday entitlements will be as per applicable company policy and applicable law, as amended from time to time."),
    ("appointment", "notice", "Notice period", 50, "Notice period and separation terms will be as per applicable company policy and applicable law."),
    ("appointment", "confidentiality", "Confidentiality and conduct", 60, "You shall maintain confidentiality of company and client information and follow the JTCS Xpert code of conduct and company policies."),
    ("appointment", "ip", "Company information", 70, "Work product and confidential information created in the course of employment remain subject to company policy and applicable law."),
    ("appointment", "statutory", "Statutory benefits", 80, "Applicable statutory benefits, if any, will be provided in accordance with applicable laws and company policy, as amended from time to time."),
    ("appointment", "general", "General terms", 90, "The terms of employment shall be governed by applicable laws, rules, regulations and company policies, as amended from time to time. This letter is not legal advice."),
)


def seed_hr_defaults() -> None:
    for name in DEFAULT_DEPARTMENTS:
        if Department.query.filter_by(name=name).first() is None:
            db.session.add(Department(name=name, is_active=True))
    for name in DEFAULT_DESIGNATIONS:
        if Designation.query.filter_by(name=name).first() is None:
            db.session.add(Designation(name=name, is_active=True))
    for letter_type, key, title, order, body in DEFAULT_LETTER_TEMPLATES:
        exists = LetterTemplate.query.filter_by(letter_type=letter_type, section_key=key).first()
        if exists is None:
            db.session.add(
                LetterTemplate(
                    letter_type=letter_type,
                    section_key=key,
                    title=title,
                    body=body,
                    sort_order=order,
                    is_active=True,
                )
            )
