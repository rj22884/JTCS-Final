from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from flask import current_app
from sqlalchemy import select, text

from app.extensions import db
from app.models.gst_billing import GstInvoice
from app.models.transactions import JTCSDailyTransaction
from app.repositories.gst_invoice_repository import GstInvoiceRepository
from app.repositories.item_master_repository import ItemMasterRepository
from app.repositories.transaction_repository import DailyTransactionRepository
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
    def line_particulars_parts(cls, line: dict) -> tuple[str, str]:
        """Item name on the first line; tax year / quarter / month / notes in brackets."""
        item_name = cls._line_text(line.get("item_name"), line.get("ItemName"))
        particulars = cls._line_text(line.get("particulars"), line.get("Particulars"))
        tax_period = cls._line_text(line.get("tax_period"), line.get("TaxPeriod"))
        quarter = cls._line_text(line.get("quarter"), line.get("Quarter"))
        month = cls._line_text(line.get("month"), line.get("Month"))
        main = item_name or particulars or "—"
        extras: list[str] = []
        if tax_period:
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
        return {
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
            "created_at": inv.CreatedAt.isoformat() if inv.CreatedAt else "",
            "lines": self._serialize_lines(lines),
        }

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
        return self._serialize(inv)

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

        lines_out: list[dict] = []
        list_price = Decimal("0.00")
        discount_total = Decimal("0.00")
        taxable_total = Decimal("0.00")
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
            taxable = _q(line_list - discount)
            if taxable < 0:
                raise ValueError(f"Line {i}: Discount cannot exceed amount.")

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

        invoice_kind = self.normalize_invoice_kind(
            payload.get("invoice_kind") or payload.get("InvoiceKind")
        )
        voucher_type = self.normalize_voucher_type(
            payload.get("voucher_type") or payload.get("VoucherType")
        )
        if voucher_type == self.VOUCHER_PURCHASE and not inv_date_raw:
            raise ValueError("Invoice Date is required for Purchase.")

        # GST applies for both GST and Non-GST series; kind only controls invoice number format.
        intra_state = bool(place_code) and place_code == seller_code
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

        pay_bank_id_raw = payload.get("payment_bank_account_id") or payload.get(
            "PaymentBankAccountID"
        )
        try:
            pay_bank_id = int(pay_bank_id_raw) if pay_bank_id_raw not in (None, "") else None
        except (TypeError, ValueError):
            pay_bank_id = None
        bank_data = {
            "bank_name": "",
            "account_number": "",
            "ifsc_code": "",
            "branch_name": "",
            "account_holder_name": "",
            "account_type": "",
            "upi_id": "",
        }
        if pay_bank_id:
            bank_svc = BankMasterService()
            bank_svc.repo.ensure_schema()
            bank_row = bank_svc.repo.get_by_id(pay_bank_id)
            if bank_row is None or not bank_row.ActiveStatus:
                raise ValueError("Selected payment bank account was not found or is inactive.")
            is_cash = bank_svc._is_cash_account(bank_row.BankName, bank_row.AccountNumber)
            if voucher_type != self.VOUCHER_PURCHASE and is_cash:
                raise ValueError("Cash cannot be used as payment bank for invoice QR.")
            bank_data = bank_svc._serialize(bank_row)
            if voucher_type != self.VOUCHER_PURCHASE and not bank_data.get("qr_bill_received"):
                raise ValueError(
                    "Selected payment bank is not marked QR/Bill Received in Bank Master."
                )
        elif require_payment_bank:
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
            "PaymentDate": payment_date,
            "AmountPaid": amount_paid,
            "TallyBillNo": (
                (payload.get("tally_bill_no") or payload.get("TallyBillNo") or "").strip()[:50]
                or None
            ),
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

    def _invoice_gst_amount(self, inv: GstInvoice) -> Decimal:
        return _q(
            Decimal(str(inv.CgstAmount or 0))
            + Decimal(str(inv.SgstAmount or 0))
            + Decimal(str(inv.IgstAmount or 0))
        )

    def _find_own_sale_daily(self, inv: GstInvoice) -> JTCSDailyTransaction | None:
        daily_id = getattr(inv, "DailyTransactionID", None)
        if daily_id:
            daily = db.session.get(JTCSDailyTransaction, int(daily_id))
            if daily is not None:
                return daily
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
            .order_by(JTCSDailyTransaction.TransactionID.desc())
        )
        if exclude_daily_id:
            stmt = stmt.where(JTCSDailyTransaction.TransactionID != int(exclude_daily_id))
        return db.session.scalars(stmt).first()

    def _tally_bill_already_in_sales(self, tally_bill_no: str | None, *, exclude_daily_id: int | None = None) -> bool:
        return self._followup_sale_daily(tally_bill_no, exclude_daily_id=exclude_daily_id) is not None

    def _strip_followup_sale(self, daily: JTCSDailyTransaction) -> None:
        """Keep the followup row, but stop counting it as Sale so the invoice date wins."""
        sale = _q(Decimal(str(daily.SaleAmount or 0)))
        if sale == 0:
            return
        total = _q(Decimal(str(daily.TotalAmount or 0)))
        daily.SaleAmount = Decimal("0.00")
        remaining = total - sale
        daily.TotalAmount = remaining if remaining > 0 else Decimal("0.00")
        daily.ModifiedDate = datetime.utcnow()
        db.session.flush()

    def _remove_sale_daily(self, inv: GstInvoice) -> None:
        daily = self._find_own_sale_daily(inv)
        if daily is None:
            inv.DailyTransactionID = None
            return
        DailyTransactionRepository().delete(daily)
        inv.DailyTransactionID = None
        db.session.flush()

    def _sync_sale_daily(self, inv: GstInvoice) -> bool:
        """Post Sale invoice into JTCSDailyTransaction so dashboard sales cards pick it up.

        Existing SaleAmount rows (followup / stamp / etc.) stay as-is. If this invoice
        is already counted via Tally Bill Number, do not add a second row.
        """
        voucher = self.normalize_voucher_type(getattr(inv, "VoucherType", None))
        amount = _q(Decimal(str(inv.InvoiceValue or 0)))
        own = self._find_own_sale_daily(inv)
        if voucher != self.VOUCHER_SALE or amount == 0:
            if own is not None:
                self._remove_sale_daily(inv)
                return True
            return False
        followup = self._followup_sale_daily(
            getattr(inv, "TallyBillNo", None),
            exclude_daily_id=own.TransactionID if own is not None else None,
        )
        if followup is not None and followup.TransactionDate == inv.InvoiceDate:
            # Already in sales cards on this invoice date — do not double-count.
            return False
        if followup is not None:
            # Same bill was posted on followup date; move Sale to invoice date.
            self._strip_followup_sale(followup)

        gst_amount = self._invoice_gst_amount(inv)
        customer_name = (inv.CustomerName or "").strip() or None
        description = f"{self.DAILY_SUB_WORK_TYPE} — {inv.InvoiceNo}"
        if customer_name:
            description = f"{description} — {customer_name}"
        created_by = (inv.CreatedBy or "").strip() or "Sale Invoice"
        if own is not None:
            own.TransactionDate = inv.InvoiceDate
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
        return True

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
                          AND ISNULL(d.SaleAmount, 0) <> 0
                          AND d.TransactionDate = i.InvoiceDate
                          AND UPPER(LTRIM(RTRIM(ISNULL(d.ReferenceNo, N''))))
                              = UPPER(LTRIM(RTRIM(ISNULL(i.TallyBillNo, N''))))
                          AND NULLIF(LTRIM(RTRIM(ISNULL(i.TallyBillNo, N''))), N'') IS NOT NULL
                          AND NOT (
                                d.WorkType = N'Accounting'
                                AND d.SubWorkType = N'Sale / Service Invoice'
                          )
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

    def create_record(self, payload: dict, *, created_by: str | None = None) -> dict:
        if created_by:
            payload = {**payload, "created_by": created_by}
        header, lines, _ = self._build_header_and_lines(payload, persist_no=True)
        self._assert_tally_bill_unique(header.get("TallyBillNo"))

        def _write() -> dict:
            inv = self.repo.create(header, lines)
            self._sync_sale_daily(inv)
            return self._serialize(inv)

        return persist(_write)

    def update_record(self, invoice_id: int, payload: dict) -> dict:
        inv = self.repo.get_by_id(invoice_id)
        if inv is None:
            raise ValueError("Invoice not found.")
        payload = {**payload, "invoice_no": inv.InvoiceNo}
        header, lines, _ = self._build_header_and_lines(payload, persist_no=False)
        self._assert_tally_bill_unique(header.get("TallyBillNo"), exclude_invoice_id=invoice_id)
        header["UpdatedAt"] = datetime.utcnow()
        header.pop("CreatedAt", None)
        header.pop("CreatedBy", None)

        def _write() -> dict:
            updated = self.repo.update(inv, header, lines)
            self._sync_sale_daily(updated)
            return self._serialize(updated)

        return persist(_write)

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

    def delete_record(self, invoice_id: int) -> str:
        inv = self.repo.get_by_id(invoice_id)
        if inv is None:
            raise ValueError("Invoice not found.")

        def _write() -> str:
            self._remove_sale_daily(inv)
            self.repo.delete(inv)
            return "Invoice deleted successfully."

        return persist(_write)
