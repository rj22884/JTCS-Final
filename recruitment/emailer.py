"""SMTP notifications using environment configuration. Failures never block apply."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from html import escape

from flask import current_app

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool(current_app.config.get("SMTP_HOST"))


def send_mail(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> bool:
    host = current_app.config.get("SMTP_HOST")
    if not host or not to_email:
        return False
    msg = EmailMessage()
    sender = current_app.config.get("SMTP_FROM_EMAIL")
    name = current_app.config.get("SMTP_FROM_NAME")
    msg["From"] = f"{name} <{sender}>" if name else sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    for filename, data, mime in attachments or []:
        maintype, _, subtype = (mime or "application/pdf").partition("/")
        msg.add_attachment(
            data,
            maintype=maintype or "application",
            subtype=subtype or "pdf",
            filename=filename,
        )
    try:
        port = int(current_app.config.get("SMTP_PORT") or 587)
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if current_app.config.get("SMTP_USE_TLS", True):
                smtp.starttls()
            user = current_app.config.get("SMTP_USERNAME")
            password = current_app.config.get("SMTP_PASSWORD")
            if user:
                smtp.login(user, password or "")
            smtp.send_message(msg)
        return True
    except Exception:
        logger.exception("Recruitment email failed")
        return False


def send_candidate_acknowledgement(
    name: str,
    email: str,
    application_number: str,
    job_title: str,
    submitted: str,
    pdf_bytes: bytes | None = None,
) -> bool:
    subject = f"Application Received – {job_title} – JTCS Xpert"
    text = (
        f"Dear {name},\n\n"
        f"Thank you for applying for the {job_title} position at JTCS Xpert.\n\n"
        f"Application Number: {application_number}\n"
        f"Job Title: {job_title}\n"
        f"Submission Date: {submitted}\n\n"
        "Status: Application Received\n\n"
        "Check your application status:\n"
        "https://jtcsxpert.com/careers/application-status\n\n"
        "Please keep your Application Number and registered mobile/email address safe.\n\n"
        "This is an automated acknowledgement. Please do not reply with personal documents.\n\n"
        "Regards,\nJTCS Xpert Recruitment\nhttps://jtcsxpert.com\n"
    )
    html = f"""
    <p>Dear {escape(name)},</p>
    <p>Thank you for applying for the <strong>{escape(job_title)}</strong> position at JTCS Xpert.</p>
    <p>Application Number: <strong>{escape(application_number)}</strong><br>
    Job Title: {escape(job_title)}<br>
    Submission Date: {escape(submitted)}<br>
    Status: <strong>Application Received</strong></p>
    <p>Check your application status:<br>
    <a href="https://jtcsxpert.com/careers/application-status">https://jtcsxpert.com/careers/application-status</a></p>
    <p>Please keep your Application Number and registered mobile/email address safe.</p>
    <p>Regards,<br>JTCS Xpert Recruitment</p>
    """
    attachments = None
    if pdf_bytes:
        attachments = [(f"{application_number}-Application.pdf", pdf_bytes, "application/pdf")]
    return send_mail(email, subject, text, html, attachments=attachments)


def send_status_update(name: str, email: str, application_number: str, job_title: str, public_label: str, message: str) -> bool:
    subject = "Application Status Update – JTCS Xpert"
    text = (
        f"Dear {name or 'Candidate'},\n\n"
        f"Your application for the {job_title} position at JTCS Xpert has been updated.\n\n"
        f"Current Status:\n{public_label}\n\n"
        f"{message}\n\n"
        f"Application Number:\n{application_number}\n\n"
        "Check your application status:\n"
        "https://jtcsxpert.com/careers/application-status\n\n"
        "Regards,\nJTCS Xpert\n"
    )
    html = f"""
    <p>Dear {escape(name or 'Candidate')},</p>
    <p>Your application for the <strong>{escape(job_title)}</strong> position at JTCS Xpert has been updated.</p>
    <p>Current Status:<br><strong>{escape(public_label)}</strong></p>
    <p>{escape(message)}</p>
    <p>Application Number: <strong>{escape(application_number)}</strong></p>
    <p><a href="https://jtcsxpert.com/careers/application-status">Check your application status</a></p>
    <p>Regards,<br>JTCS Xpert</p>
    """
    return send_mail(email, subject, text, html)


def send_admin_notification(application_number: str, job_title: str, source: str, submitted: str) -> bool:
    to_email = current_app.config.get("RECRUITMENT_NOTIFY_EMAIL")
    if not to_email:
        return False
    subject = f"New application {application_number} – {job_title}"
    text = (
        f"A new job application was submitted.\n\n"
        f"Application Number: {application_number}\n"
        f"Job Title: {job_title}\n"
        f"Source: {source or 'Not specified'}\n"
        f"Submitted: {submitted}\n\n"
        "Open the recruitment admin dashboard to review the candidate.\n"
        "Candidate personal details are not included in this email.\n"
    )
    return send_mail(to_email, subject, text)
