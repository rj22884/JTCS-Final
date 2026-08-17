"""Offer and appointment letter PDFs. Clauses come from hr_letter_templates."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from recruitment.application_pdf import NumberedCanvas, _kv, _styles, _text
from recruitment.models import LetterTemplate


def letter_sections(letter_type: str) -> list[LetterTemplate]:
    return (
        LetterTemplate.query.filter_by(letter_type=letter_type, is_active=True)
        .order_by(LetterTemplate.sort_order.asc(), LetterTemplate.template_id.asc())
        .all()
    )


def template_version(letter_type: str) -> str:
    rows = letter_sections(letter_type)
    return f"{letter_type}-{len(rows)}"


def _fill(text: str, values: dict) -> str:
    out = text or ""
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value or "—"))
    return out


def _letter_canvas(styles, footer: str):
    def _make_canvas(*args, **kwargs):
        page = NumberedCanvas(*args, **kwargs)
        page._doc_font = styles["font"]
        page._footer_left = footer
        return page

    return _make_canvas


def _story_header(styles, title: str):
    return [
        Paragraph("JTCS Xpert", styles["brand"]),
        Paragraph("Joshi Tax Consultancy &amp; Services, Haldwani, Uttarakhand", styles["sub"]),
        Paragraph(title, styles["h"]),
    ]


def build_offer_pdf(employee, offer, sections=None) -> bytes:
    styles = _styles()
    job = employee.application.job if employee.application else None
    values = {
        "name": employee.name,
        "employee_code": employee.employee_code,
        "application_number": employee.application_number,
        "position": (employee.designation.name if employee.designation else None) or (job.job_title if job else "Sales Executive"),
        "department": (employee.department.name if employee.department else None) or (job.department if job else "Sales"),
        "location": employee.work_location or "Haldwani, Uttarakhand",
        "joining_date": offer.joining_date.strftime("%d %B %Y") if offer.joining_date else "As agreed",
        "salary_ctc": offer.salary_ctc or employee.salary_ctc or "As discussed",
        "probation": offer.probation_period or employee.probation_period or "As per company policy",
    }
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
        title=f"Offer Letter {employee.employee_code}", author="JTCS Xpert", subject="OFFER LETTER",
    )
    story = _story_header(styles, "OFFER LETTER")
    story.append(_kv(styles, [
        ("Candidate", values["name"]),
        ("Application No.", values["application_number"]),
        ("Employee Code", values["employee_code"]),
        ("Position", values["position"]),
        ("Department", values["department"]),
        ("Location", values["location"]),
        ("Date of Joining", values["joining_date"]),
        ("Compensation", values["salary_ctc"]),
        ("Probation", values["probation"]),
        ("Offer No.", offer.offer_number),
    ]))
    for section in sections or letter_sections("offer"):
        story.append(Paragraph(_text(section.title), styles["h"]))
        story.append(Paragraph(_text(_fill(section.body, values)), styles["body"]))
        story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("For JTCS Xpert", styles["body"]))
    story.append(Paragraph("Authorised Signatory", styles["label"]))
    doc.build(story, canvasmaker=_letter_canvas(styles, "JTCS Xpert — Confidential offer letter."))
    return buf.getvalue()


def build_appointment_pdf(employee, appointment, sections=None) -> bytes:
    styles = _styles()
    job = employee.application.job if employee.application else None
    values = {
        "name": employee.name,
        "employee_code": employee.employee_code,
        "application_number": employee.application_number,
        "position": (employee.designation.name if employee.designation else None) or (job.job_title if job else "Sales Executive"),
        "department": (employee.department.name if employee.department else None) or (job.department if job else "Sales"),
        "location": employee.work_location or "Haldwani, Uttarakhand",
        "joining_date": appointment.joining_date.strftime("%d %B %Y") if appointment.joining_date else (
            employee.joining_date.strftime("%d %B %Y") if employee.joining_date else "As agreed"
        ),
        "employment_type": employee.employment_type or "Full-time",
        "reporting_manager": employee.reporting_manager or "As assigned",
        "salary_ctc": employee.salary_ctc or "As per offer",
        "basic_salary": employee.basic_salary or "—",
        "hra": employee.hra or "—",
        "allowances": employee.allowances or "—",
        "other_compensation": employee.other_compensation or "—",
        "probation": employee.probation_period or "As per company policy",
    }
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
        title=f"Appointment Letter {employee.employee_code}", author="JTCS Xpert", subject="APPOINTMENT LETTER",
    )
    story = _story_header(styles, "APPOINTMENT LETTER")
    story.append(Paragraph("Employee Information", styles["h"]))
    story.append(_kv(styles, [
        ("Employee Name", values["name"]),
        ("Employee Code", values["employee_code"]),
        ("Application No.", values["application_number"]),
        ("Designation", values["position"]),
        ("Department", values["department"]),
        ("Date of Joining", values["joining_date"]),
        ("Work Location", values["location"]),
        ("Employment Type", values["employment_type"]),
        ("Reporting Manager", values["reporting_manager"]),
    ]))
    story.append(Paragraph("Compensation", styles["h"]))
    story.append(_kv(styles, [
        ("Salary / CTC", values["salary_ctc"]),
        ("Basic Salary", values["basic_salary"]),
        ("HRA", values["hra"]),
        ("Allowances", values["allowances"]),
        ("Other Compensation", values["other_compensation"]),
    ]))
    for section in sections or letter_sections("appointment"):
        story.append(Paragraph(_text(section.title), styles["h"]))
        story.append(Paragraph(_text(_fill(section.body, values)), styles["body"]))
        story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Acceptance", styles["h"]))
    story.append(Paragraph(
        "I hereby accept the terms and conditions of my appointment.",
        styles["body"],
    ))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(f"Employee Name: {values['name']}", styles["body"]))
    story.append(Paragraph(f"Employee Code: {values['employee_code']}", styles["body"]))
    story.append(Paragraph("Date: ____________________", styles["body"]))
    story.append(Paragraph("Signature: ________________", styles["body"]))
    doc.build(story, canvasmaker=_letter_canvas(styles, "JTCS Xpert — Confidential appointment letter."))
    return buf.getvalue()
