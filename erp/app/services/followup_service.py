from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.repositories.customer_repository import CustomerRepository
from app.repositories.followup_repository import FollowupRepository
from app.services.followup_payment_service import FollowupPaymentService
from app.utils.db_session import persist


IDSIGN_STATUS_URL = "https://dsc.idsignca.com/ekycadmin/signup/webstatus"


MODULE_META = {
    "ITR": {
        "code": "ITR",
        "title": "ITR",
        "subtitle": "ITR filing and compliance",
        "menu_path": "/itr/followup",
        "has_return_type": True,
        "work_type_label": "ITR",
    },
    "DSC": {
        "code": "DSC",
        "title": "DSC",
        "subtitle": "DSC application follow-up",
        "menu_path": "/dsc/followup",
        "has_return_type": False,
        "work_type_label": "DSC",
    },
    "TDS": {
        "code": "TDS",
        "title": "TDS",
        "subtitle": "TDS payment follow-up",
        "menu_path": "/tds/followup",
        "has_return_type": False,
        "has_tds_period_split": True,
        "work_type_label": "TDS",
    },
    "GST": {
        "code": "GST",
        "title": "GST",
        "subtitle": "GST return follow-up",
        "menu_path": "/gst/followup",
        "has_return_type": False,
        "has_gst_fields": False,  # Filing Frequency / Return Type removed from GST Followup
        "work_type_label": "GST",
    },
}


DSC_APPLICATION_STAGE_CODES = frozenset({"application_received", "application_no"})

TDS_FORM_TYPES = ("Original", "Revised")
TDS_QUARTERS = ("Q1", "Q2", "Q3", "Q4")
GST_RETURN_TYPES = ("GSTR1", "GSTR3B", "GSTR7", "GSTR-Others")
GST_FILING_FREQUENCIES = ("Monthly", "Quarterly", "Yearly")


def current_fy_start_year(today: date | None = None) -> int:
    today = today or date.today()
    return today.year if today.month >= 4 else today.year - 1


def tax_period_for_year(start_year: int) -> str:
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def tax_period_options(*, years_back: int = 3, years_forward: int = 1, today: date | None = None) -> list[str]:
    today = today or date.today()
    current = current_fy_start_year(today)
    start_year = current - years_back
    end_year = current + years_forward
    return [tax_period_for_year(y) for y in range(end_year, start_year - 1, -1)]


def default_tax_period(today: date | None = None) -> str:
    return tax_period_for_year(current_fy_start_year(today))


