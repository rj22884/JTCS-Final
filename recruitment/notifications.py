"""Candidate notifications. Email is active; SMS/WhatsApp stay optional hooks."""

from __future__ import annotations

import logging

from recruitment.emailer import send_status_update
from recruitment.models import JobApplication

logger = logging.getLogger(__name__)


def notify_candidate_status(application: JobApplication, public_label: str, message: str) -> None:
    candidate = application.candidate
    job_title = application.job.job_title if application.job else "Sales Executive"
    if candidate and candidate.email:
        send_status_update(
            candidate.name,
            candidate.email,
            application.application_number,
            job_title,
            public_label,
            message,
        )
    _notify_sms_or_whatsapp(application, public_label)


def _notify_sms_or_whatsapp(application: JobApplication, public_label: str) -> None:
    """Reserved for a future SMS/WhatsApp provider. Do not send unless configured."""
    return None
