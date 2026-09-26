from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from flask import current_app
from sqlalchemy import func, or_, select, text

from app.extensions import db
from app.models.gst_billing import GstInvoice
from app.models.transactions import JTCSDailyTransaction
from app.repositories.gst_invoice_repository import GstInvoiceRepository
from app.repositories.item_master_repository import ItemMasterRepository
from app.repositories.transaction_repository import (
    BankTransactionRepository,
    DailyTransactionRepository,
    MasterRepository,
)
from app.services.bank_master_service import BankMasterService
from app.utils.db_session import persist

STATE_CODES = {
    "jammu and kashmir": "01",
    "himachal pradesh": "02",
    "punjab": "03",
    "chandigarh": "04",
    "uttarakhand": "05",
    "haryana": "06",
    "delhi": "07",
    "rajasthan": "08",
    "uttar pradesh": "09",
    "bihar": "10",
    "sikkim": "11",
    "arunachal pradesh": "12",
    "nagaland": "13",
    "manipur": "14",
    "mizoram": "15",
    "tripura": "16",
    "meghalaya": "17",
    "assam": "18",
    "west bengal": "19",
    "jharkhand": "20",
    "odisha": "21",
    "chhattisgarh": "22",
    "madhya pradesh": "23",
    "gujarat": "24",
    "maharashtra": "27",
    "karnataka": "29",
    "goa": "30",
    "kerala": "32",
    "tamil nadu": "33",
    "telangana": "36",
    "andhra pradesh": "37",
}


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def amount_in_words_inr(amount: Decimal) -> str:
    ones = [
        "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
        "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
        "Seventeen", "Eighteen", "Nineteen",
    ]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def _two(n: int) -> str:
        if n < 20:
            return ones[n]
        return (tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")).strip()

    def _three(n: int) -> str:
        if n >= 100:
            rest = _two(n % 100)
            return ones[n // 100] + " Hundred" + ((" " + rest) if rest else "")
        return _two(n)

    rupees = int(amount)
    paise = int(_q(amount - Decimal(rupees)) * 100)
    if rupees == 0 and paise == 0:
        return "Zero Rupees Only."

    parts: list[str] = []
    crore = rupees // 10000000
    rupees %= 10000000
    lakh = rupees // 100000
    rupees %= 100000
    thousand = rupees // 1000
    rupees %= 1000
    if crore:
        parts.append(_two(crore) + " Crore")
    if lakh:
        parts.append(_two(lakh) + " Lakh")
    if thousand:
        parts.append(_two(thousand) + " Thousand")
    if rupees:
        parts.append(_three(rupees))
    words = " ".join(parts) + " Rupees"
    if paise:
        words += " and " + _two(paise) + " Paise"
    return words + " Only."


class GstInvoiceService:
    def __init__(
        self,
        repository: GstInvoiceRepository | None = None,
        item_repo: ItemMasterRepository | None = None,
    ):
        self.repo = repository or GstInvoiceRepository()
        self.item_repo = item_repo or ItemMasterRepository()

    @staticmethod
    def _money(value, default: str = "0") -> Decimal:
        if value in (None, ""):
            return Decimal(default)
        try:
            return _q(Decimal(str(value)))
        except (InvalidOperation, ValueError):
            return Decimal(default)

    @staticmethod
    def _qty(value, default: str = "1") -> Decimal:
        if value in (None, ""):
            return Decimal(default)
        try:
            return Decimal(str(value)).quantize(Decimal("0.001"))
        except (InvalidOperation, ValueError):
            return Decimal(default)

    @staticmethod
    def _split_gst_inclusive(gross: Decimal, gst_rate: Decimal, intra_state: bool) -> dict:
        """Split a GST-inclusive amount into taxable value. Total stays equal to gross."""
        gross = _q(gross)
        gst_rate = _q(gst_rate)
        if gross <= 0 or gst_rate <= 0:
            return {
                "taxable": gross if gross > 0 else Decimal("0.00"),
                "cgst_rate": Decimal("0.00"),
                "cgst": Decimal("0.00"),
                "sgst_rate": Decimal("0.00"),
                "sgst": Decimal("0.00"),
                "igst_rate": Decimal("0.00"),
                "igst": Decimal("0.00"),
                "round_off": Decimal("0.00"),
                "invoice_value": gross if gross > 0 else Decimal("0.00"),
                "tax_type": "CGST_SGST" if intra_state else "IGST",
            }
        taxable = _q(gross * Decimal("100") / (Decimal("100") + gst_rate))
        if intra_state:
            half = _q(gst_rate / 2)
            cgst = _q(taxable * half / Decimal("100"))
            sgst = _q(taxable * half / Decimal("100"))
            igst = Decimal("0.00")
            igst_rate = Decimal("0.00")
            cgst_rate = sgst_rate = half
            tax_type = "CGST_SGST"
            tax_sum = _q(cgst + sgst)
        else:
            igst_rate = gst_rate
            igst = _q(taxable * igst_rate / Decimal("100"))
            cgst = sgst = Decimal("0.00")
            cgst_rate = sgst_rate = Decimal("0.00")
            tax_type = "IGST"
            tax_sum = igst
        round_off = _q(gross - _q(taxable + tax_sum))
        return {
            "taxable": taxable,
            "cgst_rate": cgst_rate,
            "cgst": cgst,
            "sgst_rate": sgst_rate,
            "sgst": sgst,
            "igst_rate": igst_rate,
            "igst": igst,
            "round_off": round_off,
            "invoice_value": gross,
            "tax_type": tax_type,
        }

    def _source_bill_gross(self, inv: GstInvoice) -> Decimal | None:
        """Category or followup bill amount the user typed. That figure is the invoice total."""
        from app.models.followup import FollowupEntryMaster
        from app.models.others import OthersIncomeExpenseMaster

        keys = {(inv.TallyBillNo or "").strip(), (inv.InvoiceNo or "").strip()}
        keys.discard("")
        if not keys:
            return None
        misc = db.session.scalars(
            select(OthersIncomeExpenseMaster).where(
                OthersIncomeExpenseMaster.IsActive == True,
                or_(
                    OthersIncomeExpenseMaster.BillNo.in_(keys),
                    OthersIncomeExpenseMaster.TallyBillNo.in_(keys),
                ),
            )
        ).first()
        if misc is not None and misc.Amount is not None:
            gross = _q(Decimal(str(misc.Amount)))
            if gross > 0:
                return gross
        followup = db.session.scalars(
            select(FollowupEntryMaster).where(
                FollowupEntryMaster.IsActive == True,
                or_(
                    FollowupEntryMaster.BillNo.in_(keys),
                    FollowupEntryMaster.ApplicationNumber.in_(keys),
                ),
            )
        ).first()
        if followup is not None and followup.BillAmount is not None:
            gross = _q(Decimal(str(followup.BillAmount)))
            if gross > 0:
                return gross
        return None

    def rebifurcate_miscellaneous_inclusive(self) -> int:
        """Rewrite Miscellaneous sale invoices that added GST on top of an inclusive amount.

        A ₹400 category amount was stored as taxable and posted as ₹472. Those
        invoices are split so Invoice Value stays ₹400 and the daily sale matches.
        """
        self.repo.ensure_schema()
        invoices = list(
            db.session.scalars(
                select(GstInvoice).where(
                    GstInvoice.BillSource == self.BILL_SOURCE_MISCELLANEOUS,
                    GstInvoice.VoucherType == self.VOUCHER_SALE,
                )
            ).all()
        )
        changed = 0
        for inv in invoices:
            lines = self.repo.list_lines(inv.InvoiceID)
            if not lines:
                continue
            gst_rate = max(
                (_q(Decimal(str(line.GstRatePercent or 0))) for line in lines),
                default=Decimal("0.00"),
            )
            gross = Decimal("0.00")
            for line in lines:
                qty = Decimal(str(line.Qty or 0))
                rate = Decimal(str(line.Rate or 0))
                discount = Decimal(str(line.DiscountAmount or 0))
                gross += _q(qty * rate - discount)
            gross = _q(gross)
            current = _q(Decimal(str(inv.InvoiceValue or 0)))
            source_gross = self._source_bill_gross(inv)
            if gst_rate <= 0:
                if source_gross and source_gross > 0 and abs(current - source_gross) > Decimal("0.05"):
                    inv.InvoiceValue = source_gross
                    inv.TaxableValue = source_gross
                    inv.ListPrice = source_gross
                    inv.AmountInWords = amount_in_words_inr(source_gross)
                    inv.UpdatedAt = datetime.utcnow()
                    changed += 1
                continue
            if gross <= 0 and not (source_gross and source_gross > 0):
                continue
            if source_gross and source_gross > 0:
                if abs(current - source_gross) <= Decimal("0.05"):
                    continue
                gross = source_gross
            else:
                added_on_top = _q(gross * (Decimal("100") + gst_rate) / Decimal("100"))
                if abs(current - added_on_top) > Decimal("0.05") or abs(current - gross) <= Decimal("0.05"):
                    continue
            intra = (inv.TaxType or "") == "CGST_SGST" or (
                _q(Decimal(str(inv.CgstAmount or 0))) > 0
                or _q(Decimal(str(inv.SgstAmount or 0))) > 0
            )
            split = self._split_gst_inclusive(gross, gst_rate, intra)
            if len(lines) == 1:
                line = lines[0]
                qty = Decimal(str(line.Qty or 1)) or Decimal("1")
                line.Rate = _q(split["taxable"] / qty)
                line.TaxableValue = split["taxable"]
            else:
                # Spread the inclusive gross across lines by their current share.
                shares = []
                for line in lines:
                    qty = Decimal(str(line.Qty or 0))
                    rate = Decimal(str(line.Rate or 0))
                    discount = Decimal(str(line.DiscountAmount or 0))
                    shares.append(_q(qty * rate - discount))
                share_total = _q(sum(shares, Decimal("0.00"))) or Decimal("1")
                for line, share in zip(lines, shares):
                    part = self._split_gst_inclusive(
                        _q(gross * share / share_total), gst_rate, intra
                    )
                    qty = Decimal(str(line.Qty or 1)) or Decimal("1")
                    line.Rate = _q(part["taxable"] / qty)
                    line.TaxableValue = part["taxable"]
            inv.ListPrice = split["taxable"]
            inv.TaxableValue = split["taxable"]
            inv.TaxType = split["tax_type"]
            inv.CgstRate = split["cgst_rate"]
            inv.CgstAmount = split["cgst"]
            inv.SgstRate = split["sgst_rate"]
            inv.SgstAmount = split["sgst"]
            inv.IgstRate = split["igst_rate"]
            inv.IgstAmount = split["igst"]
            inv.RoundOffAmount = split["round_off"]
            inv.InvoiceValue = split["invoice_value"]
            inv.AmountInWords = amount_in_words_inr(split["invoice_value"])
            inv.UpdatedAt = datetime.utcnow()
            self._sync_sale_daily(inv)
            changed += 1
        if changed:
            db.session.commit()
        return changed

    def _parse_round_off(self, payload: dict) -> Decimal:
        sign = str(
            payload.get("round_off_sign") or payload.get("RoundOffSign") or ""
        ).strip().lower()
        mag = abs(
            self._money(payload.get("round_off_amount") or payload.get("RoundOffAmount"))
        )
        if mag > Decimal("100"):
            raise ValueError("Round off cannot be more than 100.00.")
        if sign in {"add", "+", "plus"}:
            return mag
        if sign in {"sub", "subtract", "-", "minus"}:
            return -mag
        signed = payload.get("round_off")
        if signed not in (None, ""):
            value = self._money(signed)
            if abs(value) > Decimal("100"):
                raise ValueError("Round off cannot be more than 100.00.")
            return value
        return Decimal("0.00")

    @staticmethod
    def _round_off_sign(value) -> str:
        try:
            amount = float(value or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount > 0:
            return "add"
        if amount < 0:
            return "sub"
        return ""

    @staticmethod
    def _line_text(*values) -> str:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    @classmethod
    def line_particulars_parts(
        cls, line: dict, *, include_tax_period: bool = True
    ) -> tuple[str, str]:
        """Item name on the first line; tax year / quarter / month / notes in brackets."""
        item_name = cls._line_text(line.get("item_name"), line.get("ItemName"))
        particulars = cls._line_text(line.get("particulars"), line.get("Particulars"))
        tax_period = cls._line_text(line.get("tax_period"), line.get("TaxPeriod"))
        quarter = cls._line_text(line.get("quarter"), line.get("Quarter"))
        month = cls._line_text(line.get("month"), line.get("Month"))
        main = item_name or particulars or "—"
        extras: list[str] = []
        if include_tax_period and tax_period:
            extras.append(tax_period)
        if quarter:
            extras.append(quarter)
        if month:
            extras.append(month)
        if (
            particulars
            and item_name
            and particulars.casefold() != item_name.casefold()
        ):
            extras.append(particulars)
        return main, ", ".join(extras)

    @classmethod
    def misc_particulars(cls, item_name: str, item_description: str | None = None) -> str:
        """Particulars for Misc-generated bills: Item (description)."""
        name = (item_name or "").strip()
        desc = (item_description or "").strip()
        if name and desc:
            return f"{name} ({desc})"[:300]
        return (name or desc or "")[:300]

    @staticmethod
    def company_profile() -> dict[str, str]:
        cfg = current_app.config
        return {
            "name": cfg.get("COMPANY_DISPLAY_NAME", "Joshi Tax Consultancy & Services"),
            "gstin": cfg.get("COMPANY_GSTIN", "05AEBPJ1665H2ZR"),
            "pan": cfg.get("COMPANY_PAN", "AEBPJ1665H"),
            "cin": cfg.get("COMPANY_CIN", ""),
            "address": cfg.get(
                "COMPANY_ADDRESS",
                "Sanjay Colony, Nainital Road, Haldwani, Uttarakhand 263139",
            ),
            "state": cfg.get("COMPANY_STATE", "Uttarakhand"),
            "state_code": cfg.get("COMPANY_STATE_CODE", "05"),
            "phone": cfg.get("COMPANY_PHONE", "9412040614"),
            "email": cfg.get("COMPANY_EMAIL", "admin@jtcsxpert.com"),
            "website": cfg.get("COMPANY_WEBSITE", "www.jtcsxpert.com"),
            "logo_filename": "img/jtcs_invoice_logo.png",
        }

    @staticmethod
    def state_code_from_name(state: str | None) -> str:
        if not state:
            return ""
        key = state.strip().lower()
        return STATE_CODES.get(key, "")

    def _load_customer(self, customer_id: int | None) -> dict[str, Any]:
        if not customer_id:
            return {}
        row = db.session.execute(
            text(
                """
                SELECT TOP 1
                    CustomerID, CustomerName, MobileNumber,
                    ISNULL(EmailID, '') AS EmailID,
                    ISNULL(AddressLine1, '') AS AddressLine1,
                    ISNULL(AddressLine2, '') AS AddressLine2,
                    ISNULL(City, '') AS City,
                    ISNULL(State, '') AS State,
                    ISNULL(Pincode, '') AS Pincode,
                    ISNULL(GSTNumber, '') AS GSTNumber
                FROM dbo.CustomerMaster
                WHERE CustomerID = :cid
                """
            ),
            {"cid": customer_id},
        ).mappings().first()
        if not row:
            return {}
        addr_parts = [
            (row["AddressLine1"] or "").strip(),
            (row["AddressLine2"] or "").strip(),
            (row["City"] or "").strip(),
            (row["State"] or "").strip(),
            (row["Pincode"] or "").strip(),
        ]
        address = ", ".join(p for p in addr_parts if p)
        gstin = (row["GSTNumber"] or "").strip()
        state = (row["State"] or "").strip()
        code = gstin[:2] if len(gstin) >= 2 and gstin[:2].isdigit() else self.state_code_from_name(state)
        return {
            "customer_id": int(row["CustomerID"]),
            "customer_name": (row["CustomerName"] or "").strip(),
            "contact_person": "",
            "billing_address": address,
            "customer_gstin": gstin,
            "contact_mobile": (row["MobileNumber"] or "").strip(),
            "contact_email": (row["EmailID"] or "").strip(),
            "place_of_supply": state,
            "place_of_supply_code": code,
        }

    def search_customers(self, q: str | None = None, limit: int = 30) -> list[dict]:
        term = (q or "").strip()
        lim = max(1, min(int(limit or 30), 100))
        params: dict[str, Any] = {}
        where = "WHERE 1=1"
        if term:
            where += (
                " AND (CustomerName LIKE :term OR MobileNumber LIKE :term"
                " OR CAST(CustomerID AS NVARCHAR(20)) LIKE :term OR GSTNumber LIKE :term)"
            )
            params["term"] = f"%{term}%"
        rows = db.session.execute(
            text(
                f"""
                SELECT TOP {lim}
                    CustomerID, CustomerName, MobileNumber,
                    ISNULL(EmailID, '') AS EmailID,
                    ISNULL(State, '') AS State,
                    ISNULL(GSTNumber, '') AS GSTNumber
                FROM dbo.CustomerMaster
                {where}
                ORDER BY CustomerName
                """
            ),
            params,
        ).mappings().all()
        return [
            {
                "customer_id": int(r["CustomerID"]),
                "customer_name": r["CustomerName"] or "",
                "mobile": r["MobileNumber"] or "",
                "email": r["EmailID"] or "",
                "state": r["State"] or "",
                "gstin": r["GSTNumber"] or "",
                "label": f"{r['CustomerName']} (#{r['CustomerID']})",
            }
            for r in rows
        ]

    INVOICE_KIND_GST = "GST"
    INVOICE_KIND_NON_GST = "NON_GST"
    VOUCHER_SALE = "SALE"
    VOUCHER_PURCHASE = "PURCHASE"
    DAILY_WORK_TYPE = "Accounting"
    DAILY_SUB_WORK_TYPE = "Sale / Service Invoice"
    BILL_SOURCE_MANUAL = "Manual"
    BILL_SOURCE_AUTOMATIC = "Automatic"
    BILL_SOURCE_IMPORT = "Import"
    BILL_SOURCE_MISCELLANEOUS = "Miscellaneous"
    BILL_SOURCES = (
        BILL_SOURCE_MANUAL,
        BILL_SOURCE_AUTOMATIC,
        BILL_SOURCE_IMPORT,
        BILL_SOURCE_MISCELLANEOUS,
    )
    # Purchase payment → bank ledger only (never used by Sale / other modules).
    PURCHASE_BANK_SOURCE_TABLE = "GstInvoice"
    PURCHASE_BANK_SOURCE_TYPE = "PURCHASE"
    PURCHASE_BANK_DESCRIPTION = "Purchase Invoice Payment"

    @staticmethod
    def normalize_bill_source(value) -> str:
        raw = (str(value or "")).strip().lower().replace(" ", "_").replace("-", "_")
        if raw in {"automatic", "auto", "temp", "temporary"}:
            return GstInvoiceService.BILL_SOURCE_AUTOMATIC
        if raw in {"import", "imported", "daybook"}:
            return GstInvoiceService.BILL_SOURCE_IMPORT
        if raw in {"miscellaneous", "misc", "oie_misc", "others_misc"}:
            return GstInvoiceService.BILL_SOURCE_MISCELLANEOUS
        return GstInvoiceService.BILL_SOURCE_MANUAL

    @staticmethod
    def normalize_voucher_type(value) -> str:
        raw = (str(value or "")).strip().upper().replace(" ", "_").replace("-", "_")
        if raw in {"PURCHASE", "PURCH", "BUY"}:
            return GstInvoiceService.VOUCHER_PURCHASE
        return GstInvoiceService.VOUCHER_SALE

    @staticmethod
    def normalize_invoice_kind(value) -> str:
        raw = (str(value or "")).strip().upper().replace(" ", "_").replace("-", "_")
        if raw in {"GST", "GST_INVOICE"}:
            return GstInvoiceService.INVOICE_KIND_GST
        if raw in {"NON_GST", "NONGST", "NON_GST_INVOICE", "NON"}:
            return GstInvoiceService.INVOICE_KIND_NON_GST
        raise ValueError("Invoice type is required. Choose GST Invoice or Non GST Invoice.")

    @staticmethod
    def _fy_years(invoice_date: date) -> tuple[int, int]:
        """Indian FY Apr–Mar → (start_year, end_year), e.g. 2026-07-18 → (2026, 2027)."""
        if invoice_date.month >= 4:
            return invoice_date.year, invoice_date.year + 1
        return invoice_date.year - 1, invoice_date.year

    def invoice_no_prefix(self, invoice_date: date, invoice_kind: str) -> str:
        kind = self.normalize_invoice_kind(invoice_kind)
        y1, y2 = self._fy_years(invoice_date)
        if kind == self.INVOICE_KIND_GST:
            # JTCS/2026-27/
            return f"JTCS/{y1}-{y2 % 100:02d}/"
        # Non-GST: JTCS/2027/  (ending FY year)
        return f"JTCS/{y2}/"

    def next_invoice_no(
        self,
        invoice_date: date | None = None,
        *,
        invoice_kind: str | None = None,
    ) -> str:
        d = invoice_date or date.today()
        kind = self.normalize_invoice_kind(invoice_kind or self.INVOICE_KIND_NON_GST)
        prefix = self.invoice_no_prefix(d, kind)
        seq = self.repo.next_sequence(prefix)
        return f"{prefix}{seq:05d}"

    def _pay_banks_from_invoice(self, inv) -> list[dict]:
        import json

        raw = getattr(inv, "PayBankAccounts", None) or ""
        banks: list[dict] = []
        if raw:
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError):
                parsed = []
            if isinstance(parsed, list):
                banks = [row for row in parsed if isinstance(row, dict)][:2]
        if banks:
            return banks
        upi = self._live_pay_upi_id(inv)
        number = (getattr(inv, "PayAccountNumber", None) or "").strip()
        if not upi and not number:
            return []
        return [
            {
                "account_id": getattr(inv, "PaymentBankAccountID", None),
                "bank_name": getattr(inv, "PayBankName", None) or "",
                "account_number": number,
                "ifsc_code": getattr(inv, "PayIFSC", None) or "",
                "branch_name": getattr(inv, "PayBranch", None) or "",
                "account_holder_name": getattr(inv, "PayAccountHolder", None) or "",
                "account_type": getattr(inv, "PayAccountType", None) or "",
                "upi_id": upi,
            }
        ]

    @staticmethod
    def _form_flag(payload: dict, *keys: str) -> bool:
        raw = None
        for key in keys:
            if key in payload:
                raw = payload.get(key)
                break
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    def _tally_status_header(self, payload: dict, bill_source: str, voucher_type: str) -> dict:
        if (
            bill_source != self.BILL_SOURCE_MISCELLANEOUS
            or voucher_type != self.VOUCHER_SALE
            or "bill_approved" not in payload
        ):
            return {}
        reason_unapprove = (payload.get("bill_unapprove_reason") or "").strip()[:500]
        reason_remove = (payload.get("payment_remove_reason") or "").strip()[:500]
        return {
            "BillApproved": self._form_flag(payload, "bill_approved"),
            "BillUnapproveReason": reason_unapprove or None,
            "InvoicePaymentReceived": self._form_flag(payload, "payment_received"),
            "InvoicePaymentRemoveReason": reason_remove or None,
        }

    def _guard_tally_status_change(self, inv: GstInvoice, payload: dict) -> None:
        """Removing approval or a received payment needs a login and a reason."""
        if "bill_approved" not in payload:
            return
        source = self.normalize_bill_source(getattr(inv, "BillSource", None))
        if source != self.BILL_SOURCE_MISCELLANEOUS:
            return
        new_approved = self._form_flag(payload, "bill_approved")
        old_approved = bool(getattr(inv, "BillApproved", False))
        old_paid = self._saved_payment_received(inv)
        removing_approval = old_approved and not new_approved
        removing_payment = False
        if "payment_received" in payload:
            new_paid = self._form_flag(payload, "payment_received")
            removing_payment = old_paid and not new_paid
        if not removing_approval and not removing_payment:
            return
        from app.utils.delete_auth import verify_delete_credentials

        verify_delete_credentials(
            str(payload.get("user_id") or payload.get("userid") or ""),
            str(payload.get("password") or ""),
        )
        if removing_approval and not (payload.get("bill_unapprove_reason") or "").strip():
            raise ValueError("Enter the reason for removing approval.")
        if removing_payment and not (payload.get("payment_remove_reason") or "").strip():
            raise ValueError("Enter the reason for removing Payment Received.")

    def _linked_misc_entries(self, inv: GstInvoice):
        from app.models.others import OthersIncomeExpenseMaster

        keys = {
            (inv.TallyBillNo or "").strip(),
            (inv.InvoiceNo or "").strip(),
        }
        keys.discard("")
        if not keys:
            return []
        return list(
            db.session.scalars(
                select(OthersIncomeExpenseMaster).where(
                    OthersIncomeExpenseMaster.IsActive == True,  # noqa: E712
                    OthersIncomeExpenseMaster.BillNo.in_(keys)
                    | OthersIncomeExpenseMaster.TallyBillNo.in_(keys),
                )
            ).all()
        )

    def _linked_followup_paid(self, inv: GstInvoice) -> bool | None:
        from app.models.followup import FollowupEntryMaster, FollowupEntryStage, FollowupWorkflowStage

        keys = {
            (inv.TallyBillNo or "").strip().upper(),
            (inv.InvoiceNo or "").strip().upper(),
        }
        keys.discard("")
        if not keys:
            return None
        bill_key = func.upper(func.ltrim(func.rtrim(FollowupEntryMaster.BillNo)))
        app_key = func.upper(func.ltrim(func.rtrim(FollowupEntryMaster.ApplicationNumber)))
        entries = list(
            db.session.scalars(
                select(FollowupEntryMaster).where(
                    FollowupEntryMaster.IsActive == True,  # noqa: E712
                    bill_key.in_(keys) | app_key.in_(keys),
                )
            ).all()
        )
        if not entries:
            return None
        entry_ids = [entry.EntryID for entry in entries]
        paid = db.session.scalar(
            select(FollowupEntryStage.EntryStageID)
            .join(FollowupWorkflowStage, FollowupWorkflowStage.StageID == FollowupEntryStage.StageID)
            .where(
                FollowupEntryStage.EntryID.in_(entry_ids),
                FollowupWorkflowStage.StageCode == "payment_received",
            )
            .limit(1)
        )
        return paid is not None

    def _source_payment_received(self, inv: GstInvoice) -> bool | None:
        """Payment Received on the screen that created this bill. None if no source row."""
        misc_entries = self._linked_misc_entries(inv)
        followup_paid = self._linked_followup_paid(inv)
        if misc_entries and followup_paid is not None:
            return any(bool(entry.PaymentReceived) for entry in misc_entries) or followup_paid
        if misc_entries:
            return any(bool(entry.PaymentReceived) for entry in misc_entries)
        return followup_paid

    def _saved_payment_received(self, inv: GstInvoice) -> bool:
        source_paid = self._source_payment_received(inv)
        if source_paid is not None:
            return source_paid
        stored = getattr(inv, "InvoicePaymentReceived", None)
        if stored is not None:
            return bool(stored)
        return False

    def sync_payment_received_for_bill(self, bill_no: str, paid: bool) -> None:
        """Keep converted sale invoices ticked from the source payment variable."""
        ids = self.repo.list_ids_for_bill_no(bill_no)
        if not ids:
            return
        for invoice_id in ids:
            inv = self.repo.get_by_id(invoice_id)
            if inv is None:
                continue
            inv.InvoicePaymentReceived = bool(paid)
            inv.UpdatedAt = datetime.utcnow()
        db.session.flush()

    def mark_source_payment_received(self, bill_no: str, paid: bool) -> None:
        """User Yes/No on the source entry. Sale invoice follows this flag."""
        key = (bill_no or "").strip()
        if not key:
            raise ValueError("Bill number is required.")
        for entry in self._linked_misc_entries_by_bill(key):
            entry.PaymentReceived = bool(paid)
        self.sync_payment_received_for_bill(key, paid)
        db.session.commit()

    def _linked_misc_entries_by_bill(self, bill_no: str):
        from app.models.others import OthersIncomeExpenseMaster

        key = (bill_no or "").strip()
        if not key:
            return []
        return list(
            db.session.scalars(
                select(OthersIncomeExpenseMaster).where(
                    OthersIncomeExpenseMaster.IsActive == True,  # noqa: E712
                    (OthersIncomeExpenseMaster.BillNo == key)
                    | (OthersIncomeExpenseMaster.TallyBillNo == key),
                )
            ).all()
        )

    def _sync_misc_payment_received(self, inv: GstInvoice) -> None:
        source = self.normalize_bill_source(getattr(inv, "BillSource", None))
        if source != self.BILL_SOURCE_MISCELLANEOUS:
            return
        if getattr(inv, "InvoicePaymentReceived", None) is None:
            return
        paid = bool(inv.InvoicePaymentReceived)
        for entry in self._linked_misc_entries(inv):
            entry.PaymentReceived = paid

    def _payment_bank_ids(self, payload: dict) -> list[int]:
        raw = payload.get("payment_bank_account_ids")
        if raw in (None, ""):
            raw = payload.get("PaymentBankAccountIDs")
        ids: list[int] = []
        if isinstance(raw, str):
            raw = [part.strip() for part in raw.split(",") if part.strip()]
        if isinstance(raw, list):
            for item in raw:
                try:
                    ids.append(int(item))
                except (TypeError, ValueError):
                    continue
        if not ids:
            single = payload.get("payment_bank_account_id") or payload.get(
                "PaymentBankAccountID"
            )
            try:
                if single not in (None, ""):
                    ids.append(int(single))
            except (TypeError, ValueError):
                pass
        ordered: list[int] = []
        for account_id in ids:
            if account_id not in ordered:
                ordered.append(account_id)
        if len(ordered) > 2:
            raise ValueError("Select at most 2 bank accounts.")
        return ordered

    def _live_pay_upi_id(self, inv) -> str:
        """Prefer snapshotted UPI; if blank, use current Bank Master UPI for that account."""
        snap = (getattr(inv, "PayUpiId", None) or "").strip()
        if snap:
            return snap
        bank_id = getattr(inv, "PaymentBankAccountID", None)
        if not bank_id:
            return ""
        try:
            bank_svc = BankMasterService()
            bank_svc.repo.ensure_schema()
            bank = bank_svc.repo.get_by_id(int(bank_id))
            if bank is None:
                return ""
            return (getattr(bank, "UpiId", None) or "").strip()
        except Exception:
            return ""

    def _serialize(self, inv, lines: list | None = None) -> dict:
        if lines is None:
            lines = self.repo.list_lines(inv.InvoiceID)
        data = {
            "invoice_id": inv.InvoiceID,
            "invoice_no": inv.InvoiceNo,
            "invoice_date": inv.InvoiceDate.isoformat() if inv.InvoiceDate else "",
            "customer_id": inv.CustomerID,
            "customer_name": inv.CustomerName or "",
            "contact_person": inv.ContactPerson or "",
            "billing_address": inv.BillingAddress or "",
            "customer_gstin": inv.CustomerGSTIN or "",
            "contact_mobile": inv.ContactMobile or "",
            "contact_email": inv.ContactEmail or "",
            "place_of_supply": inv.PlaceOfSupply or "",
            "place_of_supply_code": inv.PlaceOfSupplyCode or "",
            "reverse_charge": bool(inv.ReverseCharge),
            "invoice_kind": getattr(inv, "InvoiceKind", None)
            or self.INVOICE_KIND_NON_GST,
            "voucher_type": getattr(inv, "VoucherType", None) or self.VOUCHER_SALE,
            "tax_type": inv.TaxType or "IGST",
            "list_price": float(inv.ListPrice or 0),
            "discount_amount": float(inv.DiscountAmount or 0),
            "taxable_value": float(inv.TaxableValue or 0),
            "cgst_rate": float(inv.CgstRate or 0),
            "cgst_amount": float(inv.CgstAmount or 0),
            "sgst_rate": float(inv.SgstRate or 0),
            "sgst_amount": float(inv.SgstAmount or 0),
            "igst_rate": float(inv.IgstRate or 0),
            "igst_amount": float(inv.IgstAmount or 0),
            "invoice_value": float(inv.InvoiceValue or 0),
            "round_off": float(getattr(inv, "RoundOffAmount", 0) or 0),
            "round_off_amount": abs(float(getattr(inv, "RoundOffAmount", 0) or 0)),
            "round_off_sign": self._round_off_sign(getattr(inv, "RoundOffAmount", 0)),
            "amount_in_words": inv.AmountInWords or "",
            "notes": inv.Notes or "",
            "payment_bank_account_id": getattr(inv, "PaymentBankAccountID", None),
            "pay_bank_name": getattr(inv, "PayBankName", None) or "",
            "pay_account_number": getattr(inv, "PayAccountNumber", None) or "",
            "pay_ifsc": getattr(inv, "PayIFSC", None) or "",
            "pay_branch": getattr(inv, "PayBranch", None) or "",
            "pay_account_holder": getattr(inv, "PayAccountHolder", None) or "",
            "pay_account_type": getattr(inv, "PayAccountType", None) or "",
            "pay_upi_id": self._live_pay_upi_id(inv),
            "bill_approved": bool(getattr(inv, "BillApproved", False)),
            "bill_unapprove_reason": getattr(inv, "BillUnapproveReason", None) or "",
            "payment_received": self._saved_payment_received(inv),
            "payment_remove_reason": getattr(inv, "InvoicePaymentRemoveReason", None) or "",
            "converted_invoice": self.normalize_bill_source(getattr(inv, "BillSource", None))
            == self.BILL_SOURCE_MISCELLANEOUS,
            "origin_path": self._origin_path(inv),
            "pay_banks": self._pay_banks_from_invoice(inv),
            "payment_bank_account_ids": [
                bank.get("account_id")
                for bank in self._pay_banks_from_invoice(inv)
                if bank.get("account_id")
            ],
            "payment_date": (
                inv.PaymentDate.isoformat()
                if getattr(inv, "PaymentDate", None)
                else ""
            ),
            "amount_paid": (
                float(inv.AmountPaid)
                if getattr(inv, "AmountPaid", None) is not None
                else None
            ),
            "tally_bill_no": (getattr(inv, "TallyBillNo", None) or "").strip(),
            "bill_source": self.normalize_bill_source(
                getattr(inv, "BillSource", None) or self.BILL_SOURCE_MANUAL
            ),
            "created_at": inv.CreatedAt.isoformat() if inv.CreatedAt else "",
            "lines": self._serialize_lines(lines),
        }
        if data["bill_source"] == self.BILL_SOURCE_MISCELLANEOUS:
            for line in data["lines"]:
                # PDF / HTML preview: Item (description) only — no tax year brackets.
                line["particulars_display"] = (line.get("particulars") or "").strip() or "—"
                line["particulars_extra"] = ""
        return data

    def _item_names_by_id(self, item_ids: list) -> dict[int, str]:
        names: dict[int, str] = {}
        for item_id in {iid for iid in item_ids if iid}:
            item = self.item_repo.get_by_id(item_id)
            if item:
                names[int(item_id)] = item.ItemName or ""
        return names

    def _serialize_lines(self, lines: list) -> list[dict]:
        item_names = self._item_names_by_id(
            [getattr(ln, "ItemID", None) for ln in lines]
        )
        out: list[dict] = []
        for ln in lines:
            item_id = getattr(ln, "ItemID", None)
            row = {
                "sr_no": ln.SrNo,
                "item_id": item_id,
                "item_name": item_names.get(int(item_id), "") if item_id else "",
                "tax_period": getattr(ln, "TaxPeriod", None) or "",
                "quarter": getattr(ln, "Quarter", None) or "",
                "month": getattr(ln, "Month", None) or "",
                "particulars": ln.Particulars,
                "hsn_sac": ln.HsnSac or "",
                "unit": ln.Unit or "",
                "qty": float(ln.Qty or 0),
                "rate": float(ln.Rate or 0),
                "discount_amount": float(ln.DiscountAmount or 0),
                "taxable_value": float(ln.TaxableValue or 0),
                "gst_rate_percent": float(ln.GstRatePercent or 0),
            }
            display, extra = self.line_particulars_parts(row)
            row["particulars_display"] = display
            row["particulars_extra"] = extra
            out.append(row)
        return out

    def list_records(
        self,
        *,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        voucher_type: str | None = None,
    ) -> list[dict]:
        # Automatic invoice backfill disabled — Sales Invoice is a separate module;
        # followup/OIE/ration no longer auto-create Sale / Service Invoice rows.
        vt = self.normalize_voucher_type(voucher_type) if voucher_type else None
        return [
            self._serialize(inv, lines=[])
            for inv in self.repo.list_all(
                search=search,
                date_from=date_from,
                date_to=date_to,
                voucher_type=vt,
            )
        ]

    def get_record(self, invoice_id: int) -> dict:
        inv = self.repo.get_by_id(invoice_id)
        if inv is None:
            raise ValueError("Invoice not found.")
        data = self._serialize(inv)
        if data.get("converted_invoice"):
            try:
                data["review_steps"] = self._review_steps(inv, data)
            except Exception:
                data["review_steps"] = [
                    {
                        "title": "Source entry",
                        "detail": data.get("origin_path") or "Review details could not be loaded.",
                    }
                ]
        return data

    def _review_steps(self, inv: GstInvoice, invoice: dict) -> list[dict]:
        """What the user did on the source screen, in order, for admin review."""
        keys = {(inv.TallyBillNo or "").strip(), (inv.InvoiceNo or "").strip()}
        keys.discard("")
        followup = self._review_followup(keys)
        if followup is not None:
            return self._followup_review_steps(followup, invoice)
        misc = self._review_misc(keys)
        if misc is not None:
            return self._misc_review_steps(misc, invoice)
        return [
            {
                "title": "Source entry",
                "detail": invoice.get("origin_path") or "Source entry was not found.",
            }
        ]

    def _review_followup(self, keys: set[str]):
        from app.models.followup import FollowupEntryMaster

        if not keys:
            return None
        return db.session.scalars(
            select(FollowupEntryMaster).where(
                FollowupEntryMaster.IsActive == True,  # noqa: E712
                FollowupEntryMaster.BillNo.in_(keys)
                | FollowupEntryMaster.ApplicationNumber.in_(keys),
            )
        ).first()

    def _review_misc(self, keys: set[str]):
        from app.models.others import OthersIncomeExpenseMaster

        if not keys:
            return None
        return db.session.scalars(
            select(OthersIncomeExpenseMaster).where(
                OthersIncomeExpenseMaster.IsActive == True,  # noqa: E712
                OthersIncomeExpenseMaster.BillNo.in_(keys)
                | OthersIncomeExpenseMaster.TallyBillNo.in_(keys),
            )
        ).first()

    @staticmethod
    def _money_text(value) -> str:
        try:
            return f"{float(value):,.2f}"
        except (TypeError, ValueError):
            return "0.00"

    def _misc_review_steps(self, row, invoice: dict) -> list[dict]:
        from app.services.others_income_expense_service import OthersIncomeExpenseService

        entry = OthersIncomeExpenseService().get_entry(row.EntryID)
        categories = entry.get("categories") or []
        category_text = "; ".join(
            (
                f"{item.get('work_name') or 'Category'}"
                + (f" / {item.get('sub_work_type')}" if item.get("sub_work_type") else "")
                + f" — Rs. {self._money_text(item.get('amount'))}"
            )
            for item in categories
        ) or "No category"
        payments = entry.get("payments") or []
        payment_text = self._payment_text(payments)
        source_amount = self._money_text(entry.get("amount"))
        invoice_amount = self._money_text(invoice.get("invoice_value"))
        amount_note = f"Bill amount entered by the user: Rs. {source_amount}."
        if source_amount != invoice_amount:
            amount_note += (
                f" Saved invoice copy shows Rs. {invoice_amount}. "
                "Use the amount the user entered."
            )
        return [
            {
                "title": "1. Where this entry came from",
                "detail": "Activities > Miscellaneous > Edit Entry",
            },
            {
                "title": "2. User created the entry",
                "detail": (
                    f"Bill {entry.get('bill_no') or '—'} on {entry.get('work_date') or '—'}. "
                    f"Customer: {entry.get('customer_name') or '—'}. "
                    f"Mobile: {entry.get('mobile_number') or '—'}."
                ),
            },
            {
                "title": "3. User entered the work and amount",
                "detail": f"{category_text}. Total bill amount: Rs. {source_amount}.",
            },
            {
                "title": "4. Work Done",
                "detail": "Yes" if entry.get("work_done") else "No",
            },
            {
                "title": "5. Tally Bill Generated",
                "detail": (
                    "Yes — " + (entry.get("tally_bill_no") or entry.get("bill_no") or "")
                    if entry.get("tally_bill_generated")
                    else "No"
                ),
            },
            {
                "title": "6. Generate bill",
                "detail": (
                    f"Invoice {invoice.get('invoice_no') or '—'} dated {invoice.get('invoice_date') or '—'}. "
                    + amount_note
                ),
            },
            {
                "title": "7. Payment details",
                "detail": payment_text or "No payment line saved.",
            },
            {
                "title": "8. Payment Received",
                "detail": "Yes" if entry.get("payment_received") else "No",
            },
        ]

    def _payment_text(self, payments: list) -> str:
        from app.models.transactions import JtcsBankAccountMaster

        parts = []
        for payment in payments:
            amount = self._money_text(payment.get("amount"))
            when = payment.get("payment_date") or "—"
            account_id = payment.get("bank_account_id")
            mode = "Payment"
            if account_id:
                account = db.session.get(JtcsBankAccountMaster, int(account_id))
                if account is not None:
                    mode = (account.BankName or "Bank").strip()
                    number = (getattr(account, "AccountNumber", None) or "").strip()
                    if number:
                        mode = f"{mode} — {number}"
            parts.append(f"{mode}: Rs. {amount} on {when}")
        return "; ".join(parts)

    def _followup_review_steps(self, row, invoice: dict) -> list[dict]:
        from app.services.followup_service import FollowupService

        module = (row.ModuleCode or "").strip().upper()
        entry = FollowupService(module).get_entry(row.EntryID)
        labels = {
            "GST": "Activities > GST Followup > Edit Entry",
            "ITR": "Activities > ITR Followup > Edit Entry",
            "TDS": "Activities > TDS Followup > Edit Entry",
            "DSC": "Activities > DSC Followup > Edit Entry",
        }
        stages = entry.get("completed_stages") or []
        stage_text = ", ".join(
            item.get("StageName") or item.get("StageCode") or ""
            for item in stages
            if (item.get("StageName") or item.get("StageCode"))
        ) or "No stage ticked"
        source_amount = self._money_text(entry.get("bill_amount") or entry.get("amount") or 0)
        invoice_amount = self._money_text(invoice.get("invoice_value"))
        amount_note = f"Bill amount on the entry: Rs. {source_amount}."
        if source_amount != invoice_amount:
            amount_note += (
                f" Saved invoice copy shows Rs. {invoice_amount}. "
                "Use the amount on the entry."
            )
        return [
            {"title": "1. Where this entry came from", "detail": labels.get(module, module or "Followup")},
            {
                "title": "2. User created the entry",
                "detail": (
                    f"Bill {entry.get('bill_no') or entry.get('application_number') or '—'} "
                    f"on {entry.get('work_date') or '—'}. "
                    f"Customer: {entry.get('customer_name') or '—'}. "
                    f"Period: {entry.get('tax_period') or '—'}."
                ),
            },
            {"title": "3. Stages the user completed", "detail": stage_text},
            {"title": "4. Bill amount", "detail": amount_note},
            {
                "title": "5. Payment details",
                "detail": self._payment_text(entry.get("payments") or []) or "No payment line saved.",
            },
            {
                "title": "6. Payment Received",
                "detail": "Yes" if "payment_received" in {
                    (item.get("StageCode") or "").lower() for item in stages
                } else "No",
            },
        ]

    def get_record_with_nav(self, invoice_id: int) -> dict:
        record = self.get_record(invoice_id)
        ids = self.list_ids()
        try:
            idx = ids.index(int(invoice_id))
        except ValueError:
            return {
                "record": record,
                "position": 0,
                "total": len(ids),
                "has_prior": False,
                "has_next": False,
            }
        pos = idx + 1
        return {
            "record": record,
            "position": pos,
            "total": len(ids),
            "has_prior": pos > 1,
            "has_next": pos < len(ids),
        }

    def preview_totals(self, payload: dict) -> dict:
        return self._build_header_and_lines(
            payload, persist_no=False, require_payment_bank=False
        )[2]

    def sale_status_by_bill_nos(self, bill_nos) -> dict[str, dict]:
        """Sale-invoice Bill Status and Payment Received keyed by bill number."""
        keys = {(str(item or "")).strip() for item in bill_nos}
        keys.discard("")
        if not keys:
            return {}
        rows = db.session.scalars(
            select(GstInvoice).where(
                GstInvoice.VoucherType == self.VOUCHER_SALE,
                GstInvoice.TallyBillNo.in_(keys) | GstInvoice.InvoiceNo.in_(keys),
            )
        ).all()
        found: dict[str, dict] = {}
        for inv in rows:
            payload = {
                "invoice_no": inv.InvoiceNo or "",
                "bill_status": "Approved" if bool(getattr(inv, "BillApproved", False)) else "Approve pending",
                "payment_received": "Yes" if self._saved_payment_received(inv) else "No",
            }
            for key in ((inv.TallyBillNo or "").strip(), (inv.InvoiceNo or "").strip()):
                if key:
                    found[key.upper()] = payload
        return found

    def _origin_path(self, inv: GstInvoice) -> str:
        source = self.normalize_bill_source(getattr(inv, "BillSource", None))
        if source != self.BILL_SOURCE_MISCELLANEOUS:
            return ""
        keys = {(inv.TallyBillNo or "").strip(), (inv.InvoiceNo or "").strip()}
        keys.discard("")
        labels = {
            "GST": "Activities → GST Followup → Edit Entry",
            "ITR": "Activities → ITR Followup → Edit Entry",
            "TDS": "Activities → TDS Followup → Edit Entry",
            "DSC": "Activities → DSC Followup → Edit Entry",
        }
        misc_path = "Activities → Miscellaneous → Edit Entry"
        if not keys:
            return misc_path
        from app.models.followup import FollowupEntryMaster
        from app.models.others import OthersIncomeExpenseMaster

        followup = db.session.scalars(
            select(FollowupEntryMaster).where(
                FollowupEntryMaster.IsActive == True,  # noqa: E712
                FollowupEntryMaster.BillNo.in_(keys),
            )
        ).first()
        if followup is not None:
            return labels.get((followup.ModuleCode or "").strip().upper(), misc_path)
        misc = db.session.scalars(
            select(OthersIncomeExpenseMaster).where(
                OthersIncomeExpenseMaster.IsActive == True,  # noqa: E712
                OthersIncomeExpenseMaster.BillNo.in_(keys)
                | OthersIncomeExpenseMaster.TallyBillNo.in_(keys),
            )
        ).first()
        if misc is not None:
            return misc_path
        return misc_path

    def converted_edit_message(self, inv: GstInvoice) -> str:
        path = self._origin_path(inv) or "Activities → Miscellaneous → Edit Entry"
        return (
            "This bill came from Convert to Invoice.\n\n"
            "Edit and delete it from this path:\n\n"
            + path
        )

    def update_workflow_flags(self, invoice_id: int, payload: dict) -> dict:
        inv = self.repo.get_by_id(invoice_id)
        if inv is None:
            raise ValueError("Invoice not found.")
        if self.normalize_bill_source(getattr(inv, "BillSource", None)) != self.BILL_SOURCE_MISCELLANEOUS:
            raise ValueError("Bill Status can be changed here only for a converted invoice.")
        self._guard_tally_status_change(inv, payload)
        inv.BillApproved = self._form_flag(payload, "bill_approved")
        inv.BillUnapproveReason = (payload.get("bill_unapprove_reason") or "").strip()[:500] or None
        inv.UpdatedAt = datetime.utcnow()
        db.session.commit()
        return self._serialize(inv)

    def find_invoice_for_tally_bill(self, bill_no: str) -> dict | None:
        inv = self.repo.find_by_tally_bill_no(bill_no)
        if inv is None:
            return None
        return {
            "invoice_id": inv.InvoiceID,
            "invoice_no": inv.InvoiceNo or "",
            "customer_name": inv.CustomerName or "",
        }

    def _assert_tally_bill_unique(
        self, bill_no: str | None, *, exclude_invoice_id: int | None = None
    ) -> None:
        key = (bill_no or "").strip()
        if not key:
            return
        existing = self.repo.find_by_tally_bill_no(key)
        if existing is None:
            return
        if exclude_invoice_id and existing.InvoiceID == exclude_invoice_id:
            return
        raise ValueError(
            f"Tally Bill Number {key} par invoice pehle se hai ({existing.InvoiceNo}). "
            "Duplicate allow nahi hai."
        )

    def _build_header_and_lines(
        self, payload: dict, *, persist_no: bool, require_payment_bank: bool = True
    ) -> tuple[dict, list[dict], dict]:
        self.repo.ensure_schema()
        self.item_repo.ensure_schema()

        inv_date_raw = (payload.get("invoice_date") or "").strip()
        try:
            inv_date = date.fromisoformat(inv_date_raw[:10]) if inv_date_raw else date.today()
        except ValueError:
            inv_date = date.today()

        customer_id = payload.get("customer_id")
        try:
            customer_id = int(customer_id) if customer_id not in (None, "") else None
        except (TypeError, ValueError):
            customer_id = None

        cust = self._load_customer(customer_id)
        customer_name = (
            (payload.get("customer_name") or "").strip()
            or cust.get("customer_name")
            or ""
        )
        if not customer_name:
            raise ValueError("Customer Name is required.")

        place = (payload.get("place_of_supply") or "").strip() or cust.get("place_of_supply") or ""
        place_code = (
            (payload.get("place_of_supply_code") or "").strip()
            or cust.get("place_of_supply_code")
            or self.state_code_from_name(place)
        )
        company = self.company_profile()
        seller_code = (company.get("state_code") or "05").strip()

        raw_lines = payload.get("lines") or []
        if isinstance(raw_lines, str):
            import json

            raw_lines = json.loads(raw_lines)
        if not raw_lines:
            raise ValueError("At least one invoice line is required.")

        invoice_kind = self.normalize_invoice_kind(
            payload.get("invoice_kind") or payload.get("InvoiceKind")
        )
        voucher_type = self.normalize_voucher_type(
            payload.get("voucher_type") or payload.get("VoucherType")
        )
        bill_source = self.normalize_bill_source(
            payload.get("bill_source") or payload.get("BillSource")
        )
        # Miscellaneous Generate Bill types the category amount as GST-inclusive.
        # 400 including 18% stays 400; taxable and CGST/SGST are extracted from it.
        rate_includes_gst = (
            bill_source == self.BILL_SOURCE_MISCELLANEOUS
            and voucher_type == self.VOUCHER_SALE
        )
        intra_state = bool(place_code) and place_code == seller_code

        lines_out: list[dict] = []
        list_price = Decimal("0.00")
        discount_total = Decimal("0.00")
        taxable_total = Decimal("0.00")
        gross_total = Decimal("0.00")
        gst_rate_used = Decimal("0.00")

        for i, raw in enumerate(raw_lines, start=1):
            item_id = raw.get("item_id")
            try:
                item_id = int(item_id) if item_id not in (None, "") else None
            except (TypeError, ValueError):
                item_id = None

            item = self.item_repo.get_by_id(item_id) if item_id else None
            particulars = (
                (raw.get("particulars") or "").strip()
                or (item.ItemName if item else "")
            )
            if not particulars:
                raise ValueError(f"Line {i}: Particulars are required.")

            hsn = (raw.get("hsn_sac") or "").strip() or (item.HsnSac if item else "") or ""
            unit = (raw.get("unit") or "").strip() or (item.Unit if item else "NOS") or "NOS"
            tax_period = (raw.get("tax_period") or raw.get("TaxPeriod") or "").strip() or None
            quarter = (raw.get("quarter") or raw.get("Quarter") or "").strip() or None
            month = (raw.get("month") or raw.get("Month") or "").strip() or None
            qty = self._qty(raw.get("qty"), "1")
            rate = self._money(raw.get("rate"), str(item.DefaultRate if item else "0"))
            discount = self._money(raw.get("discount_amount"))
            gst_rate = self._money(
                raw.get("gst_rate_percent"),
                str(item.GstRatePercent if item else "18"),
            )
            line_list = _q(qty * rate)
            if rate_includes_gst and gst_rate > 0:
                gross_line = _q(line_list - discount)
                if gross_line < 0:
                    raise ValueError(f"Line {i}: Discount cannot exceed amount.")
                split = self._split_gst_inclusive(gross_line, gst_rate, intra_state)
                taxable = split["taxable"]
                rate = _q(taxable / qty) if qty else taxable
                line_list = taxable
                gross_total += gross_line
            else:
                taxable = _q(line_list - discount)
                if taxable < 0:
                    raise ValueError(f"Line {i}: Discount cannot exceed amount.")
                gross_total += taxable

            list_price += line_list
            discount_total += discount
            taxable_total += taxable
            if gst_rate > gst_rate_used:
                gst_rate_used = gst_rate

            lines_out.append(
                {
                    "SrNo": i,
                    "ItemID": item_id,
                    "Particulars": particulars[:300],
                    "TaxPeriod": (tax_period[:20] if tax_period else None),
                    "Quarter": (quarter[:40] if quarter else None),
                    "Month": (month[:20] if month else None),
                    "HsnSac": hsn[:20] if hsn else None,
                    "Unit": unit[:30],
                    "Qty": qty,
                    "Rate": rate,
                    "DiscountAmount": discount,
                    "TaxableValue": taxable,
                    "GstRatePercent": gst_rate,
                }
            )

        if voucher_type == self.VOUCHER_PURCHASE and not inv_date_raw:
            raise ValueError("Invoice Date is required for Purchase.")

        # GST applies for both GST and Non-GST series; kind only controls invoice number format.
        cgst_rate = sgst_rate = igst_rate = Decimal("0.00")
        cgst_amt = sgst_amt = igst_amt = Decimal("0.00")
        if intra_state:
            tax_type = "CGST_SGST"
            cgst_rate = sgst_rate = _q(gst_rate_used / 2)
            cgst_amt = _q(taxable_total * cgst_rate / Decimal("100"))
            sgst_amt = _q(taxable_total * sgst_rate / Decimal("100"))
        else:
            tax_type = "IGST"
            igst_rate = gst_rate_used
            igst_amt = _q(taxable_total * igst_rate / Decimal("100"))

        invoice_value = _q(taxable_total + cgst_amt + sgst_amt + igst_amt)
        if rate_includes_gst and gst_rate_used > 0:
            round_off = _q(gross_total - invoice_value)
            invoice_value = _q(gross_total)
        else:
            round_off = self._parse_round_off(payload)
            invoice_value = _q(invoice_value + round_off)
        if invoice_value < 0:
            raise ValueError("Invoice Value cannot be negative after round off.")
        words = amount_in_words_inr(invoice_value)

        invoice_no = (payload.get("invoice_no") or "").strip()
        if voucher_type == self.VOUCHER_PURCHASE:
            if not invoice_no:
                raise ValueError("Supplier Invoice No is required for Purchase.")
        elif not invoice_no:
            invoice_no = self.next_invoice_no(inv_date, invoice_kind=invoice_kind)

        pay_bank_ids = self._payment_bank_ids(payload)
        bank_data = {
            "bank_name": "",
            "account_number": "",
            "ifsc_code": "",
            "branch_name": "",
            "account_holder_name": "",
            "account_type": "",
            "upi_id": "",
        }
        pay_banks: list[dict] = []
        if pay_bank_ids:
            import json

            bank_svc = BankMasterService()
            bank_svc.repo.ensure_schema()
            for pay_bank_id in pay_bank_ids:
                bank_row = bank_svc.repo.get_by_id(pay_bank_id)
                if bank_row is None or not bank_row.ActiveStatus:
                    raise ValueError("Selected payment bank account was not found or is inactive.")
                is_cash = bank_svc._is_cash_account(bank_row.BankName, bank_row.AccountNumber)
                if voucher_type != self.VOUCHER_PURCHASE and is_cash:
                    raise ValueError("Cash cannot be used as payment bank for invoice QR.")
                serialized = bank_svc._serialize(bank_row)
                upi = (serialized.get("upi_id") or "").strip()
                snap = {
                    "account_id": pay_bank_id,
                    "bank_name": serialized.get("bank_name") or "",
                    "account_number": serialized.get("account_number") or "",
                    "ifsc_code": serialized.get("ifsc_code") or "",
                    "branch_name": serialized.get("branch_name") or "",
                    "account_holder_name": serialized.get("account_holder_name") or "",
                    "account_type": serialized.get("account_type") or "",
                    "upi_id": upi,
                }
                pay_banks.append(snap)
            bank_data = {
                "bank_name": pay_banks[0]["bank_name"],
                "account_number": pay_banks[0]["account_number"],
                "ifsc_code": pay_banks[0]["ifsc_code"],
                "branch_name": pay_banks[0]["branch_name"],
                "account_holder_name": pay_banks[0]["account_holder_name"],
                "account_type": pay_banks[0]["account_type"],
                "upi_id": pay_banks[0]["upi_id"],
            }
            pay_bank_id = pay_banks[0]["account_id"]
            pay_banks_json = json.dumps(pay_banks)
        else:
            pay_bank_id = None
            pay_banks_json = None
            if require_payment_bank:
                raise ValueError("Payment Bank Account is required.")

        pay_date_raw = (payload.get("payment_date") or payload.get("PaymentDate") or "").strip()
        payment_date = None
        if voucher_type == self.VOUCHER_PURCHASE:
            if pay_date_raw:
                try:
                    payment_date = date.fromisoformat(pay_date_raw[:10])
                except ValueError as exc:
                    raise ValueError("Invalid Payment Date.") from exc
            else:
                payment_date = date.today()
        amount_paid = None
        if voucher_type == self.VOUCHER_PURCHASE:
            amount_paid_raw = payload.get("amount_paid")
            if amount_paid_raw in (None, ""):
                amount_paid_raw = payload.get("AmountPaid")
            if amount_paid_raw not in (None, ""):
                try:
                    amount_paid = _q(Decimal(str(amount_paid_raw)))
                except Exception as exc:
                    raise ValueError("Invalid Amount Paid.") from exc
                if amount_paid < 0:
                    raise ValueError("Amount Paid cannot be negative.")

        header = {
            "InvoiceNo": invoice_no
            if voucher_type == self.VOUCHER_PURCHASE
            else (invoice_no or self.next_invoice_no(inv_date, invoice_kind=invoice_kind)),
            "InvoiceDate": inv_date,
            "CustomerID": customer_id,
            "CustomerName": customer_name[:200],
            "ContactPerson": (
                (payload.get("contact_person") or "").strip()
                or cust.get("contact_person")
                or None
            ),
            "BillingAddress": (
                (payload.get("billing_address") or "").strip()
                or cust.get("billing_address")
                or None
            ),
            "CustomerGSTIN": (
                (payload.get("customer_gstin") or "").strip()
                or cust.get("customer_gstin")
                or None
            ),
            "ContactMobile": (
                (payload.get("contact_mobile") or "").strip()
                or cust.get("contact_mobile")
                or None
            ),
            "ContactEmail": (
                (payload.get("contact_email") or "").strip()
                or cust.get("contact_email")
                or None
            ),
            "PlaceOfSupply": place[:100] if place else None,
            "PlaceOfSupplyCode": place_code[:5] if place_code else None,
            "ReverseCharge": str(payload.get("reverse_charge")).lower()
            in {"1", "true", "yes", "on"},
            "InvoiceKind": invoice_kind,
            "VoucherType": voucher_type,
            "TaxType": tax_type,
            "ListPrice": list_price,
            "DiscountAmount": discount_total,
            "TaxableValue": taxable_total,
            "CgstRate": cgst_rate,
            "CgstAmount": cgst_amt,
            "SgstRate": sgst_rate,
            "SgstAmount": sgst_amt,
            "IgstRate": igst_rate,
            "IgstAmount": igst_amt,
            "InvoiceValue": invoice_value,
            "RoundOffAmount": round_off,
            "AmountInWords": words,
            "Notes": ((payload.get("notes") or "").strip() or None),
            "PaymentBankAccountID": pay_bank_id,
            "PayBankName": bank_data["bank_name"] or None,
            "PayAccountNumber": bank_data["account_number"] or None,
            "PayIFSC": bank_data["ifsc_code"] or None,
            "PayBranch": bank_data["branch_name"] or None,
            "PayAccountHolder": bank_data["account_holder_name"] or None,
            "PayAccountType": bank_data["account_type"] or None,
            "PayUpiId": bank_data["upi_id"] or None,
            "PayBankAccounts": pay_banks_json,
            "PaymentDate": payment_date,
            "AmountPaid": amount_paid,
            "TallyBillNo": self._normalized_tally_bill_no(
                payload.get("tally_bill_no") or payload.get("TallyBillNo")
            ),
            "BillSource": bill_source,
            **self._tally_status_header(payload, bill_source, voucher_type),
            "CreatedBy": (payload.get("created_by") or None),
            "CreatedAt": datetime.utcnow(),
        }

        preview = {
            "invoice_kind": invoice_kind,
            "voucher_type": voucher_type,
            "tax_type": tax_type,
            "list_price": float(list_price),
            "discount_amount": float(discount_total),
            "taxable_value": float(taxable_total),
            "cgst_rate": float(cgst_rate),
            "cgst_amount": float(cgst_amt),
            "sgst_rate": float(sgst_rate),
            "sgst_amount": float(sgst_amt),
            "igst_rate": float(igst_rate),
            "igst_amount": float(igst_amt),
            "invoice_value": float(invoice_value),
            "round_off": float(round_off),
            "round_off_amount": abs(float(round_off)),
            "round_off_sign": self._round_off_sign(round_off),
            "amount_in_words": words,
            "invoice_no": header["InvoiceNo"],
            "payment_bank_account_id": pay_bank_id,
            "pay_bank_name": bank_data["bank_name"],
            "pay_account_number": bank_data["account_number"],
            "pay_ifsc": bank_data["ifsc_code"],
            "pay_branch": bank_data["branch_name"],
            "pay_account_holder": bank_data["account_holder_name"],
            "pay_account_type": bank_data["account_type"],
            "pay_upi_id": bank_data["upi_id"],
            "payment_date": payment_date.isoformat() if payment_date else "",
            "amount_paid": float(amount_paid) if amount_paid is not None else None,
        }
        return header, lines_out, preview

    def _norm_ref(self, value) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _normalized_tally_bill_no(value) -> str | None:
        from app.utils.tally_bill import normalize_tally_bill_key

        key = normalize_tally_bill_key(str(value or ""))
        if not key:
            return None
        return key[:50]

    def _invoice_gst_amount(self, inv: GstInvoice) -> Decimal:
        return _q(
            Decimal(str(inv.CgstAmount or 0))
            + Decimal(str(inv.SgstAmount or 0))
            + Decimal(str(inv.IgstAmount or 0))
        )

    def _is_own_sale_daily(self, daily: JTCSDailyTransaction | None) -> bool:
        if daily is None:
            return False
        return (
            (daily.WorkType or "") == self.DAILY_WORK_TYPE
            and (daily.SubWorkType or "") == self.DAILY_SUB_WORK_TYPE
        )

    def _find_own_sale_daily(self, inv: GstInvoice) -> JTCSDailyTransaction | None:
        daily_id = getattr(inv, "DailyTransactionID", None)
        if daily_id:
            daily = db.session.get(JTCSDailyTransaction, int(daily_id))
            if self._is_own_sale_daily(daily):
                return daily
            inv.DailyTransactionID = None
        invoice_no = self._norm_ref(inv.InvoiceNo)
        if not invoice_no:
            return None
        return db.session.scalars(
            select(JTCSDailyTransaction)
            .where(JTCSDailyTransaction.WorkType == self.DAILY_WORK_TYPE)
            .where(JTCSDailyTransaction.SubWorkType == self.DAILY_SUB_WORK_TYPE)
            .where(JTCSDailyTransaction.ReferenceNo == invoice_no)
            .order_by(JTCSDailyTransaction.TransactionID.desc())
        ).first()

    def _followup_sale_daily(self, tally_bill_no: str | None, *, exclude_daily_id: int | None = None) -> JTCSDailyTransaction | None:
        bill_no = self._norm_ref(tally_bill_no)
        if not bill_no:
            return None
        stmt = (
            select(JTCSDailyTransaction)
            .where(JTCSDailyTransaction.Status == "Posted")
            .where(JTCSDailyTransaction.SaleAmount != 0)
            .where(JTCSDailyTransaction.ReferenceNo == bill_no)
            .where(
                (JTCSDailyTransaction.WorkType != self.DAILY_WORK_TYPE)
                | (JTCSDailyTransaction.SubWorkType != self.DAILY_SUB_WORK_TYPE)
            )
            .where(~JTCSDailyTransaction.SubWorkType.like("%Followup Receipt"))
            .order_by(JTCSDailyTransaction.TransactionID.desc())
        )
        if exclude_daily_id:
            stmt = stmt.where(JTCSDailyTransaction.TransactionID != int(exclude_daily_id))
        return db.session.scalars(stmt).first()

    def _tally_bill_already_in_sales(self, tally_bill_no: str | None, *, exclude_daily_id: int | None = None) -> bool:
        return self._followup_sale_daily(tally_bill_no, exclude_daily_id=exclude_daily_id) is not None

    def _strip_followup_sale(self, daily: JTCSDailyTransaction) -> None:
        """Remove the follow-up receivable. Keep the row only if it is a real receipt."""
        from app.services.payment_accounting_service import PaymentAccountingService

        module = (daily.WorkType or "").strip().upper()
        acct = PaymentAccountingService(module or None)
        if acct._is_combined_daily(daily) or acct._is_receipt_daily(daily):
            acct._zero_sale_keep_receipt(daily)
            db.session.flush()
            return
        acct._delete_daily(daily)

    def _remove_sale_daily(self, inv: GstInvoice) -> None:
        daily = self._find_own_sale_daily(inv)
        if daily is None:
            inv.DailyTransactionID = None
            return
        DailyTransactionRepository().delete(daily)
        inv.DailyTransactionID = None
        db.session.flush()

    def _sync_sale_daily(self, inv: GstInvoice) -> bool:
        """Post the Sale invoice as the customer receivable.

        Follow-up workflow dailies are not a second receivable. If one still
        carries SaleAmount for this Tally Bill Number, strip or remove it.
        """
        voucher = self.normalize_voucher_type(getattr(inv, "VoucherType", None))
        amount = _q(Decimal(str(inv.InvoiceValue or 0)))
        own = self._find_own_sale_daily(inv)
        if voucher != self.VOUCHER_SALE or amount == 0:
            if own is not None:
                self._remove_sale_daily(inv)
                return True
            return False
        exclude_id = own.TransactionID if own is not None else None
        while True:
            followup = self._followup_sale_daily(
                getattr(inv, "TallyBillNo", None),
                exclude_daily_id=exclude_id,
            )
            if followup is None:
                break
            self._strip_followup_sale(followup)

        gst_amount = self._invoice_gst_amount(inv)
        customer_name = (inv.CustomerName or "").strip() or None
        description = f"{self.DAILY_SUB_WORK_TYPE} — {inv.InvoiceNo}"
        if customer_name:
            description = f"{description} — {customer_name}"
        created_by = (inv.CreatedBy or "").strip() or "Sale Invoice"
        if own is not None:
            own.TransactionDate = inv.InvoiceDate
            own.WorkType = self.DAILY_WORK_TYPE
            own.SubWorkType = self.DAILY_SUB_WORK_TYPE
            own.CustomerID = inv.CustomerID
            own.CustomerName = customer_name
            own.ReferenceNo = self._norm_ref(inv.InvoiceNo)
            own.Description = description
            own.IncomeAmount = Decimal("0")
            own.ExpenseAmount = Decimal("0")
            own.SaleAmount = amount
            own.PurchaseAmount = Decimal("0")
            own.GSTAmount = gst_amount
            own.TotalAmount = amount
            own.Status = "Posted"
            own.ModifiedDate = datetime.utcnow()
            own.Remarks = self._norm_ref(getattr(inv, "TallyBillNo", None)) or None
            inv.DailyTransactionID = own.TransactionID
            db.session.flush()
            self._reconcile_payment_duplicates(inv)
            return True

        daily = DailyTransactionRepository().create(
            {
                "TransactionDate": inv.InvoiceDate,
                "WorkType": self.DAILY_WORK_TYPE,
                "SubWorkType": self.DAILY_SUB_WORK_TYPE,
                "CustomerID": inv.CustomerID,
                "CustomerName": customer_name,
                "ReferenceNo": self._norm_ref(inv.InvoiceNo),
                "Description": description,
                "IncomeAmount": Decimal("0"),
                "ExpenseAmount": Decimal("0"),
                "SaleAmount": amount,
                "PurchaseAmount": Decimal("0"),
                "GSTAmount": gst_amount,
                "TDSAmount": Decimal("0"),
                "TotalAmount": amount,
                "PaymentSplitCount": 1,
                "Status": "Posted",
                "CreatedBy": created_by,
                "CreatedDate": datetime.utcnow(),
                "Remarks": self._norm_ref(getattr(inv, "TallyBillNo", None)) or None,
            }
        )
        inv.DailyTransactionID = daily.TransactionID
        db.session.flush()
        self._reconcile_payment_duplicates(inv)
        return True

    def _reconcile_payment_duplicates(self, inv: GstInvoice) -> None:
        tally = self._norm_ref(getattr(inv, "TallyBillNo", None))
        if not tally:
            return
        from app.services.payment_accounting_service import PaymentAccountingService

        module = None
        try:
            from app.models.followup import FollowupEntryMaster

            entry = db.session.scalars(
                select(FollowupEntryMaster)
                .where(FollowupEntryMaster.BillNo == tally)
                .order_by(FollowupEntryMaster.EntryID.desc())
            ).first()
            if entry is not None:
                module = (entry.ModuleCode or "").strip().upper() or None
        except Exception:
            module = None
        PaymentAccountingService(module).reconcile_reference(tally)

    def ensure_sale_invoices_posted(self) -> int:
        """Backfill Sale invoices that are not yet in daily sales totals."""
        self.repo.ensure_schema()
        today = date.today()
        invoice_ids = db.session.execute(
            text(
                """
                SELECT i.InvoiceID
                FROM dbo.GstInvoice i
                WHERE ISNULL(i.VoucherType, N'SALE') = N'SALE'
                  AND ISNULL(i.InvoiceValue, 0) <> 0
                  AND i.DailyTransactionID IS NULL
                  AND (
                        i.InvoiceDate = :today
                        OR ISNULL(i.CreatedBy, N'') <> N'DayBook Import'
                  )
                  AND NOT EXISTS (
                        SELECT 1
                        FROM dbo.JTCSDailyTransaction d
                        WHERE d.Status = N'Posted'
                          AND d.WorkType = N'Accounting'
                          AND d.SubWorkType = N'Sale / Service Invoice'
                          AND UPPER(LTRIM(RTRIM(ISNULL(d.ReferenceNo, N''))))
                              = UPPER(LTRIM(RTRIM(ISNULL(i.InvoiceNo, N''))))
                  )
                """
            ),
            {"today": today},
        ).scalars().all()
        posted = 0
        for invoice_id in invoice_ids:
            inv = self.repo.get_by_id(int(invoice_id))
            if inv is None:
                continue
            if self._sync_sale_daily(inv):
                posted += 1
        if posted:
            db.session.commit()
        return posted

    def _list_purchase_payment_bank_rows(self, invoice_id: int) -> list:
        """Bank legs posted only by Purchase Invoice Amount Paid (SourceTable=GstInvoice)."""
        from app.models.transactions import JtcsBankTransaction

        iid = int(invoice_id)
        stmt = (
            select(JtcsBankTransaction)
            .where(JtcsBankTransaction.SourceTable == self.PURCHASE_BANK_SOURCE_TABLE)
            .where(JtcsBankTransaction.SourceRecordID == iid)
            .where(JtcsBankTransaction.SourceType == self.PURCHASE_BANK_SOURCE_TYPE)
            .order_by(JtcsBankTransaction.JtcsBankTransactionID.asc())
        )
        return list(db.session.scalars(stmt).all())

    def _remove_purchase_payment_bank(self, inv: GstInvoice) -> None:
        """Strict: remove purchase payment bank legs only; never touches Sale / other modules."""
        voucher = self.normalize_voucher_type(getattr(inv, "VoucherType", None))
        if voucher != self.VOUCHER_PURCHASE:
            return
        bank_repo = BankTransactionRepository()
        for row in self._list_purchase_payment_bank_rows(inv.InvoiceID):
            bank_repo.delete(row)
        db.session.flush()

    def _sync_purchase_payment_bank(self, inv: GstInvoice) -> bool:
        """Post Amount Paid as Credit (Out) on the selected payment bank — PURCHASE only."""
        voucher = self.normalize_voucher_type(getattr(inv, "VoucherType", None))
        if voucher != self.VOUCHER_PURCHASE:
            return False

        amount = _q(Decimal(str(getattr(inv, "AmountPaid", None) or 0)))
        bank_account_id = getattr(inv, "PaymentBankAccountID", None)
        try:
            bank_account_id = int(bank_account_id) if bank_account_id not in (None, "") else None
        except (TypeError, ValueError):
            bank_account_id = None

        existing = self._list_purchase_payment_bank_rows(inv.InvoiceID)
        if amount <= 0 or not bank_account_id:
            if existing:
                self._remove_purchase_payment_bank(inv)
                return True
            return False

        master = MasterRepository()
        bank_snap = master.resolve_bank_account_by_id(bank_account_id)
        pay_mode_id = master.resolve_payment_mode_for_bank_account(bank_account_id)
        txn_date = getattr(inv, "PaymentDate", None) or inv.InvoiceDate
        supplier = (inv.CustomerName or "").strip() or "Supplier"
        invoice_no = (inv.InvoiceNo or "").strip()
        description = self.PURCHASE_BANK_DESCRIPTION
        remarks = f"{invoice_no} — {supplier}"[:200]
        created_by = (inv.CreatedBy or "").strip() or "Purchase Invoice"
        bank_repo = BankTransactionRepository()

        payload = {
            "JtcsBankAccountID": bank_snap.account_id or 0,
            "BankName": bank_snap.bank_name,
            "MaskedAccountNumber": bank_snap.masked_account_number,
            "TransactionDate": txn_date,
            "Description": description,
            "Debit": None,
            "Credit": amount,
            "ClosingBalance": Decimal("0"),
            "ImportedBy": created_by,
            "ImportedDate": datetime.utcnow(),
            "Remarks": remarks,
            "IsLocked": False,
            "SourceTable": self.PURCHASE_BANK_SOURCE_TABLE,
            "SourceRecordID": inv.InvoiceID,
            "SourceType": self.PURCHASE_BANK_SOURCE_TYPE,
            "SourceID": inv.InvoiceID,
            "LedgerKind": "PAYMENT",
            "PaymentModeID": pay_mode_id,
            "PaymentSequence": 1,
        }

        if existing:
            row = existing[0]
            for key, value in payload.items():
                if key in {"ImportedBy", "ImportedDate"}:
                    continue
                setattr(row, key, value)
            for extra in existing[1:]:
                bank_repo.delete(extra)
            db.session.flush()
        else:
            bank_repo.create(payload)
        return True

    def create_record(
        self,
        payload: dict,
        *,
        created_by: str | None = None,
        commit: bool = True,
        require_payment_bank: bool | None = None,
    ) -> dict:
        if created_by:
            payload = {**payload, "created_by": created_by}
        bill_source = self.normalize_bill_source(
            payload.get("bill_source") or payload.get("BillSource")
        )
        if require_payment_bank is None:
            # Sale invoices (incl. Misc / Manual) no longer require payment bank.
            # Purchase still opts in via caller when needed.
            require_payment_bank = False
        header, lines, _ = self._build_header_and_lines(
            payload, persist_no=True, require_payment_bank=require_payment_bank
        )
        header["BillSource"] = bill_source
        tally_key = header.get("TallyBillNo")
        existing = self.repo.find_by_tally_bill_no(tally_key) if tally_key else None
        if existing is not None:
            existing_source = self.normalize_bill_source(getattr(existing, "BillSource", None))
            if existing_source in {
                self.BILL_SOURCE_AUTOMATIC,
                self.BILL_SOURCE_MISCELLANEOUS,
            }:
                upgrade_payload = {
                    **payload,
                    "tally_bill_no": tally_key,
                    "bill_source": bill_source
                    if bill_source != self.BILL_SOURCE_MANUAL
                    else (
                        self.BILL_SOURCE_MISCELLANEOUS
                        if existing_source == self.BILL_SOURCE_MISCELLANEOUS
                        else self.BILL_SOURCE_MANUAL
                    ),
                }
                # Keep outer caller transaction (e.g. OIE save) — never nested persist.
                return self.update_record(
                    existing.InvoiceID, upgrade_payload, commit=commit
                )
            self._assert_tally_bill_unique(tally_key)

        def _write() -> dict:
            inv = self.repo.create(header, lines)
            self._sync_sale_daily(inv)
            self._sync_purchase_payment_bank(inv)
            return self._serialize(inv)

        if commit:
            return persist(_write)
        return _write()

    def update_record(
        self, invoice_id: int, payload: dict, *, commit: bool = True
    ) -> dict:
        inv = self.repo.get_by_id(invoice_id)
        if inv is None:
            raise ValueError("Invoice not found.")
        existing_source = self.normalize_bill_source(
            getattr(inv, "BillSource", None) or self.BILL_SOURCE_MANUAL
        )
        if existing_source == self.BILL_SOURCE_MISCELLANEOUS and not self._form_flag(
            payload, "from_source"
        ):
            raise ValueError(self.converted_edit_message(inv))
        if "bill_source" not in payload and "BillSource" not in payload:
            payload = {**payload, "bill_source": existing_source}
        bill_source = self.normalize_bill_source(
            payload.get("bill_source") or payload.get("BillSource")
        )
        payload = {**payload, "invoice_no": inv.InvoiceNo, "bill_source": bill_source}
        self._guard_tally_status_change(inv, payload)
        # Sale invoices do not require payment bank (legacy Manual bank rule removed).
        header, lines, _ = self._build_header_and_lines(
            payload, persist_no=False, require_payment_bank=False
        )
        self._assert_tally_bill_unique(header.get("TallyBillNo"), exclude_invoice_id=invoice_id)
        header["UpdatedAt"] = datetime.utcnow()
        header.pop("CreatedAt", None)
        header.pop("CreatedBy", None)

        def _write() -> dict:
            updated = self.repo.update(inv, header, lines)
            self._sync_sale_daily(updated)
            self._sync_purchase_payment_bank(updated)
            self._sync_misc_payment_received(updated)
            return self._serialize(updated)

        if commit:
            return persist(_write)
        return _write()

    def ensure_automatic_invoice(
        self,
        *,
        tally_bill_no: str,
        customer_name: str,
        bill_amount,
        invoice_date: date | None = None,
        customer_id: int | None = None,
        contact_mobile: str | None = None,
        place_of_supply: str | None = None,
        notes: str | None = None,
        particulars: str | None = None,
        created_by: str | None = None,
        commit: bool = True,
    ) -> dict | None:
        """Deprecated no-op — Sale invoices are created from Miscellaneous Generate Bill."""
        return None

    def backfill_automatic_invoices(self, *, limit: int = 40) -> int:
        """Deprecated no-op — Automatic backfill disabled."""
        return 0

    def _list_paid_bills_missing_invoice(self, *, limit: int = 40) -> list[dict]:
        """Legacy helper (unused). Kept for reference only."""
        return []

    def list_ids(self) -> list[int]:
        return self.repo.list_ids()

    def navigate(self, *, current_id: int | None, direction: str) -> dict:
        ids = self.list_ids()
        if not ids:
            raise ValueError("No invoices found.")
        direction = (direction or "").strip().lower()
        if direction in {"top", "first"}:
            target = ids[0]
        elif direction in {"bottom", "last"}:
            target = ids[-1]
        elif direction in {"prior", "prev", "previous"}:
            if current_id is None:
                target = ids[-1]
            else:
                try:
                    idx = ids.index(int(current_id))
                except ValueError:
                    target = ids[-1]
                else:
                    if idx <= 0:
                        raise ValueError("Already at first invoice.")
                    target = ids[idx - 1]
        elif direction in {"next"}:
            if current_id is None:
                target = ids[0]
            else:
                try:
                    idx = ids.index(int(current_id))
                except ValueError:
                    target = ids[0]
                else:
                    if idx >= len(ids) - 1:
                        raise ValueError("Already at last invoice.")
                    target = ids[idx + 1]
        else:
            raise ValueError("Invalid navigation direction.")
        record = self.get_record(target)
        pos = ids.index(target) + 1
        return {
            "record": record,
            "position": pos,
            "total": len(ids),
            "has_prior": pos > 1,
            "has_next": pos < len(ids),
        }

    def delete_invoices_for_bill_if_any(self, bill_no: str) -> int:
        """Delete linked sale invoices. Returns 0 when this bill has none."""
        ids = self.repo.list_ids_for_bill_no(bill_no)
        for invoice_id in ids:
            self.delete_record(invoice_id)
        return len(ids)

    def delete_invoices_for_bill(self, bill_no: str) -> int:
        """Permanently delete every sale invoice linked to this bill number."""
        count = self.delete_invoices_for_bill_if_any(bill_no)
        if not count:
            raise ValueError("No invoice is linked to this bill.")
        return count

    def delete_record(self, invoice_id: int) -> str:
        inv = self.repo.get_by_id(invoice_id)
        if inv is None:
            raise ValueError("Invoice not found.")

        def _write() -> str:
            self._remove_sale_daily(inv)
            self._remove_purchase_payment_bank(inv)
            self.repo.delete(inv)
            return "Invoice deleted successfully."

        return persist(_write)
