"""Preview and final Sales Executive application PDFs (reportlab)."""

from __future__ import annotations

import logging
import uuid
from io import BytesIO
from pathlib import Path

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from recruitment.candidate_status import format_date, public_status
from recruitment.models import JobApplication, utcnow

logger = logging.getLogger(__name__)

PRIMARY = colors.HexColor("#0F4C81")
TEAL = colors.HexColor("#0F766E")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")

_FONT_REGISTERED = False


def _register_font() -> str:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return "JTCSBody"
    candidates = [
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\Nirmala.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            try:
                pdfmetrics.registerFont(TTFont("JTCSBody", str(path)))
                _FONT_REGISTERED = True
                return "JTCSBody"
            except Exception:
                continue
    _FONT_REGISTERED = True
    return "Helvetica"


def _styles():
    font = _register_font()
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle("brand", parent=base["Title"], fontName=font, fontSize=16, textColor=PRIMARY, alignment=TA_CENTER, spaceAfter=2),
        "sub": ParagraphStyle("sub", parent=base["Normal"], fontName=font, fontSize=11, textColor=TEAL, alignment=TA_CENTER, spaceAfter=8),
        "banner": ParagraphStyle("banner", parent=base["Normal"], fontName=font, fontSize=11, textColor=colors.HexColor("#B45309"), alignment=TA_CENTER, spaceAfter=10),
        "h": ParagraphStyle("h", parent=base["Heading2"], fontName=font, fontSize=11, textColor=PRIMARY, spaceBefore=10, spaceAfter=6),
        "body": ParagraphStyle("body", parent=base["Normal"], fontName=font, fontSize=9, leading=13, textColor=colors.HexColor("#0F172A")),
        "label": ParagraphStyle("label", parent=base["Normal"], fontName=font, fontSize=8, textColor=MUTED),
        "footer": ParagraphStyle("footer", parent=base["Normal"], fontName=font, fontSize=8, textColor=MUTED, alignment=TA_CENTER),
        "right": ParagraphStyle("right", parent=base["Normal"], fontName=font, fontSize=8, textColor=MUTED, alignment=TA_RIGHT),
        "font": font,
    }


def _text(value) -> str:
    return escape(str(value or "—")).replace("\n", "<br/>")


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []
        self._doc_font = "Helvetica"
        self._footer_left = "JTCS Xpert — Application generated electronically."

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.setStrokeColor(LINE)
            self.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
            self.setFont(getattr(self, "_doc_font", "Helvetica"), 8)
            self.setFillColor(MUTED)
            self.drawString(18 * mm, 9 * mm, getattr(self, "_footer_left", "JTCS Xpert"))
            self.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Page {self._pageNumber} of {page_count}")
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)


def _kv(styles, rows: list[tuple[str, str]]) -> Table:
    data = []
    for label, value in rows:
        data.append([
            Paragraph(escape(label), styles["label"]),
            Paragraph(_text(value), styles["body"]),
        ])
    table = Table(data, colWidths=[48 * mm, 122 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, LINE),
    ]))
    return table


def _yesno(value) -> str:
    if value is True or str(value).lower() in {"1", "true", "yes", "on"}:
        return "Yes"
    if value is False or str(value).lower() in {"0", "false", "no", "off"}:
        return "No"
    return value or "—"


def payload_from_form(form: dict, job=None, resume_name: str = "") -> dict:
    years = form.get("sales_experience_years") or "0"
    months = form.get("sales_experience_months") or "0"
    return {
        "preview": True,
        "application_number": None,
        "application_date": None,
        "status": "Not submitted",
        "position": getattr(job, "job_title", None) or "Sales Executive",
        "location": getattr(job, "location", None) or "Haldwani",
        "name": form.get("name") or "",
        "father_name": form.get("father_name") or "",
        "dob": form.get("dob") or "",
        "gender": form.get("gender") or "",
        "mobile": form.get("mobile") or "",
        "email": form.get("email") or "",
        "address": form.get("address") or "",
        "city": form.get("city") or "",
        "state": form.get("state") or "",
        "pin_code": form.get("pin_code") or "",
        "highest_qualification": form.get("highest_qualification") or "",
        "last_qualification": form.get("last_qualification") or "",
        "university_board": form.get("university_board") or "",
        "passing_year": form.get("passing_year") or "",
        "percentage_cgpa": form.get("percentage_cgpa") or "",
        "sales_experience": f"{years} years {months} months",
        "previous_company": form.get("previous_company") or "",
        "previous_designation": form.get("previous_designation") or "",
        "responsibilities": form.get("responsibilities") or "",
        "total_work_experience": form.get("total_work_experience") or "",
        "software_sales_experience": form.get("software_sales_experience") or "",
        "b2b_sales_experience": form.get("b2b_sales_experience") or "",
        "tax_accounting_erp_sales_experience": form.get("tax_accounting_erp_sales_experience") or "",
        "communication_skills": form.get("communication_skills") or "",
        "computer_knowledge": form.get("computer_knowledge") or "",
        "ms_excel_knowledge": form.get("ms_excel_knowledge") or "",
        "crm_erp_knowledge": form.get("crm_erp_knowledge") or "",
        "digital_marketing_knowledge": form.get("digital_marketing_knowledge") or "",
        "other_skills": form.get("other_skills") or "",
        "expected_salary": form.get("expected_salary") or "",
        "notice_period": form.get("notice_period") or "",
        "current_employment_status": form.get("current_employment_status") or "",
        "willing_to_work_haldwani": _yesno(form.get("willing_to_work_haldwani")),
        "willing_to_travel": _yesno(form.get("willing_to_travel")),
        "source": form.get("source") or "",
        "about_candidate": form.get("about_candidate") or "",
        "suitability_answer": form.get("suitability_answer") or "",
        "declaration": "Accepted" if form.get("declaration") else "Not accepted",
        "resume_name": resume_name or (form.get("resume_name") or ""),
        "resume_submitted": "Yes" if resume_name or form.get("resume_name") else "No",
    }


