"""Label-based field extraction for Government of Uttarakhand e-Stamp certificates."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from werkzeug.datastructures import FileStorage

from app.repositories.stamp_ocr_repository import StampOcrRepository
from app.services.document_ocr_service import extract_document

logger = logging.getLogger(__name__)

# All known Uttarakhand e-Stamp labels in document order (used to slice values).
DOCUMENT_LABELS: list[tuple[str, str]] = [
    ("CertificateNumber", r"Certif[il1]cate\s*(?:No\.?|Number|Num\.?)"),
    ("CertificateIssuedDate", r"Certif[il1]cate\s*Issued\s*Date"),
    ("AccountReference", r"Account\s*Reference"),
    ("UniqueDocumentReference", r"Unique\s*(?:Doc\.?\s*)?Reference"),
    ("PurchasedBy", r"Purchased\s*by"),
    ("DescriptionOfDocument", r"Description\s+of\s+Document"),
    ("PropertyDescription", r"Property\s*Description"),
    ("ConsiderationPrice", r"Consideration\s*Price"),
    ("FirstPartyName", r"First\s*Party"),
    ("SecondPartyName", r"Second\s*Party"),
    ("StampDutyPaidBy", r"Stamp\s*Duty\s*Paid\s*By"),
    ("StampDutyAmount", r"Stamp\s*Duty\s*Am[o0]?u?n?t\s*(?:\(\s*Rs[\.:]?\s*\))?"),
]

_CERT_NUMBER_RE = re.compile(
    r"\bIN[\s\-]?UK[\s\-]?[A-Z0-9]{8,}\b",
    re.IGNORECASE,
)

# Fields returned to the Stamp Activity form (label mapping only — no positional OCR).
EXTRACT_FIELDS = {
    "CertificateNumber",
    "CertificateIssuedDate",
    "AccountReference",
    "UniqueDocumentReference",
    "PurchasedBy",
    "DescriptionOfDocument",
    "PropertyDescription",
    "ConsiderationPrice",
    "FirstPartyName",
    "SecondPartyName",
    "StampDutyPaidBy",
    "StampDutyAmount",
}


@dataclass
class StampOcrExtractResult:
    fields: dict[str, str]
    provider: str
    confidence: float
    ocr_text: str
    ocr_image_id: int | None


class StampOcrService:
    ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}

    def __init__(self, ocr_repo: StampOcrRepository | None = None):
        self.ocr_repo = ocr_repo or StampOcrRepository()

    @staticmethod
    def engine_status() -> dict:
        from app.services.ocr_provider_service import OcrProviderService

        return OcrProviderService.get_status().to_dict()

    def extract_from_upload(
        self, upload: FileStorage, *, created_by: str, store_image: bool = True
    ) -> StampOcrExtractResult:
        if not upload:
            raise ValueError("Please upload a certificate image or PDF.")

        filename = upload.filename or "clipboard.png"
        ext = self._extension(filename)
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValueError("Supported formats: PNG, JPG, JPEG, WEBP, PDF.")

        raw = upload.read()
        payload = extract_document(raw, ext=ext)
        fields = self.parse_certificate_text(payload.text)

        ocr_image_id = None
        if store_image:
            from app.utils.db_session import persist

            def _store():
                row = self.ocr_repo.create(
                    {
                        "OriginalImage": payload.raw_bytes,
                        "ImageHash": payload.image_hash,
                        "OcrText": payload.text,
                        "OcrConfidence": Decimal(str(payload.confidence)),
                        "OcrProvider": payload.provider,
                        "ImageSize": payload.image_size,
                        "CreatedBy": created_by,
                    }
                )
                return row.OcrImageID

            ocr_image_id = persist(_store)

        return StampOcrExtractResult(
            fields=fields,
            provider=payload.provider,
            confidence=payload.confidence,
            ocr_text=payload.text,
            ocr_image_id=ocr_image_id,
        )

    def parse_certificate_text(self, text: str) -> dict[str, str]:
        normalized = self._normalize_ocr_text(text)
        logger.info("===== OCR TEXT =====\n%s\n====================", normalized)

        flat = re.sub(r"\s+", " ", normalized).strip()
        markers = self._find_label_markers(flat)
        raw_values = self._slice_label_values(flat, markers)

        stamp_duty_row = self._extract_stamp_duty_row_amount(normalized)

        result: dict[str, str] = {}
        for field in EXTRACT_FIELDS:
            if field == "StampDutyAmount" and stamp_duty_row:
                result[field] = stamp_duty_row
                continue
            raw = raw_values.get(field)
            if not raw:
                continue
            cleaned = self._clean_field_value(field, raw)
            if cleaned:
                result[field] = cleaned

        if stamp_duty_row:
            result["StampDutyAmount"] = stamp_duty_row
        elif not result.get("StampDutyAmount"):
            fallback = self._extract_stamp_duty_fallback(flat)
            if fallback:
                result["StampDutyAmount"] = fallback

        if not result.get("StampDutyAmount"):
            line_amount = self._extract_stamp_duty_from_lines(normalized)
            if line_amount:
                result["StampDutyAmount"] = line_amount

        cert = self._extract_certificate_number(normalized, raw_values.get("CertificateNumber"))
        if cert:
            result["CertificateNumber"] = cert
        elif not result.get("CertificateNumber"):
            logger.warning("Certificate number not detected. Returning partial OCR fields: %s", sorted(result))
        return result

    @staticmethod
    def _normalize_ocr_text(text: str) -> str:
        """Normalize OCR output: line breaks around colons, spaces, punctuation."""
        t = re.sub(r"\r\n?", "\n", text or "")
        t = re.sub(r"\n\s*:\s*\n", "\n: ", t)
        t = re.sub(r"\n\s*:\s*", "\n: ", t)
        t = re.sub(r"(\w)\s*\n\s*:\s*", r"\1: ", t)
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r"\n+", "\n", t)
        t = re.sub(r"\s*:\s*", ": ", t)
        t = re.sub(r":\s*:+", ": ", t)
        return t.strip()

    @staticmethod
    def _find_label_markers(flat_text: str) -> list[tuple[int, int, str]]:
        markers: list[tuple[int, int, str]] = []
        for field, label_pattern in DOCUMENT_LABELS:
            match = re.search(label_pattern, flat_text, re.IGNORECASE)
            if match:
                markers.append((match.start(), match.end(), field))
        markers.sort(key=lambda item: item[0])
        return markers

    @staticmethod
    def _slice_label_values(flat_text: str, markers: list[tuple[int, int, str]]) -> dict[str, str]:
        values: dict[str, str] = {}
        for index, (_start, end, field) in enumerate(markers):
            next_start = markers[index + 1][0] if index + 1 < len(markers) else len(flat_text)
            chunk = flat_text[end:next_start]
            chunk = re.sub(r"^\s*:?\s*", "", chunk)
            chunk = chunk.strip(" :;-|")
            if chunk:
                values[field] = chunk
        return values

    @staticmethod
    def _extract_stamp_duty_row_amount(normalized: str) -> str | None:
        """
        Uttarakhand e-Stamp row rule for Stamp Duty Amount(Rs.):
        extract the figure between ':' and '(' on that row (2 decimal places).
        """
        row_patterns = (
            # Stamp Duty Amount(Rs.) : 1 (One only)
            r"Stamp\s*Duty\s*Amount\s*\(\s*Rs[\.:]?\s*\)\s*:\s*([^(\n]+?)\s*\(",
            # Label line then colon line then value: ... \n : \n 1 (One only)
            r"Stamp\s*Duty\s*Amount\s*\(\s*Rs[\.:]?\s*\)\s*(?:\n\s*)+:\s*([^(\n]+?)\s*\(",
            # Label line then value line: ... \n 1 (One only)
            r"Stamp\s*Duty\s*Amount\s*\(\s*Rs[\.:]?\s*\)\s*(?:\n\s*)+(\d+(?:\.\d+)?)\s*\(",
            # Label line then digit on its own line before (One only)
            r"Stamp\s*Duty\s*Amount\s*\(\s*Rs[\.:]?\s*\)\s*(?:\n\s*)+(?::\s*\n\s*)?(\d+(?:\.\d+)?)\s*(?:\n\s*)+\(",
        )
        for pattern in row_patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                amount = StampOcrService._amount_from_row_segment(match.group(1))
                if amount:
                    logger.info("Stamp Duty row match (%s) -> %s", pattern[:40], amount)
                    return amount

        # EasyOCR often drops the digit and keeps only "(One only)" on the next line.
        word_match = re.search(
            r"Stamp\s*Duty\s*Amount\s*\(\s*Rs[\.:]?\s*\)\s*(?:\n\s*:?\s*)*\(\s*"
            r"([A-Za-z]+(?:\s+[A-Za-z]+)*)\s+only\s*\)",
            normalized,
            re.IGNORECASE,
        )
        if word_match:
            amount = StampOcrService._word_amount(word_match.group(1))
            if amount:
                logger.info("Stamp Duty row word fallback -> %s", amount)
                return amount
        return None

    @staticmethod
    def _amount_from_row_segment(segment: str) -> str | None:
        segment = segment.strip().strip(":").strip()
        if not segment:
            return None
        numeric = re.match(r"^(\d+(?:\.\d+)?)", segment.replace(",", ""))
        if numeric:
            return StampOcrService._quantize_amount(numeric.group(1))
        return StampOcrService._word_amount(segment)

    @staticmethod
    def _extract_stamp_duty_fallback(flat_text: str) -> str | None:
        match = re.search(
            r"Stamp\s*Duty\s*Am[o0]?u?n?t\s*(?:\(\s*Rs[\.:]?\s*\))?\s*:?\s*(.+?)"
            r"(?=\s*(?:Article|Statute|Please verify|Registration|E&SB)\b|$)",
            flat_text,
            re.IGNORECASE,
        )
        if not match:
            return None
        return StampOcrService._parse_stamp_duty_amount(match.group(1))

    @staticmethod
    def _extract_stamp_duty_from_lines(normalized: str) -> str | None:
        lines = [line.strip() for line in normalized.split("\n")]
        for index, line in enumerate(lines):
            if not re.search(r"Stamp\s*Duty\s*Am[o0]?u?n?t", line, re.IGNORECASE):
                continue

            tail = re.split(
                r"Stamp\s*Duty\s*Am[o0]?u?n?t\s*(?:\(\s*Rs[\.:]?\s*\))?",
                line,
                maxsplit=1,
                flags=re.IGNORECASE,
            )
            parts: list[str] = []
            if len(tail) > 1 and tail[1].strip():
                parts.append(tail[1].strip())

            cursor = index + 1
            while cursor < len(lines) and cursor <= index + 3:
                candidate = lines[cursor].strip()
                cursor += 1
                if not candidate or candidate == ":":
                    continue
                if re.search(r"^(Article|Statute|Please verify|Registration|E&SB)\b", candidate, re.IGNORECASE):
                    break
                parts.append(candidate)
                if "(" in candidate:
                    break

            combined = " ".join(parts)
            amount = StampOcrService._parse_stamp_duty_amount(combined)
            if amount:
                return amount
        return None

    def _clean_field_value(self, field: str, raw: str) -> str | None:
        value = raw.strip()
        if not value:
            return None

        if field == "CertificateNumber":
            extracted = self._normalize_certificate_number(value)
            if extracted:
                return extracted
            match = re.search(r"([A-Z]{2}-[A-Z0-9]+|[A-Z0-9][A-Z0-9\-\/]{4,})", value, re.IGNORECASE)
            return match.group(1).upper() if match else value.split()[0][:100]

        if field == "CertificateIssuedDate":
            parsed = self._parse_issued_date(value)
            return parsed.isoformat() if parsed else None

        if field == "StampDutyAmount":
            return self._parse_stamp_duty_amount(value)

        if field == "ConsiderationPrice":
            return self._parse_stamp_duty_amount(value) or self._parse_numeric_amount(value)

        if field == "UniqueDocumentReference":
            match = re.search(r"(SUBIN[\-A-Z0-9]+|[A-Z0-9][A-Z0-9\-]{8,})", value, re.IGNORECASE)
            return match.group(1).upper() if match else value[:200]

        if field == "PropertyDescription":
            cleaned = value[:1000].strip()
            return "" if re.match(r"^(na|n/?a|nil|none|-)$", cleaned, re.I) else cleaned

        return value[:300]

    @staticmethod
    def _parse_stamp_duty_amount(value: str) -> str | None:
        """Extract stamp duty: text after ':' and before '(', formatted to 2 decimal places."""
        original = value.strip()
        if not original:
            return None

        for stop in (r"\bArticle\b", r"\bStatute\b", r"\bPlease verify\b", r"\bRegistration\b", r"\bE&SB\b"):
            match = re.search(stop, original, re.IGNORECASE)
            if match:
                original = original[: match.start()].strip()

        segment = original
        if ":" in segment:
            segment = segment.split(":", 1)[1].strip()

        segment = re.sub(r"^(?:Rs[\.:]?|INR)\s*", "", segment, flags=re.IGNORECASE).strip(" :;-|")

        if "(" in segment:
            before_paren = segment.split("(", 1)[0].strip()
            if before_paren:
                segment = before_paren

        if segment:
            numeric = re.match(r"^(\d+(?:\.\d+)?)", segment.replace(",", ""))
            if numeric:
                return StampOcrService._quantize_amount(numeric.group(1))

        paren_words = re.search(
            r"\(\s*([A-Za-z]+(?:\s+[A-Za-z]+)*)\s+only\s*\)",
            original,
            re.IGNORECASE,
        )
        if paren_words:
            word_amount = StampOcrService._word_amount(paren_words.group(1))
            if word_amount is not None:
                return word_amount

        paren_bare = re.search(
            r"\(\s*([A-Za-z]+(?:\s+[A-Za-z]+)*)\s*\)",
            original,
            re.IGNORECASE,
        )
        if paren_bare:
            word_amount = StampOcrService._word_amount(paren_bare.group(1))
            if word_amount is not None:
                return word_amount

        bare_words = re.search(
            r"\b([A-Za-z]+(?:\s+[A-Za-z]+)*)\s+only\b",
            original,
            re.IGNORECASE,
        )
        if bare_words:
            word_amount = StampOcrService._word_amount(bare_words.group(1))
            if word_amount is not None:
                return word_amount

        return StampOcrService._parse_numeric_amount(original)

    @staticmethod
    def _word_amount(text: str) -> str | None:
        words = {
            "zero": 0,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
            "twenty": 20,
            "thirty": 30,
            "forty": 40,
            "fifty": 50,
            "sixty": 60,
            "seventy": 70,
            "eighty": 80,
            "ninety": 90,
            "hundred": 100,
            "thousand": 1000,
        }
        tokens = re.findall(r"[a-z]+", text.lower())
        if not tokens:
            return None
        if len(tokens) == 1 and tokens[0] in words:
            return StampOcrService._quantize_amount(str(words[tokens[0]]))
        if tokens == ["one"]:
            return StampOcrService._quantize_amount("1")
        return None

    @staticmethod
    def _quantize_amount(raw: str) -> str | None:
        try:
            return str(Decimal(raw).quantize(Decimal("0.01")))
        except InvalidOperation:
            return raw

    @staticmethod
    def _parse_numeric_amount(value: str) -> str | None:
        match = re.search(r"(\d+(?:\.\d+)?)", value.replace(",", ""))
        if not match:
            return None
        return StampOcrService._quantize_amount(match.group(1))

    @classmethod
    def _extract_certificate_number(cls, text: str, sliced: str | None = None) -> str | None:
        for blob in (sliced or "", text or ""):
            if not blob:
                continue
            found = cls._normalize_certificate_number(blob)
            if found:
                return found
        return None

    @staticmethod
    def _normalize_certificate_number(value: str) -> str | None:
        if not value:
            return None
        match = _CERT_NUMBER_RE.search(value)
        if not match:
            return None
        compact = re.sub(r"[\s\-]+", "", match.group(0).upper())
        if compact.startswith("INUK") and len(compact) >= 12:
            return "IN-UK" + compact[4:]
        return match.group(0).upper().replace(" ", "")

    @staticmethod
    def _parse_issued_date(value: str) -> date | None:
        value = value.strip()
        value = re.sub(r"(\d)\.(\d{2}\s*[AP]M)", r"\1:\2", value, flags=re.IGNORECASE)
        date_part = re.match(
            r"(\d{1,2}[\-/][A-Za-z]{3,9}[\-/]\d{2,4}|\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4}|\d{4}-\d{2}-\d{2})",
            value,
            re.IGNORECASE,
        )
        token = date_part.group(1) if date_part else value.split()[0]

        formats = (
            "%d-%b-%Y",
            "%d-%B-%Y",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%d-%m-%y",
            "%d/%m/%y",
            "%Y-%m-%d",
        )
        for fmt in formats:
            try:
                return datetime.strptime(token.title() if "%b" in fmt or "%B" in fmt else token, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _extension(filename: str) -> str:
        dot = filename.rfind(".")
        return filename[dot:].lower() if dot >= 0 else ""
