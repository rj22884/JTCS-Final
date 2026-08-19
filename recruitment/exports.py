"""Audit trail exports: CSV, Excel, and PDF."""

from __future__ import annotations

import csv
import io
from datetime import datetime

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HEADERS = [
    "Date/Time",
    "Event",
    "Visitor ID",
    "Session ID",
    "Candidate ID",
    "Application ID",
    "IP",
    "Device",
    "Browser",
    "OS",
    "Page",
    "User/Admin",
    "Details",
]


def _rows(logs) -> list[list[str]]:
    out = []
    for log in logs:
        stamp = log.event_timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.event_timestamp else ""
        out.append([
            stamp,
            log.event_type or "",
            log.visitor_id or "",
            log.session_id or "",
            str(log.candidate_id or ""),
            str(log.application_id or ""),
            log.ip_address or "",
            log.device_type or "",
            log.browser or "",
            log.operating_system or "",
            log.page_url or "",
            log.actor_name or log.actor_type or "",
            (log.details or "").replace("\n", " "),
        ])
    return out


def export_csv(logs) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(HEADERS)
    writer.writerows(_rows(logs))
    return buf.getvalue().encode("utf-8-sig")


def export_xlsx(logs) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Audit Trail"
    ws.append(HEADERS)
    for row in _rows(logs):
        ws.append(row)
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 18
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


APP_HEADERS = [
    "Application No.",
    "Candidate Name",
    "City",
    "Qualification",
    "Sales Experience",
    "Application Date",
    "Source",
    "Status",
]

APP_DETAIL_HEADERS = APP_HEADERS + ["Mobile", "Email"]


def application_rows(applications, detailed: bool = False) -> list[list[str]]:
    from recruitment.admin_queries import education_map, experience_label

    rows = []
    for app in applications:
        candidate = app.candidate
        edu = education_map(candidate)
        exp = candidate.experience[0] if candidate.experience else None
        row = [
            app.application_number,
            candidate.name,
            candidate.city,
            edu["degree"] or edu["highest"],
            experience_label(exp),
            app.submitted_at.strftime("%d-%b-%Y") if app.submitted_at else "",
            app.source or "",
            app.application_status,
        ]
        if detailed:
            row.extend([candidate.mobile, candidate.email])
        rows.append(row)
    return rows


def export_applications_csv(applications, detailed: bool = False) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(APP_DETAIL_HEADERS if detailed else APP_HEADERS)
    writer.writerows(application_rows(applications, detailed))
    return buf.getvalue().encode("utf-8-sig")


def export_applications_xlsx(applications, detailed: bool = False) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Applications"
    headers = APP_DETAIL_HEADERS if detailed else APP_HEADERS
    ws.append(headers)
    for row in application_rows(applications, detailed):
        ws.append(row)
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 18
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_applications_pdf(applications, detailed: bool = False) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=24, rightMargin=24, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("JTCS Xpert — Job Applications", styles["Heading2"]),
        Paragraph(f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]),
        Spacer(1, 12),
    ]
    headers = APP_DETAIL_HEADERS if detailed else APP_HEADERS
    data = [headers] + application_rows(applications, detailed)[:400]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F4C81")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buf.getvalue()


def export_pdf(logs) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=24, rightMargin=24, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("JTCS Xpert — Recruitment Audit Trail", styles["Heading2"]),
        Paragraph(f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]),
        Spacer(1, 12),
    ]
    data = [HEADERS] + _rows(logs)[:400]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F4C81")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buf.getvalue()