def payload_from_application(application: JobApplication) -> dict:
    candidate = application.candidate
    job = application.job
    edu = {row.education_type: row for row in (candidate.education or [])} if candidate else {}
    highest = edu.get("highest")
    last = edu.get("last") or highest
    exp = (candidate.experience[0] if candidate and candidate.experience else None)
    skill = (candidate.skills[0] if candidate and candidate.skills else None)
    years = getattr(exp, "sales_experience_years", 0) or 0
    months = getattr(exp, "sales_experience_months", 0) or 0
    dob = ""
    if candidate and candidate.dob:
        dob = candidate.dob.strftime("%d/%m/%Y")
    return {
        "preview": False,
        "application_number": application.application_number,
        "application_date": format_date(application.submitted_at),
        "status": public_status(application.application_status)["label"],
        "position": job.job_title if job else "Sales Executive",
        "location": job.location if job else "Haldwani",
        "name": candidate.name if candidate else "",
        "father_name": candidate.father_name if candidate else "",
        "dob": dob,
        "gender": candidate.gender if candidate else "",
        "mobile": candidate.mobile if candidate else "",
        "email": candidate.email if candidate else "",
        "address": candidate.address if candidate else "",
        "city": candidate.city if candidate else "",
        "state": candidate.state if candidate else "",
        "pin_code": candidate.pin_code if candidate else "",
        "highest_qualification": highest.qualification if highest else "",
        "last_qualification": last.qualification if last else "",
        "university_board": (highest.university_board if highest else "") or "",
        "passing_year": str(highest.passing_year or "") if highest else "",
        "percentage_cgpa": highest.percentage_cgpa if highest else "",
        "sales_experience": f"{years} years {months} months",
        "previous_company": getattr(exp, "previous_company", "") or "",
        "previous_designation": getattr(exp, "previous_designation", "") or "",
        "responsibilities": getattr(exp, "responsibilities", "") or "",
        "total_work_experience": getattr(exp, "total_work_experience", "") or "",
        "software_sales_experience": getattr(exp, "software_sales_experience", "") or "",
        "b2b_sales_experience": getattr(exp, "b2b_sales_experience", "") or "",
        "tax_accounting_erp_sales_experience": getattr(exp, "tax_accounting_erp_sales_experience", "") or "",
        "communication_skills": getattr(skill, "communication_skills", "") or "",
        "computer_knowledge": getattr(skill, "computer_knowledge", "") or "",
        "ms_excel_knowledge": getattr(skill, "ms_excel_knowledge", "") or "",
        "crm_erp_knowledge": getattr(skill, "crm_erp_knowledge", "") or "",
        "digital_marketing_knowledge": getattr(skill, "digital_marketing_knowledge", "") or "",
        "other_skills": getattr(skill, "other_skills", "") or "",
        "expected_salary": application.expected_salary or "",
        "notice_period": application.notice_period or "",
        "current_employment_status": application.current_employment_status or "",
        "willing_to_work_haldwani": _yesno(application.willing_to_work_haldwani),
        "willing_to_travel": _yesno(application.willing_to_travel),
        "source": application.source or "",
        "about_candidate": application.about_candidate or "",
        "suitability_answer": application.suitability_answer or "",
        "declaration": "Accepted" if application.declaration_accepted else "Not accepted",
        "resume_name": application.resume_original_name or "",
        "resume_submitted": "Yes" if application.resume_stored_name else "No",
        "submitted_at": application.submitted_at.strftime("%d %B %Y, %I:%M %p") if application.submitted_at else "",
    }


