"""
Reusable document OCR service for JTCS ERP modules.

Used by: SHCIL Stamp, Court Fee, DSC, PAN, Aadhaar, GST Certificate (future).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from app.exceptions.stamp_exceptions import OcrUserError
from app.services.ocr_engine import OcrEngineNotAvailableError, ocr_image_bytes, ocr_pdf_bytes

logger = logging.getLogger(__name__)


@dataclass
class DocumentOcrPayload:
    provider: str
    text: str
    confidence: float
    image_hash: str
    image_size: int
    raw_bytes: bytes


def image_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def extract_document(raw: bytes, *, ext: str) -> DocumentOcrPayload:
    if not raw:
        raise ValueError("Uploaded file is empty.")

    try:
        if ext == ".pdf":
            result = ocr_pdf_bytes(raw)
        else:
            result = ocr_image_bytes(raw)
    except OcrEngineNotAvailableError as exc:
        raise OcrUserError(str(exc)) from exc
    except Exception as exc:
        logger.error("Document OCR failed: %s", exc)
        raise ValueError(str(exc)) from exc

    if not result.text.strip():
        raise ValueError(
            "OCR completed but no readable text was found. Use a clearer certificate image and retry."
        )

    return DocumentOcrPayload(
        provider=result.provider,
        text=result.text,
        confidence=result.confidence,
        image_hash=image_hash(raw),
        image_size=len(raw),
        raw_bytes=raw,
    )
