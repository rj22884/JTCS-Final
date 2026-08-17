"""Candidate-facing application status mapping and verification.

Admin statuses stay on JobApplication. This module only translates them for
the public status page and API. No extra status table is used.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from recruitment.models import JobApplication

GENERIC_VERIFY_ERROR = (
    "We could not verify the application details. Please check your Application Number "
    "and registered mobile/email address."
)

TIMELINE_STAGES = (
    "Application Submitted",
    "Under Review",
    "Shortlisted",
    "Interview Scheduled",
    "Interviewed",
    "Final Decision",
)

# Admin status → public label, message, timeline index
STATUS_MAP = {
    "New": {
        "label": "Application Received",
        "message": (
            "Thank you for applying for the Sales Executive position. "
            "Your application has been successfully received and will be reviewed by our team."
        ),
        "stage": 0,
    },
    "Under Review": {
        "label": "Application Under Review",
        "message": "Your application is currently under review by our recruitment team.",
        "stage": 1,
    },
    "Shortlisted": {
        "label": "Shortlisted",
        "message": (
            "Congratulations! Your profile has been shortlisted. "
            "Our team will contact you regarding the next step."
        ),
        "stage": 2,
    },
    "Interview Scheduled": {
        "label": "Interview Scheduled",
        "message": "Your interview has been scheduled. Please check the interview details below.",
        "stage": 3,
    },
    "Interviewed": {
        "label": "Interview Completed",
        "message": "Your interview has been completed. Our team is currently reviewing the next steps.",
        "stage": 4,
    },
    "Selected": {
        "label": "Selected",
        "message": (
            "Congratulations! You have been selected for the Sales Executive position. "
            "Our team will contact you with further details."
        ),
        "stage": 5,
    },
    "Offer Issued": {
        "label": "Offer Letter Issued",
        "message": "An offer letter has been issued. Our team will contact you regarding acceptance.",
        "stage": 5,
    },
    "Offer Accepted": {
        "label": "Offer Accepted",
        "message": "Your offer has been recorded as accepted. Appointment formalities will follow.",
        "stage": 5,
    },
    "Appointment Issued": {
        "label": "Appointment Letter Issued",
        "message": "Your appointment letter has been issued. Please keep it for your records.",
        "stage": 5,
    },
    "Rejected": {
        "label": "Application Not Selected",
        "message": (
            "Thank you for your interest in JTCS Xpert. After reviewing your application, "
            "we will not be proceeding with your application at this time."
        ),
        "stage": 5,
    },
    "On Hold": {
        "label": "Application On Hold",
        "message": "Your application is currently on hold. We will update you when there is further information.",
        "stage": 5,
    },
}

STATUS_MAP["Interview"] = STATUS_MAP["Interview Scheduled"]
STATUS_MAP["Offer"] = STATUS_MAP["Offer Issued"]
STATUS_MAP["Appointment"] = STATUS_MAP["Appointment Issued"]
STATUS_MAP["Employee"] = STATUS_MAP["Appointment Issued"]


def normalize_application_number(raw: str | None) -> str:
    return re.sub(r"\s+", "", (raw or "")).upper()


def normalize_mobile(raw: str | None) -> str:
    digits = re.sub(r"\D+", "", raw or "")
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


def normalize_email(raw: str | None) -> str:
    return (raw or "").strip().lower()


def public_status(admin_status: str | None) -> dict:
    return STATUS_MAP.get(admin_status or "New", STATUS_MAP["New"])


def format_ist(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %B %Y, %I:%M %p")


def format_date(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d %B %Y")
    return str(value)


def verify_application(application_number: str, mobile: str = "", email: str = "") -> JobApplication | None:
    number = normalize_application_number(application_number)
    mobile_n = normalize_mobile(mobile)
    email_n = normalize_email(email)
    if not number or (not mobile_n and not email_n):
        return None
    application = JobApplication.query.filter_by(application_number=number).first()
    if application is None or application.candidate is None:
        return None
    candidate = application.candidate
    if mobile_n and normalize_mobile(candidate.mobile) == mobile_n:
        return application
    if email_n and normalize_email(candidate.email) == email_n:
        return application
    return None


def _timeline(admin_status: str) -> list[dict]:
    info = public_status(admin_status)
    current = info["stage"]
    items = []
    for index, name in enumerate(TIMELINE_STAGES):
        if index < current:
            state = "done"
        elif index == current:
            state = "current"
        else:
            state = "pending"
        label = name
        if name == "Final Decision" and index == current:
            label = info["label"]
        items.append({"name": label, "state": state})
    return items


def _public_history(application: JobApplication) -> list[dict]:
    rows = []
    for item in application.status_history or []:
        mapped = public_status(item.new_status)
        rows.append({
            "date": format_date(item.changed_at),
            "label": mapped["label"],
        })
    if not rows and application.submitted_at:
        rows.append({"date": format_date(application.submitted_at), "label": "Application Received"})
    return rows


def _interview_public(application: JobApplication) -> dict | None:
    if not application.interview_scheduled_at and not application.interview_mode and not application.interview_location:
        return None
    when = application.interview_scheduled_at
    return {
        "date": when.strftime("%d %B %Y") if when else None,
        "time": when.strftime("%I:%M %p") if when else None,
        "mode": application.interview_mode or None,
        "location": application.interview_location or None,
    }


def public_status_payload(application: JobApplication) -> dict:
    mapped = public_status(application.application_status)
    job = application.job
    updated = application.updated_at or application.submitted_at
    history = application.status_history or []
    if history:
        updated = history[-1].changed_at or updated
    return {
        "application_number": application.application_number,
        "position": job.job_title if job else "Sales Executive",
        "location": job.location if job else "Haldwani",
        "application_date": format_date(application.submitted_at),
        "current_status": mapped["label"],
        "message": mapped["message"],
        "timeline": _timeline(application.application_status),
        "history": _public_history(application),
        "interview": _interview_public(application),
        "last_updated": format_ist(updated),
        "has_application_pdf": bool(getattr(application, "application_pdf_stored_name", None)),
    }