def build_pdf(payload: dict) -> bytes:
    styles = _styles()
    buf = BytesIO()
    preview = bool(payload.get("preview"))

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=payload.get("application_number") or "JTCS Application Preview",
        author="JTCS Xpert",
        subject="PREVIEW - NOT SUBMITTED" if preview else "APPLICATION SUBMITTED",
    )
    story = [
        Paragraph("JTCS Xpert", styles["brand"]),
        Paragraph("Sales Executive – Job Application", styles["sub"]),
    ]
    if preview:
        story.append(Paragraph("PREVIEW – NOT SUBMITTED", styles["banner"]))
        meta_rows = [
            ("Position", payload.get("position") or "Sales Executive"),
            ("Location", payload.get("location") or "Haldwani"),
            ("Current Status", "Not submitted"),
        ]
    else:
        story.append(Paragraph("APPLICATION SUBMITTED", styles["sub"]))
        meta_rows = [
            ("Application No.", payload.get("application_number") or "—"),
            ("Application Date", payload.get("application_date") or "—"),
            ("Position", payload.get("position") or "Sales Executive"),
            ("Location", payload.get("location") or "Haldwani"),
            ("Current Status", payload.get("status") or "—"),
        ]
    story.append(_kv(styles, meta_rows))
    story.append(Paragraph("Personal Information", styles["h"]))
    story.append(_kv(styles, [
        ("Full Name", payload.get("name")),
        ("Father's Name", payload.get("father_name")),
        ("Date of Birth", payload.get("dob")),
        ("Gender", payload.get("gender")),
        ("Mobile", payload.get("mobile")),
        ("Email", payload.get("email")),
        ("Address", payload.get("address")),
        ("City", payload.get("city")),
        ("State", payload.get("state")),
        ("PIN Code", payload.get("pin_code")),
    ]))
    story.append(Paragraph("Educational Information", styles["h"]))
    story.append(_kv(styles, [
        ("Highest Qualification", payload.get("highest_qualification")),
        ("Last Educational Qualification", payload.get("last_qualification")),
        ("University / Board", payload.get("university_board")),
        ("Year of Passing", payload.get("passing_year")),
        ("Percentage / CGPA", payload.get("percentage_cgpa")),
    ]))
    story.append(Paragraph("Professional Information", styles["h"]))
    story.append(_kv(styles, [
        ("Sales Experience", payload.get("sales_experience")),
        ("Previous Company", payload.get("previous_company")),
        ("Previous Designation", payload.get("previous_designation")),
        ("Responsibilities", payload.get("responsibilities")),
        ("Total Work Experience", payload.get("total_work_experience")),
        ("Software / IT Sales", payload.get("software_sales_experience")),
        ("B2B Sales Experience", payload.get("b2b_sales_experience")),
        ("Tax / Accounting / ERP Sales", payload.get("tax_accounting_erp_sales_experience")),
    ]))
    story.append(Paragraph("Skills", styles["h"]))
    story.append(_kv(styles, [
        ("Communication", payload.get("communication_skills")),
        ("Computer Knowledge", payload.get("computer_knowledge")),
        ("MS Excel", payload.get("ms_excel_knowledge")),
        ("CRM/ERP", payload.get("crm_erp_knowledge")),
        ("Digital Marketing", payload.get("digital_marketing_knowledge")),
        ("Other Skills", payload.get("other_skills")),
    ]))
    story.append(Paragraph("Other Information", styles["h"]))
    story.append(_kv(styles, [
        ("Expected Salary", payload.get("expected_salary")),
        ("Notice Period", payload.get("notice_period")),
        ("Employment Status", payload.get("current_employment_status")),
        ("Willing to Work in Haldwani", payload.get("willing_to_work_haldwani")),
        ("Willing to Travel", payload.get("willing_to_travel")),
        ("Source", payload.get("source")),
        ("About Yourself", payload.get("about_candidate")),
        ("Why suitable", payload.get("suitability_answer")),
        ("Resume Submitted", payload.get("resume_submitted")),
        ("Resume File", payload.get("resume_name") or "—"),
    ]))
    story.append(Paragraph("Declaration", styles["h"]))
    story.append(Paragraph(
        "I confirm that the information provided by me is true and complete to the best of my knowledge. "
        "I understand that JTCS Xpert may contact me regarding this job application.",
        styles["body"],
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(_kv(styles, [
        ("Declaration", payload.get("declaration") or "—"),
        ("Submitted", payload.get("submitted_at") or ("Preview only" if preview else "—")),
    ]))
    def _make_canvas(*args, **kwargs):
        page = NumberedCanvas(*args, **kwargs)
        page._doc_font = styles["font"]
        return page

    doc.build(story, canvasmaker=_make_canvas)
    return buf.getvalue()


def pdf_dir() -> Path:
    folder = Path(current_app.config.get("APPLICATION_PDF_DIR") or (Path(current_app.config["UPLOAD_DIR"]).parent / "application_pdfs"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def store_final_pdf(application: JobApplication) -> Path | None:
    payload = payload_from_application(application)
    data = build_pdf(payload)
    stored = f"{uuid.uuid4().hex}.pdf"
    path = pdf_dir() / stored
    path.write_bytes(data)
    application.application_pdf_stored_name = stored
    application.application_pdf_original_name = f"{application.application_number}-Application.pdf"
    application.application_pdf_generated_at = utcnow()
    return path


def resolve_application_pdf(application: JobApplication) -> Path | None:
    name = getattr(application, "application_pdf_stored_name", None)
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    path = (pdf_dir() / name).resolve()
    try:
        path.relative_to(pdf_dir().resolve())
    except ValueError:
        return None
    return path if path.is_file() else None
