from __future__ import annotations

import re

from app.customer_master.constants import (
    GROUP_TABS,
    MASTER_MANDATORY_FIELDS,
    OTHER_CUSTOMER_TYPE,
    OTHER_TYPE_MANDATORY_FIELDS,
    TAB_LABELS,
)
from app.repositories.customer_repository import CustomerRepository
from app.services.customer_group_service import CustomerGroupService
from app.utils.db_session import persist


class DuplicateFieldError(ValueError):
    def __init__(self, field: str, duplicate: dict, message: str):
        super().__init__(message)
        self.field = field
        self.duplicate = duplicate


class DuplicateMobileWarning(ValueError):
    def __init__(self, duplicates: list[dict], message: str):
        super().__init__(message)
        self.duplicates = duplicates


class CustomerMasterService:
    def __init__(
        self,
        repository: CustomerRepository | None = None,
        group_service: CustomerGroupService | None = None,
    ):
        self.repository = repository or CustomerRepository()
        self.group_service = group_service or CustomerGroupService()

    @staticmethod
    def _normalize_email(value: str | None) -> str:
        return (value or "").strip()

    def list_records(
        self,
        *,
        search: str | None = None,
        customer_group: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        self.repository.ensure_schema()
        return self.repository.list_master(
            search=search,
            customer_group=customer_group,
            status=status,
        )

    def get_record(self, customer_id: int) -> dict:
        return self.repository.get_full(customer_id)

    def check_duplicates(
        self,
        *,
        pan: str | None = None,
        aadhaar: str | None = None,
        mobile: str | None = None,
        customer_id: int | None = None,
    ) -> dict:
        return {
            "pan_duplicate": self.repository.find_by_pan(pan or "", exclude_customer_id=customer_id),
            "aadhaar_duplicate": self.repository.find_by_aadhaar(
                aadhaar or "", exclude_customer_id=customer_id
            ),
            "mobile_duplicates": self.repository.find_by_mobile(
                mobile or "", exclude_customer_id=customer_id
            ),
        }

    @staticmethod
    def _is_other_customer_type(payload: dict) -> bool:
        return (payload.get("customer_type") or "").strip().casefold() == OTHER_CUSTOMER_TYPE.casefold()

    def _apply_other_type_defaults(self, payload: dict) -> None:
        """Other type: keep PAN present; blank PAN becomes reusable placeholder."""
        if not self._is_other_customer_type(payload):
            return
        pan = self.repository._normalize_pan(payload.get("pan_number"))
        if not pan:
            payload["pan_number"] = CustomerRepository.PLACEHOLDER_PAN

    def _validate_master_payload(self, payload: dict) -> None:
        active_codes = {item["code"] for item in self.group_service.list_active_groups()}
        group = (payload.get("customer_group") or "").strip().upper()
        if group not in active_codes:
            raise ValueError("Select a valid customer group.")

        gst_number = (payload.get("gst_number") or "").strip()
        filing_frequency = (payload.get("filing_frequency") or "").strip()
        if not gst_number:
            payload["filing_frequency"] = ""
        elif filing_frequency and filing_frequency not in ("Monthly", "Quarterly", "Yearly"):
            raise ValueError("Filing Frequency must be Monthly, Quarterly, or Yearly.")

        is_other = self._is_other_customer_type(payload)
        if is_other:
            self._apply_other_type_defaults(payload)
            for field in OTHER_TYPE_MANDATORY_FIELDS:
                value = (payload.get(field) or "").strip()
                if not value:
                    label = field.replace("_", " ").title()
                    raise ValueError(f"{label} is required.")
            pan = (payload.get("pan_number") or "").strip().upper()
            if pan and len(pan) != 10:
                raise ValueError("Valid 10-character PAN is required.")
            mobile = self.repository._normalize_mobile(payload.get("mobile_number"))
            if mobile and len(mobile) != 10:
                raise ValueError("Valid 10-digit mobile number is required.")
            aadhaar = re.sub(r"\D", "", payload.get("aadhaar_number") or "")
            if aadhaar and len(aadhaar) != 12:
                raise ValueError("Valid 12-digit Aadhaar is required.")
            email = self._normalize_email(payload.get("email_id"))
            if email and ("@" not in email or "." not in email.split("@")[-1]):
                raise ValueError("Valid email ID is required.")
            return

        for field in MASTER_MANDATORY_FIELDS:
            value = (payload.get(field) or "").strip()
            if not value:
                label = field.replace("_", " ").title()
                raise ValueError(f"{label} is required.")

        mobile = self.repository._normalize_mobile(payload.get("mobile_number"))
        if not mobile or len(mobile) != 10:
            raise ValueError("Valid 10-digit mobile number is required.")

        aadhaar = re.sub(r"\D", "", payload.get("aadhaar_number") or "")
        if len(aadhaar) != 12:
            raise ValueError("Valid 12-digit Aadhaar is required.")

        pan = (payload.get("pan_number") or "").strip().upper()
        if len(pan) != 10:
            raise ValueError("Valid 10-character PAN is required.")

        email = self._normalize_email(payload.get("email_id"))
        if "@" not in email or "." not in email.split("@")[-1]:
            raise ValueError("Valid email ID is required.")

    def _check_blocking_duplicates(self, payload: dict, customer_id: int | None) -> None:
        pan_dup = self.repository.find_by_pan(payload.get("pan_number") or "", exclude_customer_id=customer_id)
        if pan_dup:
            raise DuplicateFieldError(
                "pan_number",
                pan_dup,
                f"PAN already exists for customer {pan_dup['customer_name']} (ID {pan_dup['customer_id']}).",
            )
        aadhaar_raw = (payload.get("aadhaar_number") or "").strip()
        if not aadhaar_raw:
            return
        aadhaar_dup = self.repository.find_by_aadhaar(
            aadhaar_raw, exclude_customer_id=customer_id
        )
        if aadhaar_dup:
            raise DuplicateFieldError(
                "aadhaar_number",
                aadhaar_dup,
                f"Aadhaar already exists for customer {aadhaar_dup['customer_name']} (ID {aadhaar_dup['customer_id']}).",
            )

    def _check_mobile_duplicate(self, payload: dict, customer_id: int | None, *, allow: bool) -> None:
        mobile_dups = self.repository.find_by_mobile(
            payload.get("mobile_number") or "", exclude_customer_id=customer_id
        )
        if mobile_dups and not allow:
            raise DuplicateMobileWarning(
                mobile_dups,
                "Mobile number already exists for other customer(s). You may still proceed if intended.",
            )

    def save_record(
        self,
        payload: dict,
        *,
        customer_id: int | None = None,
        allow_duplicate_mobile: bool = False,
    ) -> dict:
        self._validate_master_payload(payload)

        entry_id = customer_id
        if entry_id is None:
            raw_id = payload.get("customer_id")
            if raw_id not in (None, "", "0"):
                try:
                    entry_id = int(raw_id)
                except (TypeError, ValueError):
                    entry_id = None

        self._check_blocking_duplicates(payload, entry_id)
        self._check_mobile_duplicate(payload, entry_id, allow=allow_duplicate_mobile)

        def _write() -> dict:
            return self.repository.save_full(payload, customer_id=entry_id)

        return persist(_write)

    def delete_record(self, customer_id: int) -> str:
        def _write() -> str:
            row = self.repository.get_detail(customer_id)
            if (row.get("CustomerStatus") or "").lower() == "inactive":
                raise ValueError("Customer is already inactive.")
            self.repository.deactivate(customer_id)
            return "Customer marked inactive successfully."

        return persist(_write)

    def ui_config(self) -> dict:
        self.group_service.repository.ensure_schema()
        try:
            self.repository.ensure_schema()
        except Exception:
            from app.extensions import db

            db.session.rollback()
        return {
            "groups": self.group_service.list_active_groups(),
            "group_tabs": self.group_service.build_group_tabs_map(),
            "tab_labels": TAB_LABELS,
            "mandatory_fields": sorted(MASTER_MANDATORY_FIELDS),
            "other_type_mandatory_fields": sorted(OTHER_TYPE_MANDATORY_FIELDS),
            "other_customer_type": OTHER_CUSTOMER_TYPE,
            "placeholder_pan": CustomerRepository.PLACEHOLDER_PAN,
        }
