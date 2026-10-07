from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.repositories.customer_repository import CustomerRepository
from app.repositories.followup_repository import FollowupRepository
from app.services.followup_billing_service import FollowupBillingService
from app.services.followup_payment_service import FollowupPaymentService
from app.utils.db_session import persist
from app.utils.master_delete_guard import assert_master_unused


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
DSC_TYPES = ("Ind.", "Org.")
DSC_CLASSES = ("Class-II", "Class-III")
DSC_YEARS = ("1-Year", "2-Years", "3-Years")

# ITR, GST and TDS share one manual flow. DSC keeps its own stages.
TAX_FOLLOWUP_MODULES = frozenset({"ITR", "GST", "TDS"})
TAX_WORKFLOW_STAGES = (
    ("documents_received", "Documents Received", 1),
    ("return_filed", "Return Filed", 2),
    ("invoice", "Invoice", 3),
)

# Pasted from Followup Master. Followup screens use these names, not the master screen.
FIXED_WORKFLOW_STAGES = {
    "ITR": TAX_WORKFLOW_STAGES,
    "GST": TAX_WORKFLOW_STAGES,
    "TDS": TAX_WORKFLOW_STAGES,
    "DSC": (
        ("documents_received", "Documents Received", 1),
        ("application_received", "Application Received", 2),
        ("kyc", "KYC", 3),
        ("download_status", "Download Status", 4),
        ("tally_bill_generated", "Tally Bill Generated", 5),
        ("invoice", "Invoice", 6),
    ),
}

# Saved on the entry itself. These modules do not use a stage-code master.
MANUAL_STAGE_MODULES = ("ITR", "GST", "TDS", "DSC")


def stage_description(code: str | None) -> str:
    """Manual stage name stored on the entry. The stage master is not used."""
    key = (code or "").strip().lower().replace(" ", "_")
    aliases = {
        "gstr1_filed": "return_filed",
        "gstr3b_filed": "return_filed",
        "itr_filed": "return_filed",
        "application_no": "application_received",
    }
    key = aliases.get(key, key)
    for stages in FIXED_WORKFLOW_STAGES.values():
        for stage_code, name, _order in stages:
            if stage_code == key:
                return name
    text = (code or "").strip()
    return text


