from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# Old:   UKCT1758885D2654K 17-APR-2026 10 - Not Locked ...
# G:     UKCT0347908G2633K 03-JUL-2026 - 2 ACC_PAY Not Locked -
# G+:    UKCT0839313G2621O / UKCT1002G2616L329 ...
# F:     UKCT0219293F2617L 02-JUN-2026 - 2 ACC_PAY Not Locked -
# Stationery = digits after the type letter (D/F/G/…) before trailing suffix.
RECEIPT_LINE = re.compile(
    r"^((?:UK|JK)CT\d+[A-Z](\d+)[A-Z0-9]*)\s+"
    r"(\d{2}-[A-Z]{3}-\d{4})\s+"
    r"(?:-\s+)?"
    r"([\d.]+)\s+"
    r"(-|\S+)\s+"
    r"(.+)$",
    re.IGNORECASE,
)
STATIONERY_FROM_RECEIPT = re.compile(
    r"(?:UK|JK)CT\d+[A-Z](\d+)[A-Z0-9]*$",
    re.IGNORECASE,
)
REPORT_FROM = re.compile(
    r"List of (?:Generated )?Receipts from\s+(\d{2}-[A-Za-z]{3}-\d{4})",
    re.IGNORECASE,
)
REPORT_TO = re.compile(r"to\s+(\d{2}-[A-Za-z]{3}-\d{4})", re.IGNORECASE)
STATE_LINE = re.compile(r"State\s*:\s*(.+)", re.IGNORECASE)
TOTAL_LINE = re.compile(r"^Total\s+([\d.]+)", re.IGNORECASE)
COUNT_LINE = re.compile(r"Record Count\s*:\s*(\d+)", re.IGNORECASE)
PAGE_HEADER = re.compile(
    r"^(?:Stock Holding Corporation.*|Page\s+\d+\s+of\s+\d+|::\s*.+)$",
    re.IGNORECASE,
)
SKIP_PREFIXES = (
    "list of receipts",
    "list of generated receipts",
    "receipt no",
    "litigant name",
    "above amount",
    "stock holding",
    "report generated",
    "report generated on",
    "account :",
    "branch code",
    "-- ",
)


@dataclass
class ParsedReceiptLine:
    receipt_no: str
    receipt_date: date | None
    amount: Decimal
    payment_mode: str | None
    receipt_status: str | None
    remarks: str | None
    stationery_no: str


@dataclass
class ParsedReceiptReport:
    report_from: date | None = None
    report_to: date | None = None
    state_name: str | None = None
    total_amount: Decimal | None = None
    record_count: int | None = None
    lines: list[ParsedReceiptLine] = field(default_factory=list)


class ECourtPdfService:
    @staticmethod
    def extract_text(raw: bytes) -> str:
        try:
            import pdfplumber
        except ImportError as exc:
            raise ValueError("PDF reader not installed. Run: pip install pdfplumber") from exc

        parts: list[str] = []
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if not text.strip():
                    continue
                page_lines: list[str] = []
                for raw_line in text.splitlines():
                    line = " ".join(raw_line.split())
                    if not line:
                        continue
                    if PAGE_HEADER.match(line):
                        continue
                    page_lines.append(line)
                if page_lines:
                    parts.append("\n".join(page_lines))
        return "\n".join(parts)

    @staticmethod
    def _parse_report_date(raw: str) -> date | None:
        raw = (raw or "").strip()
        for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
            try:
                return datetime.strptime(raw.title(), fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _split_status_remarks(tail: str) -> tuple[str | None, str | None]:
        text = (tail or "").strip()
        if not text:
            return None, None
        if text.endswith("-"):
            status = text[:-1].strip()
            remarks = "-"
            return status or None, remarks
        if ":" in text:
            status, remarks = text.split(":", 1)
            return status.strip() or None, remarks.strip() or None
        return text, None

    @classmethod
    def parse_stationery_no(cls, receipt_no: str) -> str | None:
        receipt = (receipt_no or "").strip()
        match = STATIONERY_FROM_RECEIPT.search(receipt)
        return match.group(1) if match else None

    @classmethod
    def parse_report_text(cls, text: str) -> ParsedReceiptReport:
        report = ParsedReceiptReport()
        seen_receipts: set[str] = set()

        for raw_line in (text or "").splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            lower = line.lower()

            from_match = REPORT_FROM.search(line)
            if from_match and report.report_from is None:
                report.report_from = cls._parse_report_date(from_match.group(1))
            to_match = REPORT_TO.search(line)
            if to_match and report.report_to is None:
                report.report_to = cls._parse_report_date(to_match.group(1))
            state_match = STATE_LINE.search(line)
            if state_match and report.state_name is None:
                report.state_name = state_match.group(1).strip()
            total_match = TOTAL_LINE.match(line)
            if total_match:
                try:
                    report.total_amount = Decimal(total_match.group(1))
                except InvalidOperation:
                    pass
            count_match = COUNT_LINE.search(line)
            if count_match:
                report.record_count = int(count_match.group(1))

            if report.state_name and STATE_LINE.match(line) and not re.match(
                r"^[A-Z]{2,4}CT", line, re.IGNORECASE
            ):
                continue

            if any(lower.startswith(prefix) for prefix in SKIP_PREFIXES):
                continue

            receipt_match = RECEIPT_LINE.match(line)
            if not receipt_match:
                continue

            receipt_no = receipt_match.group(1).upper()
            if receipt_no in seen_receipts:
                continue
            seen_receipts.add(receipt_no)

            stationery_no = receipt_match.group(2) or ""
            receipt_date = cls._parse_report_date(receipt_match.group(3))
            try:
                amount = Decimal(receipt_match.group(4))
            except InvalidOperation:
                continue
            payment_mode = receipt_match.group(5)
            if payment_mode == "-":
                payment_mode = None
            status, remarks = cls._split_status_remarks(receipt_match.group(6))

            report.lines.append(
                ParsedReceiptLine(
                    receipt_no=receipt_no,
                    receipt_date=receipt_date,
                    amount=amount,
                    payment_mode=payment_mode,
                    receipt_status=status,
                    remarks=remarks,
                    stationery_no=stationery_no,
                )
            )

        if report.record_count is None:
            report.record_count = len(report.lines)
        return report

    @classmethod
    def parse_pdf_bytes(cls, raw: bytes) -> ParsedReceiptReport:
        text = cls.extract_text(raw)
        if not text.strip():
            raise ValueError("Could not read text from PDF. Ensure it is a text-based e-Court receipt report.")
        report = cls.parse_report_text(text)
        if not report.lines:
            raise ValueError(
                "No receipt rows found in PDF. Upload SHCIL e-Court "
                "'List of Receipts' or 'Generated Receipts' report."
            )
        return report
