"""Stamp module domain exceptions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExistingStampRecord:
    stamp_id: int
    transaction_id: int | None
    customer_name: str | None
    transaction_date: str
    certificate_number: str


class StampDuplicateError(ValueError):
    def __init__(self, existing: ExistingStampRecord):
        self.existing = existing
        if existing.transaction_id:
            detail = f"already sold in full (Transaction #{existing.transaction_id})"
        else:
            detail = f"already registered (Stamp Record #{existing.stamp_id}, no transaction posted)"
        super().__init__(
            f"Certificate Number '{existing.certificate_number}' {detail}."
        )


class OcrUserError(ValueError):
    """User-facing OCR error with explicit reason (never generic OCR Failed)."""

    USER_MESSAGE = "OCR Engine Not Installed. Administrator Contact Required."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.USER_MESSAGE)
