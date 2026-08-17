"""Offer and appointment PDF generation using existing reportlab stack."""

from __future__ import annotations

import io
import re
from datetime import date, datetime
from pathlib import Path

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.models.hr import HrLetterTemplate
from app.extensions import db

VARIABLE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def storage_root() -> Path:
    root = Path(current_app.root_path).parent / "var" / "hr_documents"
    root.mkdir(parents=True, exist_ok=True)
    return root


def render_template_text(body: str, values: dict[str, str]) -> str:
    def _replace(match: re.Match) -> str:
        key = match.group(1)
        value = values.get(key)
        if value is None or str(value).strip() == "":
            return "—"
        return str(value)

    return VARIABLE_RE.sub(_replace, body or "")


def letter_values(employee: dict, extra: dict | None = None) -> dict[str, str]:
    payload = {
        "employee_name": employee.get("Name") or "",
        "employee_code": employee.get("EmployeeCode") or "",
        "application_number": employee.get("ApplicationNumber") or "",
        "designation": employee.get("designation_name") or "",
        "department": employee.get("department_name") or "",
        "joining_date": _fmt_date(employee.get("JoiningDate")),
        "work_location": employee.get("location_name") or "",
        "salary_ctc": _fmt_money(employee.get("SalaryCtc")),
        "probation_period": employee.get("ProbationPeriod") or "",
        "reporting_manager": employee.get("ReportingManager") or "",
        "employment_type": employee.get("employment_type_name") or "",
        "today": _fmt_date(date.today()),
    }
    if extra:
        payload.update({k: "" if v is None else str(v) for k, v in extra.items()})
    return payload


def active_sections(letter_type: str) -> list[HrLetterTemplate]:
    return (
        db.session.query(HrLetterTemplate)
        .filter(HrLetterTemplate.LetterType == letter_type, HrLetterTemplate.IsActive == True)  # noqa: E712
        .order_by(HrLetterTemplate.SortOrder.asc(), HrLetterTemplate.TemplateID.asc())
        .all()
    )


def build_letter_pdf(*, title: str, employee: dict, letter_type: str, extra: dict | None = None) -> bytes:
    values = letter_values(employee, extra)
    sections = active_sections(letter_type)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"JTCS Xpert — {title}",
        author="JTCS Xpert",
    )
    styles = getSampleStyleSheet()
    brand = ParagraphStyle(
        "HrBrand",
        parent=styles["Heading1"],
        fontName="Times-Bold",
        fontSize=16,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1E5A7A"),
        spaceAfter=2,
    )
    heading = ParagraphStyle(
        "HrTitle",
        parent=styles["Heading2"],
        fontName="Times-Bold",
        fontSize=13,
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    meta = ParagraphStyle(
        "HrMeta",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=9,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#555555"),
        spaceAfter=8,
    )
    section_title = ParagraphStyle(
        "HrSection",
        parent=styles["Heading3"],
        fontName="Times-Bold",
        fontSize=11,
        alignment=TA_LEFT,
        spaceBefore=8,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "HrBody",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=10,
        alignment=TA_JUSTIFY,
        leading=14,
        spaceAfter=4,
    )
    story = [
        Paragraph("JTCS Xpert", brand),
        Paragraph(title, heading),
        Paragraph(
            f"Date: {values.get('today')} &nbsp;&nbsp; "
            f"Employee: {values.get('employee_name')} &nbsp;&nbsp; "
            f"Code: {values.get('employee_code')} &nbsp;&nbsp; "
            f"Application: {values.get('application_number')}",
            meta,
        ),
    ]
    if not sections:
        story.append(Paragraph("No active letter template sections are configured.", body))
    for section in sections:
        story.append(Paragraph(section.Title, section_title))
        text = render_template_text(section.Body, values).replace("\n", "<br/>")
        story.append(Paragraph(text, body))
        story.append(Spacer(1, 2 * mm))

    def _footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont("Times-Roman", 8)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(18 * mm, 10 * mm, "JTCS Xpert — Confidential HR document")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc_obj.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def save_pdf_bytes(stored_name: str, pdf_bytes: bytes) -> Path:
    path = (storage_root() / stored_name).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not str(path).startswith(str(storage_root().resolve())):
        raise ValueError("Invalid HR document path")
    path.write_bytes(pdf_bytes)
    return path


def resolve_stored_file(stored_name: str) -> Path | None:
    if not stored_name or "/" in stored_name or "\\" in stored_name or ".." in stored_name:
        return None
    path = (storage_root() / stored_name).resolve()
    try:
        path.relative_to(storage_root().resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def _fmt_date(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")
    return str(value)


def _fmt_money(value) -> str:
    if value is None or value == "":
        return "—"
    try:
        return f"INR {float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)