class FollowupService:
    def __init__(
        self,
        module_code: str,
        *,
        followup_repo: FollowupRepository | None = None,
        customer_repo: CustomerRepository | None = None,
    ):
        code = (module_code or "").strip().upper()
        if code not in MODULE_META:
            raise ValueError(f"Unknown followup module: {module_code}")
        self.module_code = code
        self.meta = MODULE_META[code]
        self.followup_repo = followup_repo or FollowupRepository()
        self.customer_repo = customer_repo or CustomerRepository()

    @staticmethod
    def _stage_dict(row) -> dict:
        return {
            "stage_id": row.StageID,
            "module_code": row.ModuleCode,
            "stage_code": row.StageCode,
            "stage_name": row.StageName,
            "display_order": row.DisplayOrder,
            "active_status": bool(row.ActiveStatus),
        }

    @staticmethod
    def _entry_dict(row, *, stages: list | None = None, available_cols: set[str] | None = None) -> dict:
        completed = stages or []
        available_cols = available_cols or set()
        bill_amount = None
        if "BillAmount" in available_cols:
            bill_val = getattr(row, "BillAmount", None)
            bill_amount = float(bill_val) if bill_val is not None else None
        itr_filed_date = None
        if "ITRFiledDate" in available_cols:
            itr_val = getattr(row, "ITRFiledDate", None)
            itr_filed_date = itr_val.isoformat() if itr_val else None
        return_filing_status = None
        if "ReturnFilingStatus" in available_cols:
            return_filing_status = getattr(row, "ReturnFilingStatus", None)
        filing_date = None
        if "FilingDate" in available_cols:
            filing_val = getattr(row, "FilingDate", None)
            filing_date = filing_val.isoformat() if filing_val else None
        application_number = None
        if "ApplicationNumber" in available_cols:
            application_number = getattr(row, "ApplicationNumber", None)
        location = None
        if "Location" in available_cols:
            location = getattr(row, "Location", None)
        introduced_by = None
        if "IntroducedBy" in available_cols:
            introduced_by = getattr(row, "IntroducedBy", None)
        form_type = None
        if "FormType" in available_cols:
            form_type = getattr(row, "FormType", None)
        quarter = None
        if "Quarter" in available_cols:
            quarter = getattr(row, "Quarter", None)
        return {
            "entry_id": row.EntryID,
            "module_code": row.ModuleCode,
            "work_date": row.WorkDate.isoformat() if row.WorkDate else None,
            "tax_period": row.TaxPeriod,
            "customer_id": row.CustomerID,
            "return_type": row.ReturnType,
            "form_type": form_type,
            "quarter": quarter,
            "application_number": application_number,
            "location": location,
            "introduced_by": introduced_by,
            "bill_no": row.BillNo,
            "bill_date": row.BillDate.isoformat() if row.BillDate else None,
            "bill_amount": bill_amount,
            "itr_filed_date": itr_filed_date,
            "return_filing_status": return_filing_status,
            "filing_date": filing_date,
            "pan_number": row.PANNumber,
            "remarks": row.Remarks,
            "reason_for_unverified": row.ReasonForUnverified,
            "stage_ids": [s.StageID for s in (row.stages or [])],
            "completed_stages": completed,
            "workflow_status": FollowupRepository._workflow_status(
                completed,
                [],
            ),
        }

    def list_stages(self, *, active_only: bool = True) -> list[dict]:
        if self.module_code == "GST":
            try:
                self.followup_repo.ensure_gst_return_filed_stage()
            except Exception:
                self.followup_repo.session.rollback()
        rows = self.followup_repo.list_stages(self.module_code, active_only=active_only)
        return [self._stage_dict(row) for row in rows]

    def list_entries(
        self,
        *,
        search: str | None = None,
        status_filter: str | None = None,
        tax_period: str | None = None,
        return_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        if self.module_code == "ITR":
            self.followup_repo.ensure_filing_status_columns()
        if self.module_code == "TDS":
            self.followup_repo.ensure_tds_period_columns()
        # Progressive exclusive-bucket status filter (ITR + DSC).
        # Other modules keep repository tick-based status filtering.
        repo_status = None if self.module_code in {"ITR", "DSC"} else status_filter
        rows = self.followup_repo.list_entries(
            self.module_code,
            search=search,
            status_filter=repo_status,
            tax_period=tax_period,
            return_type=return_type,
            date_from=date_from,
            date_to=date_to,
        )
        for row in rows:
            if row.get("WorkDate"):
                row["work_date"] = row["WorkDate"].isoformat() if hasattr(row["WorkDate"], "isoformat") else str(row["WorkDate"])
            if row.get("BillDate"):
                row["bill_date"] = row["BillDate"].isoformat() if hasattr(row["BillDate"], "isoformat") else str(row["BillDate"])
            if row.get("CreatedDate"):
                row["created_date"] = row["CreatedDate"].isoformat() if hasattr(row["CreatedDate"], "isoformat") else str(row["CreatedDate"])
            row["entry_id"] = row.get("EntryID")
            row["customer_name"] = row.get("CustomerName") or ""
            row["mobile_number"] = row.get("MobileNumber") or ""
            row["email_id"] = row.get("EmailID") or row.get("email_id") or ""
            row["pan_number"] = row.get("PANNumber") or row.get("pan_number") or ""
            row["return_type"] = row.get("ReturnType")
            row["application_number"] = row.get("ApplicationNumber")
            row["location"] = row.get("Location")
            row["introduced_by"] = row.get("IntroducedBy")
            if self.module_code == "DSC" and not row["application_number"] and row.get("BillNo"):
                completed_codes = {
                    (s.get("StageCode") or "").lower() for s in row.get("completed_stages", [])
                }
                if "tally_bill_generated" not in completed_codes and "payment_received" not in completed_codes:
                    row["application_number"] = row.get("BillNo")
            row["bill_no"] = row.get("BillNo")
            row["bill_date"] = row.get("BillDate")
            if row.get("BillDate") and hasattr(row["BillDate"], "isoformat"):
                row["bill_date"] = row["BillDate"].isoformat()
            row["bill_amount"] = float(row["BillAmount"]) if row.get("BillAmount") is not None else None
            if row.get("ITRFiledDate") and hasattr(row["ITRFiledDate"], "isoformat"):
                row["itr_filed_date"] = row["ITRFiledDate"].isoformat()
            else:
                row["itr_filed_date"] = row.get("ITRFiledDate")
            row["return_filing_status"] = row.get("ReturnFilingStatus") or row.get("return_filing_status")
            if row.get("FilingDate") and hasattr(row["FilingDate"], "isoformat"):
                row["filing_date"] = row["FilingDate"].isoformat()
            else:
                row["filing_date"] = row.get("FilingDate") or row.get("filing_date")
            row["remarks"] = row.get("Remarks")
            row["reason_for_unverified"] = row.get("ReasonForUnverified")
            row["tax_period"] = row.get("TaxPeriod")
            row["form_type"] = row.get("FormType")
            row["quarter"] = row.get("Quarter")
            row["filing_frequency"] = row.get("FilingFrequency") or row.get("filing_frequency") or ""
            row["stage_ids"] = [s["StageID"] for s in row.get("completed_stages", [])]
            row["has_tally_bill"] = bool(
                row.get("has_tally_bill")
                or row.get("bill_no")
                or any(
                    (s.get("StageCode") or "").lower() == "tally_bill_generated"
                    for s in row.get("completed_stages", [])
                )
                or (row.get("workflow_status") or "") == "Tally Bill Generated"
            )
        if self.module_code == "ITR":
            self._heal_itr_payment_status_rows(rows)
            self._attach_itr_payment_receive_dates(rows)
            if status_filter:
                rows = self._filter_entries_by_status(rows, status_filter, module_code="ITR")
        elif self.module_code == "DSC":
            if status_filter:
                rows = self._filter_entries_by_status(rows, status_filter, module_code="DSC")
        return rows

    def _attach_itr_payment_receive_dates(self, rows: list[dict]) -> None:
        """ITR grid: payment receive date(s) only when Payment Received is ticked."""
        bill_nos = {
            (row.get("bill_no") or row.get("BillNo") or "").strip().upper()
            for row in rows
            if row.get("payment_received")
            and (row.get("bill_no") or row.get("BillNo") or "").strip()
        }
        dates_map: dict[str, list[str]] = {}
        if bill_nos:
            dates_map = FollowupPaymentService("ITR").payment_dates_by_bills(bill_nos)

        for row in rows:
            if not row.get("payment_received"):
                row["payment_receive_dates"] = []
                row["payment_receive_date"] = ""
                continue
            bill = (row.get("bill_no") or row.get("BillNo") or "").strip().upper()
            dates = list(dates_map.get(bill) or [])
            row["payment_receive_dates"] = dates
            row["payment_receive_date"] = ", ".join(dates)

    @staticmethod
    def _completed_stage_codes(row: dict) -> set[str]:
        return {
            (es.get("StageCode") or "").lower()
            for es in (row.get("completed_stages") or [])
            if (es.get("StageCode") or "").strip()
        }

    @classmethod
    def _itr_progress_bucket(cls, row: dict) -> str:
        """ITR Excel card bucket: furthest progress tick, exclusive of later stages.

        PENDING → only pending (no later ticks)
        DOCUMENTS RECEIVED → docs ticked, later not
        ITR FILED → itr filed ticked, later not
        TALLY BILL GENERATED / PAYMENT PENDING → bill ticked, payment not
        PAYMENT RECEIVED → all ticks / payment received
        """
        codes = cls._completed_stage_codes(row)
        status = (row.get("workflow_status") or "").strip()
        if status == "Unverified" or "unverified" in codes:
            return "unverified"
        if row.get("payment_received") or "payment_received" in codes:
            return "payment_received"
        if "tally_bill_generated" in codes or status == "Tally Bill Generated":
            return "tally_bill_generated"
        if "itr_filed" in codes or status == "ITR Filed":
            return "itr_filed"
        if "documents_received" in codes or status == "Documents Received":
            return "documents_received"
        return "pending"

    @classmethod
    def _dsc_progress_bucket(cls, row: dict) -> str:
        """DSC card bucket: furthest progress tick, exclusive of later stages (ITR-style).

        PENDING → no progress ticks
        DOCUMENTS RECEIVED → docs ticked, later not
        APPLICATION → application ticked, later not
        KYC / DOWNLOAD STATUS → same exclusive rule
        TALLY BILL GENERATED / PAYMENT PENDING → bill ticked, payment not
        PAYMENT RECEIVED → payment received
        """
        codes = cls._completed_stage_codes(row)
        status = (row.get("workflow_status") or "").strip()
        status_l = status.lower()
        if status == "Unverified" or "unverified" in codes:
            return "unverified"
        if row.get("payment_received") or "payment_received" in codes:
            return "payment_received"
        if "tally_bill_generated" in codes or status == "Tally Bill Generated":
            return "tally_bill_generated"
        if "download_status" in codes or status == "Download Status":
            return "download_status"
        if "kyc" in codes or status_l == "kyc":
            return "kyc"
        if (
            "application_received" in codes
            or "application_no" in codes
            or any(c.startswith("application") for c in codes)
            or status_l.startswith("application")
        ):
            return "application_received"
        if "documents_received" in codes or status == "Documents Received":
            return "documents_received"
        return "pending"

    @classmethod
    def _progress_bucket(cls, row: dict, module_code: str) -> str:
        if module_code == "DSC":
            return cls._dsc_progress_bucket(row)
        return cls._itr_progress_bucket(row)

    @classmethod
    def _filter_entries_by_status(
        cls, rows: list[dict], status_filter: str, *, module_code: str = "ITR"
    ) -> list[dict]:
        """Exclusive progressive current-stage buckets (ITR Excel / DSC same logic)."""
        sf = (status_filter or "").strip().lower()
        if not sf:
            return rows
        if sf.startswith("unticked:"):
            # Legacy card filter values → same progressive bucket
            sf = sf.split(":", 1)[1].strip()
            if not sf:
                return rows
        # Excel: PAYMENT PENDING = BILL GENERATED without payment received
        if sf == "payment_pending":
            return [
                r
                for r in rows
                if cls._progress_bucket(r, module_code) == "tally_bill_generated"
            ]
        itr_codes = {
            "pending",
            "documents_received",
            "itr_filed",
            "tally_bill_generated",
            "payment_received",
            "unverified",
        }
        dsc_codes = {
            "pending",
            "documents_received",
            "application_received",
            "application_no",
            "kyc",
            "download_status",
            "tally_bill_generated",
            "payment_received",
            "unverified",
        }
        valid = dsc_codes if module_code == "DSC" else itr_codes
        if sf in valid or (module_code == "DSC" and sf.startswith("application")):
            bucket_key = "application_received" if sf.startswith("application") else sf
            return [
                r for r in rows if cls._progress_bucket(r, module_code) == bucket_key
            ]
        return [
            r
            for r in rows
            if (r.get("workflow_status") or "").lower() == sf.replace("_", " ")
        ]

    def _heal_itr_payment_status_rows(self, rows: list[dict]) -> None:
        """ITR-only: if payment was posted but payment_received stage was dropped, fix status."""
        if not rows:
            return
        payment_stage = self.followup_repo.get_stage_by_code("ITR", "payment_received")
        if payment_stage is None:
            return
        candidates: list[tuple[dict, str]] = []
        for row in rows:
            if row.get("payment_received"):
                continue
            bill_no = (row.get("bill_no") or row.get("BillNo") or "").strip()
            if not bill_no:
                continue
            completed_codes = {
                (s.get("StageCode") or "").lower() for s in row.get("completed_stages") or []
            }
            if "payment_received" in completed_codes:
                continue
            candidates.append((row, bill_no))
        if not candidates:
            return
        paid = FollowupPaymentService("ITR").bills_with_posted_payment({b for _, b in candidates})
        if not paid:
            return
        for row, bill_no in candidates:
            if bill_no.strip().upper() not in paid:
                continue
            completed = list(row.get("completed_stages") or [])
            completed.append(
                {
                    "StageID": payment_stage.StageID,
                    "StageCode": payment_stage.StageCode,
                    "StageName": payment_stage.StageName,
                    "DisplayOrder": payment_stage.DisplayOrder,
                }
            )
            row["completed_stages"] = completed
            row["stage_ids"] = [s["StageID"] for s in completed]
            row["payment_received"] = True
            row["workflow_status"] = payment_stage.StageName or "Payment Received"

    @staticmethod
    def received_amount_for_letter(record: dict) -> float:
        """Cash/bank amount actually received — excludes उधार / credit lines."""
        from app.services.followup_payment_service import FollowupPaymentService

        payments = record.get("payments") or []
        total = 0.0
        saw_payment = False
        for payment in payments:
            saw_payment = True
            if FollowupPaymentService.is_udhaar_payment_line(payment):
                continue
            try:
                total += float(payment.get("amount") or 0)
            except (TypeError, ValueError):
                continue
        if saw_payment:
            return total
        try:
            return float(record.get("bill_amount") or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def udhaar_amount_for_record(record: dict) -> float:
        from app.services.followup_payment_service import FollowupPaymentService

        total = 0.0
        for payment in record.get("payments") or []:
            if not FollowupPaymentService.is_udhaar_payment_line(payment):
                continue
            try:
                total += float(payment.get("amount") or 0)
            except (TypeError, ValueError):
                continue
        return total

    def stats(
        self,
        *,
        search: str | None = None,
        tax_period: str | None = None,
        return_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        """Card totals.

        ITR + DSC: Excel progressive buckets (current furthest stage only).
        Other modules: count of cases with each stage tick.
        """
        rows = self.list_entries(
            search=search,
            tax_period=tax_period,
            return_type=return_type,
            date_from=date_from,
            date_to=date_to,
        )
        total = len(rows)

        if self.module_code in {"ITR", "DSC"}:
            buckets: dict[str, int] = {}
            for row in rows:
                key = self._progress_bucket(row, self.module_code)
                buckets[key] = buckets.get(key, 0) + 1
            pending = buckets.get("pending", 0)
            payment_received = buckets.get("payment_received", 0)
            # Excel: PAYMENT PENDING = BILL GENERATED without payment received
            payment_pending = buckets.get("tally_bill_generated", 0)
            by_status: dict[str, int] = {}
            for stage in self.list_stages():
                code = (stage.get("stage_code") or "").strip().lower()
                name = (stage.get("stage_name") or "").strip()
                if not name:
                    continue
                bucket_code = (
                    "application_received"
                    if self.module_code == "DSC" and code.startswith("application")
                    else code
                )
                by_status[name] = buckets.get(bucket_code, 0)
            return {
                "total": total,
                "pending": pending,
                "payment_received": payment_received,
                "payment_pending": payment_pending,
                "by_status": by_status,
            }

        pending = sum(1 for r in rows if (r.get("workflow_status") or "Pending") == "Pending")
        payment_received = sum(1 for r in rows if r.get("payment_received"))
        by_status = {}
        for stage in self.list_stages():
            code = (stage.get("stage_code") or "").strip().lower()
            name = (stage.get("stage_name") or "").strip()
            if not name:
                continue
            by_status[name] = sum(
                1
                for r in rows
                if any(
                    (es.get("StageCode") or "").lower() == code
                    for es in (r.get("completed_stages") or [])
                )
            )
        return {
            "total": total,
            "pending": pending,
            "payment_received": payment_received,
            "payment_pending": total - payment_received,
            "by_status": by_status,
        }

    def get_entry(self, entry_id: int) -> dict:
        if self.module_code == "TDS":
            self.followup_repo.ensure_tds_period_columns()
        row = self.followup_repo.get_entry(entry_id)
        if row is None or not row.IsActive or row.ModuleCode != self.module_code:
            raise ValueError("Followup entry not found.")
        customer = self.customer_repo.get_detail(row.CustomerID)
        completed = [
            {
                "StageID": es.StageID,
                "StageCode": es.stage.StageCode if es.stage else "",
                "StageName": es.stage.StageName if es.stage else "",
                "DisplayOrder": es.stage.DisplayOrder if es.stage else 0,
            }
            for es in sorted(row.stages or [], key=lambda x: (x.stage.DisplayOrder if x.stage else 0))
        ]
        all_stages = self.followup_repo.list_stages(self.module_code)
        available_cols = self.followup_repo.entry_master_columns()
        data = self._entry_dict(row, stages=completed, available_cols=available_cols)
        data["workflow_status"] = FollowupRepository._workflow_status(completed, all_stages)
        if self.module_code == "DSC":
            completed_codes = {s.get("StageCode") for s in completed}
            if not data.get("application_number") and data.get("bill_no"):
                if (
                    "tally_bill_generated" not in completed_codes
                    and "payment_received" not in completed_codes
                ):
                    data["application_number"] = data["bill_no"]
                    data["bill_no"] = None
            data["application_locked"] = bool(data.get("application_number"))
        data["customer_name"] = customer.get("CustomerName") or ""
        data["mobile_number"] = customer.get("MobileNumber") or ""
        data["email_id"] = customer.get("EmailID") or customer.get("email_id") or ""
        data["pan_number"] = (
            data.get("pan_number")
            or customer.get("PANNumber")
            or customer.get("pan_number")
            or ""
        )
        if self.meta.get("has_gst_fields"):
            self.customer_repo.ensure_schema()
            data["filing_frequency"] = (
                customer.get("FilingFrequency")
                or customer.get("filing_frequency")
                or ""
            )
        payment_service = FollowupPaymentService(self.module_code)
        if data.get("bill_no"):
            daily = payment_service.find_daily_for_bill(data["bill_no"])
            if daily is not None:
                data["payments"] = payment_service.load_payment_lines(daily)
                data["daily_transaction_id"] = daily.TransactionID
                received = self.received_amount_for_letter({**data, "payments": data["payments"]})
                data["received_amount"] = received
                if self.module_code == "ITR":
                    bill_val = float(data.get("bill_amount") or 0)
                    if bill_val <= 0 and received > 0:
                        data["bill_amount"] = received
                    elif bill_val <= 0 and daily.SaleAmount:
                        data["bill_amount"] = float(daily.SaleAmount)
                    # Ensure Payment Received stage is present in the edit form when
                    # payment was posted but the stage row was previously dropped.
                    completed_codes = {
                        (s.get("StageCode") or "").lower() for s in (data.get("completed_stages") or [])
                    }
                    if "payment_received" not in completed_codes:
                        payment_stage = self.followup_repo.get_stage_by_code("ITR", "payment_received")
                        if payment_stage is not None:
                            completed = list(data.get("completed_stages") or [])
                            completed.append(
                                {
                                    "StageID": payment_stage.StageID,
                                    "StageCode": payment_stage.StageCode,
                                    "StageName": payment_stage.StageName,
                                    "DisplayOrder": payment_stage.DisplayOrder,
                                }
                            )
                            data["completed_stages"] = completed
                            data["stage_ids"] = [s["StageID"] for s in completed]
                            data["workflow_status"] = payment_stage.StageName or "Payment Received"
        return data

    @classmethod
    def _fetch_idsign_webstatus_html(cls, reference_no: str) -> str:
        """Fetch raw HTML from ID Sign webstatus page for ReferenceNo."""
        ref = (reference_no or "").strip()
        if not ref:
            raise ValueError("Application number is required to sync status.")
        url = f"{IDSIGN_STATUS_URL}?ReferenceNo={quote(ref)}"
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; JTCS-DSC-Sync/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urlopen(request, timeout=25) as response:
                raw = response.read()
        except HTTPError as exc:
            raise ValueError(f"ID Sign status page returned HTTP {exc.code}.") from exc
        except URLError as exc:
            raise ValueError(f"Unable to reach ID Sign status page: {exc.reason}") from exc
        return raw.decode("utf-8", errors="ignore")

    @classmethod
    def _fetch_idsign_latest_status(cls, reference_no: str) -> str:
        """Fetch latest status text from ID Sign webstatus page for ReferenceNo."""
        html = cls._fetch_idsign_webstatus_html(reference_no)
        statuses = cls._parse_idsign_status_rows(html)
        if not statuses:
            raise ValueError(
                f"No status found on ID Sign for Reference No. {reference_no.strip()}. "
                "Verify the application number."
            )
        # Always take the LAST status row from the table (e.g. Token Issued / VIDEO PENDING).
        return statuses[-1]

    @classmethod
    def _fetch_idsign_status_details(cls, reference_no: str) -> dict:
        """Fetch latest status + Reject comment(IF ANY) from ID Sign webstatus."""
        html = cls._fetch_idsign_webstatus_html(reference_no)
        statuses = cls._parse_idsign_status_rows(html)
        if not statuses:
            raise ValueError(
                f"No status found on ID Sign for Reference No. {reference_no.strip()}. "
                "Verify the application number."
            )
        return {
            "status": statuses[-1],
            "reject_comment": cls._parse_idsign_reject_comment(html),
        }

    @staticmethod
    def _parse_idsign_reject_comment(html: str) -> str | None:
        """Extract Reject comment(IF ANY) value from ID Sign webstatus HTML/text."""
        if not html:
            return None
        # Normalize tags to spaces so label/value survive markup splits.
        text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
        text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        match = re.search(
            r"Reject\s*comment\s*\(\s*IF\s*ANY\s*\)\s*:\s*(.*)$",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        value = (match.group(1) or "").strip()
        # Trim trailing punctuation noise commonly present on ID Sign pages.
        value = value.strip(" ,;|")
        return value or None

    @staticmethod
    def _parse_idsign_status_rows(html: str) -> list[str]:
        """Extract status labels from ID Sign webstatus table (last row = latest)."""
        statuses: list[str] = []
        skip = {
            "status",
            "date&time",
            "date & time",
            "date&amp;time",
            "date",
            "time",
        }

        # Prefer full <tr> blocks with first cell = status (date cell may be blank).
        tr_re = re.compile(r"<tr[^>]*>(.*?)</tr>", flags=re.IGNORECASE | re.DOTALL)
        td_re = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", flags=re.IGNORECASE | re.DOTALL)
        for tr_html in tr_re.findall(html or ""):
            cells = []
            for cell_html in td_re.findall(tr_html):
                text = re.sub(r"<[^>]+>", " ", cell_html)
                text = re.sub(r"\s+", " ", text).strip()
                cells.append(text)
            if not cells:
                continue
            label = cells[0]
            if not label or label.lower() in skip:
                continue
            # Skip pure date-looking first cells
            if re.match(
                r"^\d{4}-\d{2}-\d{2}|^\d{2}[-/]\d{2}[-/]\d{4}",
                label,
            ):
                continue
            statuses.append(label)

        if statuses:
            return statuses

        # Fallback: known phrases — pick the one that appears last in the HTML.
        html_lower = (html or "").lower()
        best_phrase = None
        best_pos = -1
        for phrase in (
            "Token Issued",
            "Ready to Download- Download PIN SET",
            "Ready to Download - Download PIN SET",
            "Ready to Download",
            "VIDEO PENDING",
            "Pending eSign",
            "Hold for Documents",
            "Initial Approved",
            "Final Approved",
            "Pending CA Approval",
            "Submit For Approval",
            "Customer Submit",
        ):
            pos = html_lower.rfind(phrase.lower())
            if pos > best_pos:
                best_pos = pos
                best_phrase = phrase
        return [best_phrase] if best_phrase else []

    def sync_idsign_status(self, entry_id: int) -> dict:
        """DSC only: pull latest ID Sign status (last table row) into Remarks."""
        if self.module_code != "DSC":
            raise ValueError("ID Sign sync is only available for DSC followup.")
        row = self.followup_repo.get_entry(entry_id)
        if row is None or not row.IsActive or row.ModuleCode != self.module_code:
            raise ValueError("Followup entry not found.")

        available_cols = self.followup_repo.entry_master_columns()
        application_no = None
        if "ApplicationNumber" in available_cols:
            application_no = (getattr(row, "ApplicationNumber", None) or "").strip() or None
        if not application_no:
            application_no = (row.BillNo or "").strip() or None
        if not application_no:
            raise ValueError("Application number is missing for this record.")

        details = self._fetch_idsign_status_details(application_no)
        latest_status = details["status"]
        remarks = latest_status[:500]
        # Reuse existing FollowupEntryMaster.ReasonForUnverified for DSC Reject Comment
        # (DSC workflow has no Unverified stage). No schema change.
        reject_comment = details.get("reject_comment")
        reject_stored = (reject_comment[:500] if reject_comment else None)

        def _write():
            self.followup_repo.update_entry(
                row,
                {
                    "Remarks": remarks,
                    "ReasonForUnverified": reject_stored,
                },
            )
            return {
                "entry_id": entry_id,
                "application_number": application_no,
                "remarks": remarks,
                "status": latest_status,
                "reason_for_unverified": reject_stored,
                "reject_comment": reject_stored,
                "message": "ID Sign status synced to Remarks.",
            }

        return persist(_write)

    def _parse_work_date(self, payload: dict) -> date:
        raw = (payload.get("work_date") or payload.get("WorkDate") or "").strip()
        try:
            return date.fromisoformat(raw[:10])
        except ValueError as exc:
            raise ValueError("Valid work date is required.") from exc

    def _parse_stage_ids(self, payload: dict) -> list[int]:
        raw = payload.get("stage_ids") or payload.get("StageIDs")
        if raw is None:
            raw = payload.getlist("stage_ids") if hasattr(payload, "getlist") else []
        if isinstance(raw, str):
            raw = [part.strip() for part in raw.split(",") if part.strip()]
        ids: list[int] = []
        for item in raw or []:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
        valid = {s.StageID for s in self.followup_repo.list_stages(self.module_code)}
        return [sid for sid in ids if sid in valid]

    def _parse_optional_date(self, payload: dict, *keys: str) -> date | None:
        for key in keys:
            raw = payload.get(key)
            if raw in (None, ""):
                continue
            try:
                return date.fromisoformat(str(raw).strip()[:10])
            except ValueError:
                continue
        return None

    def _parse_bill_amount(self, payload: dict):
        raw = payload.get("bill_amount") or payload.get("BillAmount")
        if raw in (None, ""):
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            raise ValueError("Valid bill amount is required.") from None

    def _stage_codes_from_ids(self, stage_ids: list[int]) -> set[str]:
        stages = self.followup_repo.list_stages(self.module_code)
        id_to_code = {s.StageID: s.StageCode for s in stages}
        return {id_to_code[sid] for sid in stage_ids if sid in id_to_code}

    @staticmethod
    def _normalize_itr_return_type(return_type: str | None) -> str:
        rt = (return_type or "Original").strip()
        if not rt:
            return "Original"
        compact = rt.lower().replace(" ", "")
        if compact == "original":
            return "Original"
        if compact == "revised":
            return "Revised1"
        match = re.match(r"^revised(\d+)$", compact)
        if match:
            return f"Revised{match.group(1)}"
        return rt

    @staticmethod
    def _normalize_gst_return_type(return_type: str | None) -> str:
        rt = (return_type or "").strip()
        if not rt:
            raise ValueError("Return type is required.")
        aliases = {
            "gstr1": "GSTR1",
            "gstr-1": "GSTR1",
            "gstr3b": "GSTR3B",
            "gstr-3b": "GSTR3B",
            "gstr7": "GSTR7",
            "gstr-7": "GSTR7",
            "gstr-others": "GSTR-Others",
            "gstrothers": "GSTR-Others",
            "others": "GSTR-Others",
        }
        key = rt.lower().replace(" ", "")
        normalized = aliases.get(key, rt)
        if normalized not in GST_RETURN_TYPES:
            raise ValueError("Select a valid GST return type.")
        return normalized

    @staticmethod
    def _customer_pan(customer: dict) -> str:
        pan = customer.get("PANNumber") or customer.get("pan_number") or ""
        return str(pan).strip().upper()

    def _is_dsc_application_stage(self, stage_code: str) -> bool:
        code = (stage_code or "").strip().lower()
        return code in DSC_APPLICATION_STAGE_CODES or code.startswith("application")

    def _dsc_saved_application_number(self, row) -> str | None:
        if row is None:
            return None
        self.followup_repo.ensure_application_number_column()
        cols = self.followup_repo.entry_master_columns()
        if "ApplicationNumber" in cols:
            value = getattr(row, "ApplicationNumber", None)
            if value and str(value).strip():
                return str(value).strip()
        if row.BillNo:
            stage_codes = {
                es.stage.StageCode
                for es in (row.stages or [])
                if es.stage and es.stage.StageCode
            }
            if "tally_bill_generated" not in stage_codes and "payment_received" not in stage_codes:
                return str(row.BillNo).strip()
        return None

    def _assert_itr_entry_not_duplicate(
        self,
        *,
        tax_period: str,
        return_type: str | None,
        customer: dict,
        customer_id: int,
        entry_id: int | None = None,
    ) -> None:
        if self.module_code != "ITR":
            return
        pan = self._customer_pan(customer)
        normalized_return = self._normalize_itr_return_type(return_type)
        existing = None
        if pan:
            existing = self.followup_repo.find_active_entry_by_return_key(
                module_code=self.module_code,
                tax_period=tax_period,
                return_type=normalized_return,
                pan_number=pan,
                exclude_entry_id=entry_id,
            )
        if existing is None:
            existing = self.followup_repo.find_active_entry_by_customer_return_key(
                module_code=self.module_code,
                tax_period=tax_period,
                return_type=normalized_return,
                customer_id=customer_id,
                exclude_entry_id=entry_id,
            )
        if existing:
            identity = pan or (customer.get("CustomerName") or f"customer #{customer_id}")
            raise ValueError(
                f"Duplicate entry: {normalized_return} already exists for {identity} "
                f"and period {tax_period}."
            )

    def save_entry(self, payload: dict, *, created_by: str | None = None) -> dict:
        work_date = self._parse_work_date(payload)
        tax_period = (payload.get("tax_period") or payload.get("TaxPeriod") or default_tax_period()).strip()
        if not tax_period:
            raise ValueError("Tax period is required.")

        form_type = None
        quarter = None
        if self.meta.get("has_tds_period_split"):
            self.followup_repo.ensure_tds_period_columns()
            form_type = (payload.get("form_type") or payload.get("FormType") or "").strip()
            quarter = (payload.get("quarter") or payload.get("Quarter") or "").strip().upper()
            if not form_type:
                raise ValueError("Return type is required.")
            if form_type not in TDS_FORM_TYPES:
                raise ValueError("Select a valid return type (Original or Revised).")
            if not quarter:
                raise ValueError("Quarter is required.")
            if quarter not in TDS_QUARTERS:
                raise ValueError("Select a valid quarter (Q1–Q4).")

        customer_id_raw = payload.get("customer_id") or payload.get("CustomerID")
        try:
            customer_id = int(customer_id_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Customer is required.") from exc

        customer = self.customer_repo.get_detail(customer_id)
        return_type = None
        if self.meta["has_return_type"]:
            return_type = self._normalize_itr_return_type(
                payload.get("return_type") or payload.get("ReturnType") or "Original"
            )
        elif self.meta.get("has_gst_fields"):
            self.customer_repo.ensure_schema()
            return_type = self._normalize_gst_return_type(
                payload.get("return_type") or payload.get("ReturnType")
            )

        remarks = (payload.get("remarks") or payload.get("Remarks") or "").strip() or None
        reason = (payload.get("reason_for_unverified") or payload.get("ReasonForUnverified") or "").strip() or None
        application_no = (
            payload.get("application_number")
            or payload.get("ApplicationNumber")
            or payload.get("bill_no")
            or payload.get("BillNo")
            or ""
        ).strip() or None
        stage_ids = self._parse_stage_ids(payload)
        stage_codes = self._stage_codes_from_ids(stage_ids)

        # ITR: if payment lines are submitted, always keep payment_received in stages
        # even when earlier steps (e.g. Documents Received) were skipped.
        if self.module_code == "ITR":
            payment_lines_raw = payload.get("payment_lines")
            has_payment_lines = isinstance(payment_lines_raw, list) and len(payment_lines_raw) > 0
            if has_payment_lines and "payment_received" not in stage_codes:
                payment_stage = self.followup_repo.get_stage_by_code("ITR", "payment_received")
                if payment_stage is not None and payment_stage.ActiveStatus:
                    stage_ids = list(stage_ids) + [payment_stage.StageID]
                    stage_codes = self._stage_codes_from_ids(stage_ids)

        entry_id_raw = payload.get("entry_id") or payload.get("EntryID")
        entry_id = None
        existing_bill_no = None
        existing_row = None
        if entry_id_raw not in (None, "", "0"):
            try:
                entry_id = int(entry_id_raw)
            except (TypeError, ValueError):
                entry_id = None
        if entry_id:
            existing_row = self.followup_repo.get_entry(entry_id)
            if existing_row:
                existing_bill_no = existing_row.BillNo

        if self.module_code == "DSC":
            self.followup_repo.ensure_dsc_extra_columns()
            has_application_stage = any(self._is_dsc_application_stage(code) for code in stage_codes)
            has_documents_received = "documents_received" in stage_codes
            saved_application = self._dsc_saved_application_number(existing_row)
            if saved_application:
                if application_no and application_no != saved_application:
                    raise ValueError("Application number cannot be changed once saved.")
                application_no = saved_application
            elif has_application_stage and not has_documents_received and not application_no:
                raise ValueError("Application number is required when Application No. is checked.")

            location = (payload.get("location") or payload.get("Location") or "").strip()
            introduced_by = (
                payload.get("introduced_by") or payload.get("IntroducedBy") or ""
            ).strip()
            if not location:
                raise ValueError("Location is required.")
            if not introduced_by:
                raise ValueError("Introduced by is required.")
            email_id = (payload.get("email_id") or payload.get("EmailID") or "").strip()
        else:
            location = None
            introduced_by = None
            email_id = None

        needs_billing = (
            self.module_code == "ITR"
            and (
                "tally_bill_generated" in stage_codes
                or "payment_received" in stage_codes
                or "itr_filed" in stage_codes
            )
        ) or (
            self.module_code == "DSC"
            and ("tally_bill_generated" in stage_codes or "payment_received" in stage_codes)
        )
        if needs_billing:
            self.followup_repo.ensure_billing_columns()

        bill_no = (payload.get("bill_no") or payload.get("BillNo") or existing_bill_no or "").strip() or None
        if "tally_bill_generated" in stage_codes or "payment_received" in stage_codes:
            bill_amount = self._parse_bill_amount(payload)
        else:
            bill_amount = None

        if self.module_code == "DSC" and "tally_bill_generated" in stage_codes:
            if not bill_no:
                raise ValueError("Tally bill number is required when Tally Bill Generated is checked.")
            if bill_amount is None or float(bill_amount) <= 0:
                raise ValueError("Bill amount is required when Tally Bill Generated is checked.")

        if self.module_code == "ITR" and "payment_received" in stage_codes:
            if bill_amount is None or float(bill_amount) <= 0:
                payment_service = FollowupPaymentService(self.module_code)
                try:
                    preview_lines = payment_service.parse_payment_lines(payload, Decimal("0"))
                    derived = sum((line["amount"] for line in preview_lines), Decimal("0"))
                    if derived > 0:
                        bill_amount = float(derived)
                except ValueError:
                    pass

        bill_date = self._parse_optional_date(payload, "bill_date", "BillDate")
        itr_filed_date = self._parse_optional_date(payload, "itr_filed_date", "ITRFiledDate")

        self._assert_itr_entry_not_duplicate(
            tax_period=tax_period,
            return_type=return_type,
            customer=customer,
            customer_id=customer_id,
            entry_id=entry_id,
        )

        customer_pan = self._customer_pan(customer) or None
        data = {
            "ModuleCode": self.module_code,
            "WorkDate": work_date,
            "TaxPeriod": tax_period,
            "CustomerID": customer_id,
            "ReturnType": return_type,
            "PANNumber": customer_pan,
            "Remarks": remarks,
            "ReasonForUnverified": reason,
            "ModifiedDate": datetime.utcnow(),
        }
        if self.meta.get("has_tds_period_split"):
            data["FormType"] = form_type
            data["Quarter"] = quarter
        if self.module_code == "DSC":
            data["ApplicationNumber"] = application_no
            data["Location"] = location
            data["IntroducedBy"] = introduced_by

        if "itr_filed" in stage_codes:
            if not itr_filed_date:
                itr_filed_date = date.today()
            data["ITRFiledDate"] = itr_filed_date
        else:
            data["ITRFiledDate"] = None

        if "tally_bill_generated" in stage_codes:
            data["BillNo"] = bill_no
            data["BillAmount"] = bill_amount
            data["BillDate"] = bill_date or date.today()
        elif "payment_received" in stage_codes:
            data["BillNo"] = bill_no
            data["BillAmount"] = bill_amount
            if bill_date:
                data["BillDate"] = bill_date
        elif self.module_code == "DSC":
            data["BillNo"] = None
            data["BillAmount"] = None
            data["BillDate"] = None
        else:
            data["BillNo"] = None
            data["BillAmount"] = None
            data["BillDate"] = None

        def _write() -> dict:
            if self.module_code == "DSC":
                self.customer_repo.update_email(customer_id, email_id)
            if entry_id:
                row = self.followup_repo.get_entry(entry_id)
                if row is None or not row.IsActive or row.ModuleCode != self.module_code:
                    raise ValueError("Followup entry not found.")
                self.followup_repo.update_entry(row, data)
                self.followup_repo.replace_entry_stages(entry_id, stage_ids)
                saved_id = entry_id
            else:
                data["CreatedBy"] = created_by
                data["CreatedDate"] = datetime.utcnow()
                data["IsActive"] = True
                row = self.followup_repo.create_entry(data)
                self.followup_repo.replace_entry_stages(row.EntryID, stage_ids)
                saved_id = row.EntryID

            final_bill_no = data.get("BillNo")
            payment_service = FollowupPaymentService(self.module_code)
            if "payment_received" in stage_codes:
                if not final_bill_no:
                    raise ValueError("Tally bill number is required before marking Payment Received.")
                amount_value = data.get("BillAmount")
                if amount_value is None or float(amount_value) <= 0:
                    raise ValueError("Bill amount is required for Payment Received.")
                payment_lines = payment_service.parse_payment_lines(payload, Decimal(str(amount_value)))
                if not payment_lines:
                    raise ValueError("Add at least one payment mode with amount.")
                if self.module_code in ("ITR", "DSC", "GST", "TDS"):
                    for line in payment_lines:
                        if not line.get("payment_date"):
                            raise ValueError("Each payment line must have a date.")
                existing_daily = payment_service.find_daily_for_bill(final_bill_no)
                daily_work_date = work_date if self.module_code == "ITR" else (bill_date or work_date)
                payment_service.post_payment(
                    bill_no=final_bill_no,
                    work_date=daily_work_date,
                    entry_amount=Decimal(str(amount_value)),
                    payment_lines=payment_lines,
                    customer_name=customer.get("CustomerName"),
                    customer_id=customer_id,
                    remarks=remarks,
                    created_by=created_by or "System",
                    existing_daily=existing_daily,
                )
            elif final_bill_no:
                payment_service.remove_linked_transactions(final_bill_no)

            return self.get_entry(saved_id)

        return persist(_write)

    def delete_entry(self, entry_id: int) -> str:
        def _write() -> str:
            row = self.followup_repo.get_entry(entry_id)
            if row is None or not row.IsActive or row.ModuleCode != self.module_code:
                raise ValueError("Followup entry not found.")
            if row.BillNo:
                FollowupPaymentService(self.module_code).remove_linked_transactions(row.BillNo)
            self.followup_repo.deactivate_entry(row)
            return "Followup entry deleted successfully."

        return persist(_write)

    # ---- Workflow stage master (Masters menu) ----

    def list_master_stages(self, *, search: str | None = None) -> list[dict]:
        rows = self.list_stages(active_only=False)
        if search:
            needle = search.strip().lower()
            rows = [
                row
                for row in rows
                if needle in (row["stage_name"] or "").lower()
                or needle in (row["stage_code"] or "").lower()
            ]
        return rows

    def get_master_stage(self, stage_id: int) -> dict:
        row = self.followup_repo.get_stage(stage_id)
        if row is None or row.ModuleCode != self.module_code:
            raise ValueError("Workflow stage not found.")
        return self._stage_dict(row)

    def create_master_stage(self, payload: dict) -> dict:
        stage_name = (payload.get("stage_name") or payload.get("StageName") or "").strip()
        stage_code = (payload.get("stage_code") or payload.get("StageCode") or "").strip().lower().replace(" ", "_")
        if not stage_name:
            raise ValueError("Stage name is required.")
        if not stage_code:
            stage_code = stage_name.lower().replace(" ", "_")
        try:
            display_order = int(payload.get("display_order") or payload.get("DisplayOrder") or 1)
        except (TypeError, ValueError):
            display_order = 1
        if self.followup_repo.get_stage_by_code(self.module_code, stage_code):
            raise ValueError(f"Stage code '{stage_code}' already exists.")

        def _write() -> dict:
            row = self.followup_repo.create_stage(
                {
                    "ModuleCode": self.module_code,
                    "StageCode": stage_code,
                    "StageName": stage_name,
                    "DisplayOrder": display_order,
                    "ActiveStatus": True,
                    "CreatedDate": datetime.utcnow(),
                }
            )
            return self._stage_dict(row)

        return persist(_write)

    def update_master_stage(self, stage_id: int, payload: dict) -> dict:
        row = self.followup_repo.get_stage(stage_id)
        if row is None or row.ModuleCode != self.module_code:
            raise ValueError("Workflow stage not found.")

        stage_name = (payload.get("stage_name") or payload.get("StageName") or row.StageName).strip()
        if not stage_name:
            raise ValueError("Stage name is required.")
        try:
            display_order = int(payload.get("display_order") or payload.get("DisplayOrder") or row.DisplayOrder)
        except (TypeError, ValueError):
            display_order = row.DisplayOrder

        active_status = row.ActiveStatus
        if "active_status" in payload or "ActiveStatus" in payload:
            raw = payload.get("active_status", payload.get("ActiveStatus"))
            if isinstance(raw, bool):
                active_status = raw
            else:
                active_status = str(raw).lower() in {"1", "true", "yes", "on", "active"}

        def _write() -> dict:
            updated = self.followup_repo.update_stage(
                row,
                {
                    "StageName": stage_name,
                    "DisplayOrder": display_order,
                    "ActiveStatus": active_status,
                },
            )
            return self._stage_dict(updated)

        return persist(_write)

    def delete_master_stage(self, stage_id: int) -> str:
        def _write() -> str:
            row = self.followup_repo.get_stage(stage_id)
            if row is None or row.ModuleCode != self.module_code:
                raise ValueError("Workflow stage not found.")
            if not row.ActiveStatus:
                raise ValueError("Workflow stage is already inactive.")
            self.followup_repo.deactivate_stage(row)
            return "Workflow stage marked inactive successfully."

        return persist(_write)
