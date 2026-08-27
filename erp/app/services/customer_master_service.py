from __future__ import annotations

import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy.exc import IntegrityError

from app.customer_master.constants import (
    GROUP_TABS,
    MASTER_MANDATORY_FIELDS,
    OTHER_CUSTOMER_TYPE,
    OTHER_TYPE_MANDATORY_FIELDS,
    TAB_LABELS,
)
from app.customer_master.gst_state_codes import gst_code_for_state
from app.repositories.customer_repository import CustomerRepository
from app.services.customer_group_service import CustomerGroupService
from app.utils.db_session import persist

logger = logging.getLogger(__name__)

_PINCODE_API = "https://api.postalpincode.in/pincode/{pin}"


class DuplicateFieldError(ValueError):
    def __init__(self, field: str, duplicate: dict, message: str):
        super().__init__(message)
        self.field = field
        self.duplicate = duplicate


class DuplicateMobileWarning(ValueError):
    def __init__(self, duplicates: list[dict], message: str):
        super().__init__(message)
        self.duplicates = duplicates


class CustomerInUseError(ValueError):
    def __init__(self, usage: dict, message: str):
        super().__init__(message)
        self.usage = usage


_IN_USE_MESSAGE = (
    "This customer is linked to existing records and cannot be deleted or inactivated. "
    "Only Edit is allowed."
)
_IN_USE_PERMANENT_MESSAGE = (
    "This customer has linked records and cannot be permanently deleted."
)


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
        record = self.repository.get_full(customer_id)
        record.update(self._chart_group_fields(customer_id))
        record.update(self._income_expense_work_fields(customer_id))
        record["usage"] = self.repository.get_usage(customer_id)
        record["has_links"] = not record["usage"].get("can_delete", True)
        return record

    @staticmethod
    def _chart_group_fields(customer_id: int | None) -> dict:
        """Read Chart of Account group links (does not alter CustomerMaster table)."""
        empty = {"chart_group_ids": [], "chart_group_names": ""}
        if not customer_id:
            return empty
        try:
            from app.services.chart_account_service import ChartAccountService

            linked = ChartAccountService().get_customer_record(int(customer_id))
            return {
                "chart_group_ids": list(linked.get("group_ids") or []),
                "chart_group_names": linked.get("group_name") or "",
            }
        except Exception:
            return empty

    def _income_expense_work_fields(self, customer_id: int | None) -> dict:
        empty = {
            "income_expense_work_ids": [],
            "requires_income_expense_works": False,
        }
        if not customer_id:
            return empty
        try:
            work_ids = self.repository.list_income_expense_work_ids(int(customer_id))
            chart = self._chart_group_fields(customer_id)
            requires = self._requires_income_expense_works(
                chart.get("chart_group_ids") or [],
                customer_group=None,
            ) or bool(work_ids)
            return {
                "income_expense_work_ids": work_ids,
                "requires_income_expense_works": requires,
            }
        except Exception:
            return empty

    @staticmethod
    def _parse_id_list(raw) -> list[int]:
        if raw is None:
            return []
        if isinstance(raw, str):
            values = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        elif isinstance(raw, (list, tuple, set)):
            values = list(raw)
        else:
            values = [raw]
        ids: list[int] = []
        seen: set[int] = set()
        for value in values:
            try:
                num = int(value)
            except (TypeError, ValueError):
                continue
            if num <= 0 or num in seen:
                continue
            seen.add(num)
            ids.append(num)
        return ids

    @staticmethod
    def _group_text_is_income_expense(text: str) -> bool:
        t = (text or "").casefold()
        return any(
            token in t
            for token in (
                "income",
                "expense",
                "purchase",
                "sale",
                "sales",
                "salary",
                "wages",
                "contra",
            )
        )

    def _requires_income_expense_works(
        self,
        chart_group_ids: list[int],
        *,
        customer_group: str | None,
    ) -> bool:
        """True when selected chart groups (or customer group) are Income/Expense related."""
        if customer_group and self._group_text_is_income_expense(customer_group):
            return True
        if not chart_group_ids:
            return False
        try:
            from app.services.chart_group_service import ChartGroupService

            by_id = {
                int(g["group_id"]): g
                for g in ChartGroupService().list_active_for_dropdown()
            }
        except Exception:
            return False
        for gid in chart_group_ids:
            g = by_id.get(int(gid))
            if not g:
                continue
            blob = f"{g.get('label') or ''} {g.get('group_name') or ''} {g.get('under_type') or ''}"
            if self._group_text_is_income_expense(blob):
                return True
        return False

    def _sync_chart_groups(self, customer_id: int, payload: dict) -> None:
        """Persist Chart of Account groups for this customer (CoA table only)."""
        from app.services.chart_account_service import ChartAccountService

        raw = payload.get("chart_group_ids")
        if raw is None:
            raw = payload.get("group_ids")
        ChartAccountService().assign_customer_group(
            int(customer_id),
            {
                "group_ids": raw,
                "group_id": payload.get("group_id"),
                "opening_balance": payload.get("opening_balance")
                or payload.get("OpeningBalance"),
                "opening_balance_date": payload.get("opening_balance_date")
                or payload.get("OpeningBalanceDate"),
                "opening_balance_dr_cr": payload.get("opening_balance_dr_cr")
                or payload.get("OpeningBalanceDrCr"),
            },
        )

    def _sync_income_expense_works(self, customer_id: int, payload: dict) -> None:
        work_ids = self._parse_id_list(
            payload.get("income_expense_work_ids")
            if "income_expense_work_ids" in payload
            else payload.get("work_ids")
        )
        chart_ids = self._parse_id_list(
            payload.get("chart_group_ids")
            if payload.get("chart_group_ids") is not None
            else payload.get("group_ids")
        )
        requires = self._requires_income_expense_works(
            chart_ids,
            customer_group=(payload.get("customer_group") or ""),
        )
        if not requires or not work_ids:
            # Optional: clear links when not applicable or none selected.
            self.repository.replace_income_expense_work_ids(int(customer_id), [])
            return
        # Validate against active WorkMaster (read-only).
        from app.services.work_master_service import WorkMasterService

        active = {int(r["work_id"]) for r in WorkMasterService().list_records()}
        invalid = [wid for wid in work_ids if wid not in active]
        if invalid:
            raise ValueError("One or more Income/Expense work types are invalid or inactive.")
        self.repository.replace_income_expense_work_ids(int(customer_id), work_ids)

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

        chart_ids = self._parse_id_list(
            payload.get("chart_group_ids")
            if payload.get("chart_group_ids") is not None
            else payload.get("group_ids")
        )
        if not chart_ids:
            single = payload.get("group_id")
            if single is None:
                single = payload.get("GroupID")
            chart_ids = self._parse_id_list([single] if single not in (None, "") else [])
        if not chart_ids:
            raise ValueError("Select Chart of Account Group.")
        if not self.group_service.is_group_valid_for_chart(group, chart_ids[0]):
            raise ValueError(
                "Selected Customer Group is not valid for the selected Chart of Account Group."
            )

        gst_number = (payload.get("gst_number") or "").strip()
        filing_frequency = (payload.get("filing_frequency") or "").strip()
        if not gst_number:
            payload["filing_frequency"] = ""
        elif filing_frequency and filing_frequency not in ("Monthly", "Quarterly", "Yearly"):
            raise ValueError("Filing Frequency must be Monthly, Quarterly, or Yearly.")

        if self._is_other_customer_type(payload):
            self._apply_other_type_defaults(payload)

        required_fields = (
            OTHER_TYPE_MANDATORY_FIELDS
            if self._is_other_customer_type(payload)
            else MASTER_MANDATORY_FIELDS
        )
        for field in required_fields:
            value = (payload.get(field) or "").strip()
            if not value:
                label = field.replace("_", " ").title()
                raise ValueError(f"{label} is required.")

        # Format checks only when optional fields are filled (not mandatory).
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
        if entry_id and (payload.get("customer_status") or "").strip().lower() == "inactive":
            usage = self.repository.get_usage(int(entry_id))
            if not usage.get("can_delete"):
                raise CustomerInUseError(usage, _IN_USE_MESSAGE)

        # Chart of Account groups required (Sale/Purchase/Income/Expense/Contra — max 5).
        from app.services.chart_account_service import ChartAccountService

        ChartAccountService()._parse_groups(payload)

        def _write() -> dict:
            return self.repository.save_full(payload, customer_id=entry_id)

        # Income/Expense work types are optional — sync when provided, never block save.
        saved = persist(_write)
        cid = saved.get("customer_id") or entry_id
        if not cid:
            raise ValueError("Customer saved but ID is missing — cannot assign chart groups.")
        self._sync_chart_groups(int(cid), payload)

        def _sync_works() -> None:
            self._sync_income_expense_works(int(cid), payload)

        persist(_sync_works)
        saved.update(self._chart_group_fields(int(cid)))
        saved.update(self._income_expense_work_fields(int(cid)))
        return saved

    def delete_record(self, customer_id: int) -> str:
        usage = self.repository.get_usage(customer_id)
        row = self.repository.get_detail(customer_id)
        inactive = (row.get("CustomerStatus") or "").strip().lower() == "inactive"
        if not usage.get("can_delete"):
            raise CustomerInUseError(
                usage,
                _IN_USE_PERMANENT_MESSAGE if inactive else _IN_USE_MESSAGE,
            )

        def _write() -> str:
            if inactive:
                self.repository.purge(customer_id)
                return "Customer permanently deleted. This cannot be recovered."
            self.repository.deactivate(customer_id)
            return (
                "Customer marked inactive. Delete again to permanently remove "
                "(cannot be recovered)."
            )

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise CustomerInUseError(usage, _IN_USE_PERMANENT_MESSAGE) from exc

    def restore_record(self, customer_id: int) -> str:
        def _write() -> str:
            row = self.repository.get_detail(customer_id)
            status = (row.get("CustomerStatus") or "").strip().lower()
            if status == "active":
                raise ValueError("Customer is already active.")
            if status != "inactive":
                raise ValueError("Only inactive customers can be restored.")
            self.repository.activate(customer_id)
            return "Customer restored to Active."

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

    @staticmethod
    def lookup_pincode(pincode: str | None) -> dict:
        """Resolve India pincode → country / state / district for Address tab autofill."""
        pin = re.sub(r"\D", "", pincode or "")
        if len(pin) != 6:
            raise ValueError("Enter a valid 6-digit pincode.")

        url = _PINCODE_API.format(pin=pin)
        req = Request(url, headers={"User-Agent": "JTCS-ERP-CustomerMaster/1.0", "Accept": "application/json"})
        try:
            with urlopen(req, timeout=8) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("Pincode lookup failed for %s: %s", pin, exc)
            raise ValueError("Unable to look up pincode right now. Try again.") from exc

        row = payload[0] if isinstance(payload, list) and payload else {}
        if str(row.get("Status") or "").lower() != "success":
            raise ValueError(row.get("Message") or "Pincode not found.")

        offices = row.get("PostOffice") or []
        if not offices:
            raise ValueError("Pincode not found.")

        office = offices[0] if isinstance(offices[0], dict) else {}
        country = (office.get("Country") or "India").strip() or "India"
        state = (office.get("State") or "").strip()
        district = (office.get("District") or "").strip()
        if not state and not district:
            raise ValueError("Pincode found but address details are incomplete.")

        city = (office.get("Block") or office.get("Division") or office.get("Name") or district or "").strip()
        gst_code = gst_code_for_state(state)

        return {
            "ok": True,
            "pincode": pin,
            "country": country,
            "state": state,
            "district": district,
            "city": city,
            "state_gst_code": gst_code,
            "post_office": (office.get("Name") or "").strip(),
        }