def canonical_stage_code(value: str | None) -> str:
    """Accept a stored description or an older stage code and return the code."""
    text = (value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    compact = lowered.replace(" ", "_")
    aliases = {
        "gstr1_filed": "return_filed",
        "gstr3b_filed": "return_filed",
        "gstr-1_filed": "return_filed",
        "itr_filed": "return_filed",
        "application_no": "application_received",
    }
    compact = aliases.get(compact, compact)
    for stages in FIXED_WORKFLOW_STAGES.values():
        for stage_code, name, _order in stages:
            if compact == stage_code or lowered == name.lower():
                return stage_code
    return compact

TDS_FORM_TYPES = ("Original", "Revised")
TDS_QUARTERS = ("Q1", "Q2", "Q3", "Q4")
GST_RETURN_TYPES = ("GSTR1", "GSTR3B", "GSTR7", "GSTR-Others")
GST_FILING_FREQUENCIES = ("Monthly", "Quarterly", "Yearly")
GST_MONTHS = (
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
    "January",
    "February",
    "March",
)


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


def default_gst_month(today: date | None = None) -> str:
    today = today or date.today()
    return GST_MONTHS[(today.month - 4) % 12]


def _iso_date(value) -> str | None:
    if not value:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    text = str(value).strip()
    return text[:10] if text else None


def _lookup_tally_bill_followup(key: str) -> dict | None:
    repo = FollowupRepository()
    try:
        repo.ensure_billing_columns()
    except Exception:
        repo.session.rollback()
    row = repo.find_by_tally_bill_no(key)
    if not row:
        return None
    module = (row.get("ModuleCode") or "").strip().upper()
    meta = MODULE_META.get(module) or {}
    title = (meta.get("title") or module or "Followup").strip()
    tax_period = (row.get("TaxPeriod") or "").strip()
    return_type = (row.get("ReturnType") or "").strip()
    parts = [f"{title} Followup"]
    if tax_period:
        parts.append(tax_period)
    particulars = " — ".join(parts)
    if return_type:
        particulars = f"{particulars} ({return_type})"
    bill_date = row.get("BillDate") or row.get("WorkDate")
    amount = row.get("BillAmount")
    return {
        "entry_id": row.get("EntryID"),
        "module_code": module,
        "module_title": title,
        "source": "followup",
        "customer_id": row.get("CustomerID"),
        "customer_name": (row.get("CustomerName") or "").strip(),
        "mobile_number": (row.get("MobileNumber") or "").strip(),
        "bill_no": (row.get("BillNo") or "").strip(),
        "invoice_date": _iso_date(bill_date),
        "bill_amount": float(amount) if amount is not None else None,
        "tax_period": tax_period,
        "quarter": (row.get("Quarter") or "").strip(),
        "return_type": return_type,
        "particulars": particulars,
        "invoice_kind": "GST" if module == "GST" else "NON_GST",
    }


def _lookup_tally_bill_income_expense(key: str) -> dict | None:
    """Resolve from Others Income / Expense (Misc. BillNo or TallyBillNo)."""
    from app.repositories.others_repository import OthersIncomeExpenseRepository

    repo = OthersIncomeExpenseRepository()
    try:
        repo.ensure_schema()
    except Exception:
        repo.session.rollback()
    row = repo.find_by_tally_bill_no(key)
    if row is None or not row.IsActive:
        return None

    work = row.work_type
    ledger_kind = (work.LedgerKind if work else "") or ""
    details = list(getattr(row, "detail_lines", None) or [])
    work_labels: list[str] = []
    for detail in sorted(details, key=lambda item: item.LineSequence or 0):
        parent = detail.work_type.WorkName if detail.work_type else ""
        sub = detail.sub_work_type.SubWorkType if detail.sub_work_type else ""
        if parent and sub:
            work_labels.append(f"{parent} / {sub}")
        elif parent:
            work_labels.append(parent)
        elif sub:
            work_labels.append(sub)
    if not work_labels and work:
        work_labels.append(work.WorkName or "")

    label = ", ".join(x for x in work_labels if x) or "Others / Misc"
    title = "Income / Expense (Misc.)" if ledger_kind == "Misc." else "Income / Expense"
    bill_date = getattr(row, "TallyBillDate", None) or row.WorkDate
    amount = getattr(row, "TallyBillAmount", None)
    if amount is None:
        amount = row.Amount
    from app.utils.tally_bill import normalize_tally_bill_key

    tally_no = normalize_tally_bill_key(
        (getattr(row, "TallyBillNo", None) or "").strip() or (row.BillNo or "").strip()
    )
    return {
        "entry_id": row.EntryID,
        "module_code": "OIE",
        "module_title": title,
        "source": "income_expense",
        "ledger_kind": ledger_kind,
        "customer_id": getattr(row, "CustomerID", None),
        "customer_name": (row.CustomerName or "").strip(),
        "mobile_number": (row.MobileNumber or "").strip(),
        "bill_no": tally_no,
        "invoice_date": _iso_date(bill_date),
        "bill_amount": float(amount) if amount is not None else None,
        "tax_period": "",
        "quarter": "",
        "return_type": "",
        "particulars": f"Others / Misc — {label}"[:300],
        "invoice_kind": "NON_GST",
    }


def _canonical_stage_ids(completed: list | None, row) -> list[str]:
    """Checkbox codes. Stored names such as Documents Received map back to the tick."""
    codes: list[str] = []
    seen: set[str] = set()
    for item in completed or []:
        raw = item.get("StageCode") or item.get("StageID") or item.get("StageName")
        code = canonical_stage_code(raw)
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    if codes:
        return codes
    for stage in getattr(row, "stages", None) or []:
        code = canonical_stage_code(getattr(stage, "StageCode", None))
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def lookup_tally_bill(bill_no: str) -> dict | None:
    """Resolve Tally Bill from Followup or Income / Expense (Misc.)."""
    key = (bill_no or "").strip()
    if not key:
        return None
    return _lookup_tally_bill_followup(key) or _lookup_tally_bill_income_expense(key)


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
        dsc_type = getattr(row, "DscType", None) if "DscType" in available_cols else None
        dsc_class = getattr(row, "DscClass", None) if "DscClass" in available_cols else None
        dsc_year = getattr(row, "DscYear", None) if "DscYear" in available_cols else None
        form_type = None
        if "FormType" in available_cols:
            form_type = getattr(row, "FormType", None)
        quarter = None
        if "Quarter" in available_cols:
            quarter = getattr(row, "Quarter", None)
        gst_month = getattr(row, "GstMonth", None) if "GstMonth" in available_cols else None
        billing_type = getattr(row, "BillingType", None) if "BillingType" in available_cols else None
        billing_customer_id = (
            getattr(row, "BillingCustomerID", None) if "BillingCustomerID" in available_cols else None
        )
        return {
            "entry_id": row.EntryID,
            "module_code": row.ModuleCode,
            "work_date": row.WorkDate.isoformat() if row.WorkDate else None,
            "tax_period": row.TaxPeriod,
            "gst_month": gst_month,
            "customer_id": row.CustomerID,
            "billing_type": (billing_type or ""),
            "billing_customer_id": int(billing_customer_id) if billing_customer_id else None,
            "billing_customer_name": "",
            "return_type": row.ReturnType,
            "form_type": form_type,
            "quarter": quarter,
            "application_number": application_number,
            "location": location,
            "introduced_by": introduced_by,
            "dsc_type": dsc_type,
            "dsc_class": dsc_class,
            "dsc_year": dsc_year,
            "bill_no": row.BillNo,
            "bill_date": row.BillDate.isoformat() if row.BillDate else None,
            "bill_amount": bill_amount,
            "itr_filed_date": itr_filed_date,
            "return_filing_status": return_filing_status,
            "filing_date": filing_date,
            "pan_number": row.PANNumber,
            "remarks": row.Remarks,
            "reason_for_unverified": row.ReasonForUnverified,
            "stage_ids": _canonical_stage_ids(completed, row),
            "completed_stages": completed,
            "workflow_status": FollowupRepository._workflow_status(
                completed,
                [],
            ),
        }

    def list_stages(self, *, active_only: bool = True) -> list[dict]:
        """Fixed stage list. Names are not read from Followup Master."""
        fixed = FIXED_WORKFLOW_STAGES.get(self.module_code) or ()
        return [
            {
                "stage_id": code,
                "stage_code": code,
                "stage_name": name,
                "display_order": order,
                "active_status": True,
            }
            for code, name, order in fixed
        ]

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
        self.followup_repo.ensure_gst_month_column()
        if self.module_code == "ITR":
            self.followup_repo.ensure_filing_status_columns()
        if self.module_code == "TDS":
            self.followup_repo.ensure_tds_period_columns()
        if self.module_code == "DSC":
            from app.repositories.customer_repository import CustomerRepository

            CustomerRepository().ensure_schema()
            self.followup_repo.ensure_dsc_extra_columns()
        # Progressive exclusive-bucket status filter for every follow-up module.
        repo_status = None if self.module_code in TAX_FOLLOWUP_MODULES or self.module_code == "DSC" else status_filter
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
            row["customer_id"] = row.get("CustomerID")
            row["billing_type"] = (row.get("BillingType") or "")
            raw_billing = row.get("BillingCustomerID")
            try:
                row["billing_customer_id"] = int(raw_billing) if raw_billing else None
            except (TypeError, ValueError):
                row["billing_customer_id"] = None
            row["billing_customer_name"] = ""
            row["customer_name"] = row.get("CustomerName") or ""
            row["mobile_number"] = row.get("MobileNumber") or ""
            row["email_id"] = row.get("EmailID") or row.get("email_id") or ""
            row["pan_number"] = row.get("PANNumber") or row.get("pan_number") or ""
            row["aadhaar_number"] = row.get("AadhaarNumber") or row.get("aadhaar_number") or ""
            row["employee_code"] = row.get("EmployeeCode") or ""
            dob = row.get("DateOfBirth")
            if dob is not None and hasattr(dob, "isoformat"):
                row["date_of_birth"] = dob.isoformat()
            else:
                row["date_of_birth"] = str(dob)[:10] if dob else ""
            row["return_type"] = row.get("ReturnType")
            row["application_number"] = row.get("ApplicationNumber")
            row["location"] = row.get("Location")
            row["introduced_by"] = row.get("IntroducedBy")
            row["dsc_type"] = row.get("DscType") or ""
            row["dsc_class"] = row.get("DscClass") or ""
            row["dsc_year"] = row.get("DscYear") or ""
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
            row["gst_month"] = row.get("GstMonth") or ""
            row["form_type"] = row.get("FormType")
            row["quarter"] = row.get("Quarter")
            row["filing_frequency"] = row.get("FilingFrequency") or row.get("filing_frequency") or ""
            row["stage_ids"] = [
                s.get("StageCode") or s.get("StageID") for s in row.get("completed_stages", [])
            ]
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
        if status_filter and (self.module_code in TAX_FOLLOWUP_MODULES or self.module_code == "DSC"):
            rows = self._filter_entries_by_status(rows, status_filter, module_code=self.module_code)
        from app.services.gst_invoice_service import GstInvoiceService

        status_map = GstInvoiceService().sale_status_by_bill_nos(
            [(row.get("bill_no") or row.get("BillNo") or "") for row in rows]
        )
        for row in rows:
            key = (row.get("bill_no") or row.get("BillNo") or "").strip().upper()
            row["sale_invoice"] = status_map.get(key)
        self._attach_linked_invoices(rows)
        return rows

    @staticmethod
    def _invoice_link_dict(inv) -> dict:
        from app.services.gst_invoice_service import GstInvoiceService

        return GstInvoiceService().invoice_action_snapshot(inv)

    def _fill_billing_customer_name(self, row: dict) -> None:
        if row.get("billing_type") != "OTHER_CUSTOMER":
            return
        if (row.get("billing_customer_name") or "").strip():
            return
        try:
            billing_id = int(row.get("billing_customer_id") or 0)
        except (TypeError, ValueError):
            return
        if billing_id <= 0:
            return
        billing_customer = self.customer_repo.get_by_id(billing_id)
        row["billing_customer_name"] = (
            billing_customer.CustomerName if billing_customer is not None else ""
        )

    def _resolve_billing_customer(
        self,
        payload: dict,
        *,
        followup_customer_id: int,
        invoice_checked: bool,
    ) -> tuple[str, int]:
        """Billing customer is the invoice customer. Follow-up customer stays unchanged."""
        if not invoice_checked:
            return "", int(followup_customer_id)
        raw_type = (payload.get("billing_type") or payload.get("BillingType") or "")
        billing_type = str(raw_type).strip().upper()
        if billing_type not in {"SAME_CUSTOMER", "OTHER_CUSTOMER"}:
            raise ValueError("Please select Same Customer or Other Customer.")
        if billing_type == "SAME_CUSTOMER":
            return "SAME_CUSTOMER", int(followup_customer_id)
        raw_id = payload.get("billing_customer_id")
        if raw_id in (None, ""):
            raw_id = payload.get("BillingCustomerID")
        try:
            billing_id = int(raw_id)
        except (TypeError, ValueError):
            billing_id = 0
        if billing_id <= 0 or self.customer_repo.get_by_id(billing_id) is None:
            raise ValueError("Please select the Billing Customer.")
        return "OTHER_CUSTOMER", billing_id

    def _strip_unlinked_invoice_stage(self, row: dict) -> None:
        """Invoice is complete only when a real invoice is linked to this entry."""
        completed = [
            stage
            for stage in (row.get("completed_stages") or [])
            if canonical_stage_code(stage.get("StageCode") or stage.get("stage_code") or "") != "invoice"
        ]
        row["completed_stages"] = completed
        row["stage_ids"] = [
            code
            for code in (row.get("stage_ids") or [])
            if canonical_stage_code(str(code)) != "invoice"
        ]
        row["workflow_status"] = FollowupRepository._workflow_status(completed, [])

    def _attach_linked_invoices(self, rows: list[dict]) -> None:
        """Invoice No / Date / Amount come from the saved invoice, not the follow-up form."""
        for row in rows:
            row["linked_invoice"] = None
        if self.module_code not in TAX_FOLLOWUP_MODULES and self.module_code != "DSC":
            return
        if not rows:
            return
        from app.repositories.gst_invoice_repository import GstInvoiceRepository

        repo = GstInvoiceRepository()
        ids = []
        for row in rows:
            try:
                ids.append(int(row.get("entry_id") or 0))
            except (TypeError, ValueError):
                continue
        by_entry = repo.find_by_followup_entries(ids)
        for row in rows:
            try:
                entry_id = int(row.get("entry_id") or 0)
            except (TypeError, ValueError):
                entry_id = 0
            inv = by_entry.get(entry_id) if entry_id else None
            if inv is None:
                bill = (row.get("bill_no") or row.get("BillNo") or "").strip()
                matches = repo.list_ids_for_bill_no(bill) if bill else []
                if len(matches) == 1:
                    inv = repo.get_by_id(matches[0])
                    other_entry = getattr(inv, "FollowupEntryID", None) if inv is not None else None
                    if inv is not None and other_entry not in (None, entry_id):
                        inv = None
            if inv is None:
                self._strip_unlinked_invoice_stage(row)
                self._fill_billing_customer_name(row)
                continue
            row["linked_invoice"] = self._invoice_link_dict(inv)
            followup_customer = int(row.get("customer_id") or 0)
            invoice_customer = int(getattr(inv, "CustomerID", None) or 0)
            if invoice_customer and followup_customer and invoice_customer != followup_customer:
                row["billing_type"] = "OTHER_CUSTOMER"
                row["billing_customer_id"] = invoice_customer
                row["billing_customer_name"] = inv.CustomerName or ""
            elif followup_customer:
                row["billing_type"] = "SAME_CUSTOMER"
                row["billing_customer_id"] = followup_customer
            self._fill_billing_customer_name(row)

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
        """Tax follow-up card bucket: furthest progress tick, exclusive of later stages.

        Documents Received → Return Filed → Invoice.
        Older Payment Received ticks stay on the Invoice bucket. They are not a stage.
        """
        codes = cls._completed_stage_codes(row)
        status = (row.get("workflow_status") or "").strip()
        if (
            "invoice" in codes
            or "tally_bill_generated" in codes
            or "payment_received" in codes
            or row.get("payment_received")
            or status in {"Invoice", "Tally Bill Generated", "Payment Received"}
        ):
            return "invoice"
        if (
            "return_filed" in codes
            or "itr_filed" in codes
            or status in {"Return Filed", "ITR Filed"}
        ):
            return "return_filed"
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
        TALLY BILL GENERATED → bill ticked. Older Payment Received ticks stay on that bucket.
        """
        codes = cls._completed_stage_codes(row)
        status = (row.get("workflow_status") or "").strip()
        status_l = status.lower()
        if status == "Unverified" or "unverified" in codes:
            return "unverified"
        if "invoice" in codes or status == "Invoice":
            return "invoice"
        if (
            "tally_bill_generated" in codes
            or "payment_received" in codes
            or row.get("payment_received")
            or status in {"Tally Bill Generated", "Payment Received"}
        ):
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
        # Payment pending = Invoice stage without Payment Received.
        # DSC still uses Tally Bill Generated for that bucket.
        if sf == "payment_pending":
            pending_code = "tally_bill_generated" if module_code == "DSC" else "invoice"
            return [
                r
                for r in rows
                if cls._progress_bucket(r, module_code) == pending_code
            ]
        if module_code != "DSC" and sf == "itr_filed":
            sf = "return_filed"
        if module_code != "DSC" and sf == "tally_bill_generated":
            sf = "invoice"
        itr_codes = {
            "pending",
            "documents_received",
            "return_filed",
            "invoice",
        }
        dsc_codes = {
            "pending",
            "documents_received",
            "application_received",
            "application_no",
            "kyc",
            "download_status",
            "tally_bill_generated",
            "invoice",
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
        """Historical receipts stay in accounting. They no longer create a follow-up stage."""
        return
        if not rows:
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
                    "StageID": "payment_received",
                    "StageCode": "payment_received",
                    "StageName": "Payment Received",
                    "DisplayOrder": 4,
                }
            )
            row["completed_stages"] = completed
            row["stage_ids"] = [s.get("StageCode") or s.get("StageID") for s in completed]
            row["payment_received"] = True
            row["workflow_status"] = "Payment Received"

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

    @staticmethod
    def _unique_gst_cases(rows: list[dict]) -> list[dict]:
        """One GST case is one customer + month + tax year.

        A blank month is a legacy row and stays its own case.
        Different months for the same customer are never merged.
        """
        unique: list[dict] = []
        seen: set[tuple] = set()
        for row in rows:
            try:
                customer_id = int(row.get("customer_id") or row.get("CustomerID") or 0)
            except (TypeError, ValueError):
                customer_id = 0
            month = (row.get("gst_month") or row.get("GstMonth") or "").strip().lower()
            period = (row.get("tax_period") or row.get("TaxPeriod") or "").strip().lower()
            if month:
                key = (customer_id, month, period)
            else:
                key = ("entry", row.get("entry_id") or row.get("EntryID"), period)
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        return unique

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

        Every module: exclusive bucket of the furthest ticked stage.
        GST counts each customer + month + tax year as its own case.
        """
        rows = self.list_entries(
            search=search,
            tax_period=tax_period,
            return_type=return_type,
            date_from=date_from,
            date_to=date_to,
        )
        if self.module_code == "GST":
            rows = self._unique_gst_cases(rows)
        total = len(rows)

        if self.module_code in TAX_FOLLOWUP_MODULES or self.module_code == "DSC":
            buckets: dict[str, int] = {}
            for row in rows:
                key = self._progress_bucket(row, self.module_code)
                buckets[key] = buckets.get(key, 0) + 1
            pending = buckets.get("pending", 0)
            payment_received = buckets.get("payment_received", 0)
            pending_code = "tally_bill_generated" if self.module_code == "DSC" else "invoice"
            payment_pending = buckets.get(pending_code, 0)
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
        pending_code = "tally_bill_generated" if self.module_code == "DSC" else "invoice"
        payment_pending = sum(
            1
            for r in rows
            if self._progress_bucket(r, self.module_code) == pending_code
        )
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
            "payment_pending": payment_pending,
            "by_status": by_status,
        }

    def customer_bill_summary(self, customer_id: int) -> dict:
        """Saved bills and actual receipts for one customer.

        Overdue is cumulative bill amount minus cumulative payment received.
        A saved invoice amount is used as-is and is never rewritten here.
        """
        from sqlalchemy import select

        from app.extensions import db
        from app.models.followup import FollowupEntryMaster
        from app.models.gst_billing import GstInvoice
        from app.services.gst_invoice_service import GstInvoiceService
        from app.services.payment_accounting_service import PaymentAccountingService

        empty = {
            "invoice_total": 0.0,
            "payment_received_total": 0.0,
            "overdue_amount": 0.0,
            "bill_count": 0,
        }
        try:
            cid = int(customer_id)
        except (TypeError, ValueError):
            return empty
        if cid <= 0:
            return empty

        self.followup_repo.ensure_gst_month_column()

        def money(value) -> Decimal:
            return Decimal(str(value or 0)).quantize(Decimal("0.01"))

        def bill_key(value) -> str:
            return (value or "").strip().upper()

        bills: dict[str, Decimal] = {}
        invoice_alias_keys: set[str] = set()
        invoices = list(
            db.session.scalars(
                select(GstInvoice).where(
                    GstInvoice.CustomerID == cid,
                    GstInvoice.VoucherType == GstInvoiceService.VOUCHER_SALE,
                )
            ).all()
        )
        invoice_keys: list[tuple] = []
        for inv in invoices:
            aliases = {bill_key(inv.InvoiceNo), bill_key(getattr(inv, "TallyBillNo", None))}
            aliases.discard("")
            invoice_alias_keys.update(aliases)
            primary = (
                bill_key(getattr(inv, "TallyBillNo", None))
                or bill_key(inv.InvoiceNo)
                or f"INV:{inv.InvoiceID}"
            )
            if primary not in bills:
                bills[primary] = money(inv.InvoiceValue)
            aliases.add(primary)
            invoice_keys.append((inv, aliases))

        followups = list(
            db.session.scalars(
                select(FollowupEntryMaster).where(
                    FollowupEntryMaster.CustomerID == cid,
                    FollowupEntryMaster.IsActive == True,  # noqa: E712
                    FollowupEntryMaster.BillAmount.isnot(None),
                )
            ).all()
        )
        for row in followups:
            key = bill_key(row.BillNo) or f"ENTRY:{row.EntryID}"
            if key in bills or key in invoice_alias_keys:
                continue
            bills[key] = money(row.BillAmount)

        pay = PaymentAccountingService()
        received = Decimal("0.00")
        seen_receipts: set[int] = set()

        def add_receipts(ref: str) -> bool:
            nonlocal received
            if not ref or ref.startswith("ENTRY:") or ref.startswith("INV:"):
                return False
            found = False
            for daily in pay.find_receipt_dailies(ref):
                other_customer = getattr(daily, "CustomerID", None)
                if other_customer is not None and int(other_customer) != cid:
                    continue
                found = True
                receipt_id = int(daily.TransactionID)
                if receipt_id in seen_receipts:
                    continue
                seen_receipts.add(receipt_id)
                received += pay._received_on_daily(daily)
            return found

        for key in list(bills):
            add_receipts(key)
        for inv, aliases in invoice_keys:
            had_receipt = False
            for alias in aliases:
                if add_receipts(alias):
                    had_receipt = True
            if had_receipt:
                continue
            paid = money(getattr(inv, "AmountPaid", None))
            if paid > 0:
                received += paid

        invoice_ids = [int(inv.InvoiceID) for inv, _aliases in invoice_keys]
        if invoice_ids:
            for allocated in GstInvoiceService().money_in_totals(invoice_ids).values():
                received += money(allocated)

        bill_total = money(sum(bills.values(), Decimal("0.00")))
        received = money(received)
        overdue = money(bill_total - received)
        return {
            "invoice_total": float(bill_total),
            "payment_received_total": float(received),
            "overdue_amount": float(overdue),
            "bill_count": len(bills),
        }

    def get_entry(self, entry_id: int) -> dict:
        self.followup_repo.ensure_gst_month_column()
        if self.module_code == "TDS":
            self.followup_repo.ensure_tds_period_columns()
        if self.module_code == "DSC":
            self.followup_repo.ensure_dsc_extra_columns()
        row = self.followup_repo.get_entry(entry_id)
        if row is None or not row.IsActive or row.ModuleCode != self.module_code:
            raise ValueError("Followup entry not found.")
        customer = self.customer_repo.get_detail(row.CustomerID)
        stage_meta = {
            code: (name, order)
            for code, name, order in FIXED_WORKFLOW_STAGES.get(self.module_code, ())
        }
        completed = []
        for es in row.stages or []:
            code = canonical_stage_code(es.StageCode)
            if not code:
                continue
            name, order = stage_meta.get(code, (code.replace("_", " ").title(), 0))
            completed.append(
                {
                    "StageID": code,
                    "StageCode": code,
                    "StageName": name,
                    "DisplayOrder": order,
                }
            )
        completed.sort(key=lambda item: item["DisplayOrder"])
        all_stages = []
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
            receipt_daily = payment_service.accounting.find_receipt_daily(data["bill_no"])
            sale_daily = payment_service.accounting.find_sale_daily(data["bill_no"])
            daily = receipt_daily or sale_daily
            if daily is not None:
                data["payments"] = (
                    payment_service.load_payment_lines(receipt_daily) if receipt_daily is not None else []
                )
                data["daily_transaction_id"] = daily.TransactionID
                if data["payments"]:
                    received = self.received_amount_for_letter({**data, "payments": data["payments"]})
                else:
                    received = 0.0
                data["received_amount"] = received
        self._attach_linked_invoices([data])
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

    def _parse_stage_ids(self, payload: dict) -> list[str]:
        raw = payload.get("stage_ids") or payload.get("StageIDs")
        if raw is None:
            raw = payload.getlist("stage_ids") if hasattr(payload, "getlist") else []
        if isinstance(raw, str):
            raw = [part.strip() for part in raw.split(",") if part.strip()]
        allowed = {code for code, _name, _order in FIXED_WORKFLOW_STAGES.get(self.module_code, ())}
        codes: list[str] = []
        seen: set[str] = set()
        for item in raw or []:
            code = canonical_stage_code(str(item) if item is not None else "")
            if self.module_code in TAX_FOLLOWUP_MODULES:
                if code == "tally_bill_generated":
                    code = "invoice"
                elif self.module_code == "TDS" and code == "kyc":
                    code = "return_filed"
                elif code == "unverified":
                    continue
            if code in allowed and code not in seen:
                seen.add(code)
                codes.append(code)
        return codes

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

    def _stage_codes_from_ids(self, stage_ids: list[str]) -> set[str]:
        return {str(code).strip().lower() for code in stage_ids if code}

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
                canonical_stage_code(es.StageCode)
                for es in (row.stages or [])
                if es.StageCode
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

    @staticmethod
    def _normalize_gst_month(raw) -> str:
        text = str(raw or "").strip()
        if not text:
            raise ValueError("Month is required.")
        for name in GST_MONTHS:
            if name.lower() == text.lower():
                return name
        raise ValueError("Select a valid month.")

    def _assert_gst_entry_not_duplicate(
        self,
        *,
        tax_period: str,
        gst_month: str,
        customer: dict,
        customer_id: int,
        entry_id: int | None = None,
    ) -> None:
        if self.module_code != "GST":
            return
        existing = self.followup_repo.find_active_gst_month_duplicate(
            customer_id=customer_id,
            tax_period=tax_period,
            gst_month=gst_month,
            exclude_entry_id=entry_id,
        )
        if existing:
            name = (customer.get("CustomerName") or "").strip() or f"customer #{customer_id}"
            raise ValueError(
                f"Duplicate entry: {name} already has a GST follow-up for {gst_month} {tax_period}."
            )

    def save_entry(self, payload: dict, *, created_by: str | None = None) -> dict:
        self.followup_repo.ensure_billing_customer_columns()
        self.followup_repo.ensure_gst_month_column()
        self.followup_repo.ensure_stage_code_unique()
        self.followup_repo.ensure_dsc_extra_columns()
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

        entry_id_raw = payload.get("entry_id") or payload.get("EntryID")
        entry_id = None
        existing_bill_no = None
        existing_bill_amount = None
        existing_bill_date = None
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
                if getattr(existing_row, "BillAmount", None) is not None:
                    existing_bill_amount = float(existing_row.BillAmount)
                existing_bill_date = getattr(existing_row, "BillDate", None)

        gst_month = None
        if self.module_code == "GST":
            gst_month = self._normalize_gst_month(payload.get("gst_month") or payload.get("GstMonth"))
            self._assert_gst_entry_not_duplicate(
                tax_period=tax_period,
                gst_month=gst_month,
                customer=customer,
                customer_id=customer_id,
                entry_id=entry_id,
            )

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
            dsc_type = (payload.get("dsc_type") or payload.get("DscType") or "").strip()
            dsc_class = (payload.get("dsc_class") or payload.get("DscClass") or "").strip()
            dsc_year = (payload.get("dsc_year") or payload.get("DscYear") or "").strip()
            if dsc_type not in DSC_TYPES:
                raise ValueError("DSC type is required (Ind. or Org.).")
            if dsc_class not in DSC_CLASSES:
                raise ValueError("DSC class is required (Class-II or Class-III).")
            if dsc_year not in DSC_YEARS:
                raise ValueError("Year is required (1-Year, 2-Years or 3-Years).")
            if not location:
                raise ValueError("Location is required.")
            if not introduced_by:
                raise ValueError("Introduced by is required.")
            email_id = (payload.get("email_id") or payload.get("EmailID") or "").strip()
        else:
            location = None
            introduced_by = None
            dsc_type = None
            dsc_class = None
            dsc_year = None
            email_id = None

        self.followup_repo.ensure_billing_customer_columns()
        invoice_stage = "invoice" in stage_codes
        if invoice_stage and (self.module_code in TAX_FOLLOWUP_MODULES or self.module_code == "DSC"):
            linked_invoice = None
            if entry_id:
                from app.repositories.gst_invoice_repository import GstInvoiceRepository

                linked_invoice = GstInvoiceRepository().find_by_followup_entry(entry_id)
            if linked_invoice is None:
                raise ValueError(
                    "Invoice cannot be selected manually. "
                    "Please click 'Create Invoice' to generate the invoice first."
                )
        billing_type, billing_customer_id = self._resolve_billing_customer(
            payload,
            followup_customer_id=customer_id,
            invoice_checked="invoice" in stage_codes,
        )
        tax_followup = self.module_code in TAX_FOLLOWUP_MODULES
        if (
            tax_followup
            and entry_id
            and existing_row is not None
            and "invoice" in stage_codes
            and "return_filed" not in stage_codes
        ):
            previous_codes = {
                canonical_stage_code(getattr(stage, "StageCode", None))
                for stage in (existing_row.stages or [])
            }
            if "return_filed" in previous_codes or "itr_filed" in previous_codes:
                raise ValueError(
                    "Please uncheck Invoice first before unchecking Return Filed."
                )
        needs_billing = (
            (not tax_followup and "tally_bill_generated" in stage_codes)
            or "payment_received" in stage_codes
            or "return_filed" in stage_codes
            or "itr_filed" in stage_codes
        )
        if needs_billing:
            self.followup_repo.ensure_billing_columns()

        bill_no = (payload.get("bill_no") or payload.get("BillNo") or existing_bill_no or "").strip() or None
        if tax_followup:
            # Invoice is created manually in the Invoice module. Do not mint a Tally bill here.
            bill_no = existing_bill_no
            if "payment_received" in stage_codes and not bill_no:
                bill_no = FollowupBillingService.next_bill_no(self.module_code, work_date)
        elif "tally_bill_generated" in stage_codes and not bill_no:
            bill_no = FollowupBillingService.next_bill_no(self.module_code, work_date)
        if bill_no and self.module_code != "DSC":
            other = self.followup_repo.find_by_tally_bill_no(bill_no)
            other_id = int(other.get("EntryID") or 0) if other else 0
            if other and other_id and other_id != int(entry_id or 0):
                other_mod = (other.get("ModuleCode") or "").strip().upper() or "Followup"
                other_name = (other.get("CustomerName") or "").strip()
                label = "Bill number" if tax_followup else "Tally Bill Number"
                raise ValueError(
                    f"{label} {bill_no} already used in {other_mod} Followup"
                    + (f" ({other_name})" if other_name else "")
                    + ". Duplicate allow nahi hai."
                )
        raw_amount = payload.get("bill_amount")
        if raw_amount in (None, ""):
            raw_amount = payload.get("BillAmount")
        if raw_amount not in (None, ""):
            bill_amount = self._parse_bill_amount(payload)
        else:
            bill_amount = existing_bill_amount

        if "tally_bill_generated" in stage_codes and not bill_no:
            raise ValueError("Tally bill number is required when Tally Bill Generated is checked.")

        bill_date = self._parse_optional_date(payload, "bill_date", "BillDate") or work_date
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
        if self.module_code == "GST":
            data["GstMonth"] = gst_month
        if "invoice" in stage_codes:
            data["BillingType"] = billing_type
            data["BillingCustomerID"] = billing_customer_id
        if self.module_code == "DSC":
            data["ApplicationNumber"] = application_no
            data["DscType"] = dsc_type
            data["DscClass"] = dsc_class
            data["DscYear"] = dsc_year
            data["Location"] = location
            data["IntroducedBy"] = introduced_by

        if "return_filed" in stage_codes or "itr_filed" in stage_codes:
            if not itr_filed_date:
                itr_filed_date = date.today()
            data["ITRFiledDate"] = itr_filed_date
        else:
            data["ITRFiledDate"] = None

        saved_bill_no = bill_no or existing_bill_no
        saved_bill_date = bill_date or existing_bill_date
        keeps_bill = (not tax_followup and "tally_bill_generated" in stage_codes) or (
            "payment_received" in stage_codes
        )
        if keeps_bill:
            if saved_bill_no:
                data["BillNo"] = saved_bill_no
            if bill_amount is not None:
                data["BillAmount"] = bill_amount
            if saved_bill_date:
                data["BillDate"] = saved_bill_date
            elif not tax_followup and "tally_bill_generated" in stage_codes:
                data["BillDate"] = date.today()

        persist_stage_ids = list(stage_ids)
        if existing_row is not None:
            for link in existing_row.stages or []:
                if canonical_stage_code(link.StageCode) == "payment_received":
                    if "payment_received" not in persist_stage_ids:
                        persist_stage_ids.append("payment_received")
                    break

        def _write() -> dict:
            if self.module_code == "DSC":
                self.customer_repo.update_email(customer_id, email_id)
            if entry_id:
                row = self.followup_repo.get_entry(entry_id)
                if row is None or not row.IsActive or row.ModuleCode != self.module_code:
                    raise ValueError("Followup entry not found.")
                self.followup_repo.update_entry(row, data)
                self.followup_repo.replace_entry_stages(entry_id, persist_stage_ids)
                saved_id = entry_id
            else:
                data["CreatedBy"] = created_by
                data["CreatedDate"] = datetime.utcnow()
                data["IsActive"] = True
                row = self.followup_repo.create_entry(data)
                self.followup_repo.replace_entry_stages(row.EntryID, persist_stage_ids)
                saved_id = row.EntryID

            billing_stage = (not tax_followup and "tally_bill_generated" in stage_codes) or (
                "payment_received" in stage_codes
            )
            final_bill_no = data.get("BillNo") if billing_stage else existing_bill_no
            payment_service = FollowupPaymentService(self.module_code)
            old_bill = (existing_bill_no or "").strip()
            new_bill = (final_bill_no or "").strip() if billing_stage else old_bill
            amount_value = data.get("BillAmount")
            if amount_value is None:
                amount_value = existing_bill_amount
            if billing_stage and old_bill and old_bill.upper() != new_bill.upper():
                payment_service.remove_followup_accounting(old_bill)

            if billing_stage and new_bill:
                payment_service.accounting.reconcile_reference(new_bill)

            if "payment_received" in stage_codes:
                if not new_bill:
                    if tax_followup:
                        raise ValueError("Payment reference is missing. Save Payment Received again.")
                    raise ValueError("Tally bill number is required before marking Payment Received.")
                payment_lines = payment_service.parse_payment_lines(
                    payload, Decimal(str(amount_value or 0))
                )
                if not payment_lines:
                    raise ValueError("Add at least one payment mode with amount.")
                received_total = sum((line["amount"] for line in payment_lines), Decimal("0"))
                if received_total <= 0:
                    raise ValueError("Payment amount must be greater than zero.")
                if amount_value is None or float(amount_value) <= 0:
                    amount_value = float(received_total)
                if self.module_code in ("ITR", "DSC", "GST", "TDS"):
                    for line in payment_lines:
                        if not line.get("payment_date"):
                            raise ValueError("Each payment line must have a date.")
                existing_daily = payment_service.accounting.find_receipt_daily(new_bill)
                daily_work_date = work_date if self.module_code == "ITR" else (bill_date or work_date)
                payment_service.post_payment(
                    bill_no=new_bill,
                    work_date=daily_work_date,
                    entry_amount=Decimal(str(amount_value)),
                    payment_lines=payment_lines,
                    customer_name=customer.get("CustomerName"),
                    customer_id=customer_id,
                    remarks=remarks,
                    created_by=created_by or "System",
                    existing_daily=existing_daily,
                )
            elif billing_stage and new_bill:
                payment_service.remove_receipts(new_bill)
            elif billing_stage and old_bill:
                payment_service.remove_followup_accounting(old_bill)

            from app.services.gst_invoice_service import GstInvoiceService

            if "invoice" in stage_codes and billing_customer_id:
                GstInvoiceService().assign_billing_customer(saved_id, int(billing_customer_id))
            if billing_stage and new_bill and "payment_received" in stage_codes:
                GstInvoiceService().sync_payment_received_for_bill(new_bill, True)
            return self.get_entry(saved_id)

        return persist(_write)

    def delete_entry(self, entry_id: int) -> str:
        row = self.followup_repo.get_entry(entry_id)
        if row is None or not row.IsActive or row.ModuleCode != self.module_code:
            raise ValueError("Followup entry not found.")
        for link in list(row.stages or []):
            code = canonical_stage_code(link.StageCode)
            if code == "payment_received":
                raise ValueError("Remove Payment Received in Edit before deleting this entry.")
        from app.services.gst_invoice_service import GstInvoiceService

        invoices = GstInvoiceService()
        for invoice_id in invoices.repo.list_ids_for_followup_entry(entry_id):
            invoices.delete_record(
                invoice_id,
                payload={"from_source": True, "followup_entry_id": int(entry_id)},
            )

        def _write() -> str:
            current = self.followup_repo.get_entry(entry_id)
            if current is None or not current.IsActive or current.ModuleCode != self.module_code:
                raise ValueError("Followup entry not found.")
            if current.BillNo:
                FollowupPaymentService(self.module_code).remove_followup_accounting(current.BillNo)
            self.followup_repo.deactivate_entry(current)
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
            assert_master_unused(
                table="FollowupWorkflowStage",
                pk_column="StageID",
                pk_value=stage_id,
                display_name=row.StageName or "Workflow stage",
            )
            self.followup_repo.deactivate_stage(row)
            return "Workflow stage marked inactive successfully."

        return persist(_write)

    DSC_ASSIST_KEYS = {
        "idsign_business_id": 80,
        "customer_video_link": 500,
    }

    def get_dsc_assist(self) -> dict[str, str]:
        stored = self.followup_repo.list_dsc_settings()
        return {key: stored.get(key, "") for key in self.DSC_ASSIST_KEYS}

    def save_dsc_assist(self, key: str, value: str, *, modified_by: str) -> dict[str, str]:
        setting_key = (key or "").strip()
        max_len = self.DSC_ASSIST_KEYS.get(setting_key)
        if max_len is None:
            raise ValueError("Unknown DSC setting.")
        cleaned = (value or "").strip()
        if len(cleaned) > max_len:
            raise ValueError(f"Value is too long (max {max_len} characters).")
        if setting_key == "customer_video_link" and cleaned:
            lower = cleaned.lower()
            if not (lower.startswith("http://") or lower.startswith("https://")):
                raise ValueError("Video link must start with http:// or https://")

        def _write() -> dict[str, str]:
            saved = self.followup_repo.upsert_dsc_setting(
                setting_key,
                cleaned,
                modified_by=modified_by,
            )
            values = self.get_dsc_assist()
            values[setting_key] = saved
            return values

        return persist(_write)
