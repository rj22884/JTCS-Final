"""Create Misc Activity + Sale invoice for Document Print jobs (Daily Customer)."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select, text

from app.extensions import db
from app.models.others import OthersIncomeExpenseMaster
from app.repositories.customer_repository import CustomerRepository
from app.repositories.others_repository import WorkMasterRepository
from app.services.gst_invoice_service import GstInvoiceService
from app.services.others_income_expense_service import OthersIncomeExpenseService
from app.utils.db_session import persist


PRINT_TAG_RE = re.compile(r"\[PRINT:([A-Z0-9\-]+)\]", re.IGNORECASE)
DEFAULT_CUSTOMER_NAME = "Daily Customer"
DEFAULT_WORK_NAME = "Document Print"
DEFAULT_PLACE = "UTTARAKHAND"
DEFAULT_PLACE_CODE = "05"
DEFAULT_PURPOSE = "Customer Paid"
DEFAULT_UPI_VPA = "rajn8755396@barodampay"


class PrintJobBillingService:
    def __init__(self) -> None:
        self.oie = OthersIncomeExpenseService()
        self.gst = GstInvoiceService()
        self.customers = CustomerRepository()
        self.works = WorkMasterRepository()

    def _ensure_purpose_customer_paid(self) -> str:
        from app.services.purpose_master_service import PurposeMasterService

        svc = PurposeMasterService()
        want = DEFAULT_PURPOSE.casefold()
        for row in svc.list_records(active_only=False):
            name = (row.get("purpose_name") or "").strip()
            if name.casefold() == want:
                if not row.get("active_status"):
                    svc.update_record(
                        int(row["purpose_id"]),
                        {
                            "PurposeName": name,
                            "Description": row.get("description") or "Document Print UPI receipt",
                            "ActiveStatus": "1",
                        },
                    )
                return name
        created = svc.create_record(
            {
                "PurposeName": DEFAULT_PURPOSE,
                "Description": "Document Print UPI receipt (auto)",
                "ActiveStatus": "1",
            },
            created_by="Print App",
        )
        return (created.get("purpose_name") or DEFAULT_PURPOSE).strip()

    def _resolve_upi_bank_account_id(self, upi_vpa: str | None) -> int:
        from app.services.bank_master_service import BankMasterService

        target = (upi_vpa or DEFAULT_UPI_VPA).strip().casefold()
        if not target:
            raise ValueError("UPI VPA is required to tag Money In account.")
        banks = BankMasterService().list_payment_accounts(qr_bill_received_only=False)
        # Prefer exact UPI match on QR-enabled accounts, then any UPI match.
        qr_hits = [
            b
            for b in banks
            if (b.get("upi_id") or "").strip().casefold() == target and b.get("qr_bill_received")
        ]
        if qr_hits:
            return int(qr_hits[0]["account_id"])
        hits = [
            b for b in banks if (b.get("upi_id") or "").strip().casefold() == target
        ]
        if hits:
            return int(hits[0]["account_id"])
        raise ValueError(
            f'Bank Master me UPI "{upi_vpa or DEFAULT_UPI_VPA}" wala account nahi mila. '
            "Masters → Bank Account me UPI ID set karein."
        )

    def _post_money_inout(
        self,
        *,
        work_date: date,
        amount: Decimal,
        customer_id: int,
        invoice_id: int,
        upi_vpa: str | None,
        remarks: str,
    ) -> dict:
        from app.services.others_bank_cash_service import OthersBankCashService

        purpose = self._ensure_purpose_customer_paid()
        bank_id = self._resolve_upi_bank_account_id(upi_vpa)
        obc = OthersBankCashService()
        credit_key = obc._customer_ledger_key(customer_id) or f"customer-{int(customer_id)}"
        result = obc.save_entry(
            {
                "WorkDate": work_date.isoformat(),
                "Purpose": purpose,
                "CreditLedgerKey": credit_key,
                "DebitLedgerKey": f"bank-{bank_id}",
                "Amount": str(amount),
                "Remarks": remarks[:500],
                "InvoiceMode": "selected",
                "InvoiceIDs": str(int(invoice_id)),
                "CustomerID": str(int(customer_id)),
            },
            created_by="Print App",
        )
        return {
            "money_entry_id": result.entry_id,
            "money_voucher_no": result.voucher_no,
            "purpose": purpose,
            "bank_account_id": bank_id,
            "credit_ledger_key": credit_key,
        }

    @staticmethod
    def _money(value) -> Decimal:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Valid amount is required.") from exc
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")
        return amount.quantize(Decimal("0.01"))

    @staticmethod
    def _tag(public_id: str) -> str:
        return f"[PRINT:{public_id.strip().upper()}]"

    def _find_existing(self, public_id: str) -> OthersIncomeExpenseMaster | None:
        tag = self._tag(public_id)
        rows = db.session.scalars(
            select(OthersIncomeExpenseMaster)
            .where(
                OthersIncomeExpenseMaster.IsActive == True,  # noqa: E712
                OthersIncomeExpenseMaster.Remarks.like(f"%{tag}%"),
            )
            .order_by(OthersIncomeExpenseMaster.EntryID.desc())
        ).all()
        for row in rows:
            match = PRINT_TAG_RE.search(row.Remarks or "")
            if match and match.group(1).upper() == public_id.strip().upper():
                return row
        return None

    def _resolve_daily_customer(self) -> dict:
        self.customers.ensure_schema()
        row = self.customers.session.execute(
            text(
                """
                SELECT TOP 1 CustomerID, CustomerName, MobileNumber,
                       ISNULL(State, '') AS State
                FROM dbo.CustomerMaster
                WHERE UPPER(LTRIM(RTRIM(CustomerName))) = UPPER(:name)
                  AND CustomerStatus <> N'Inactive'
                ORDER BY CustomerID
                """
            ),
            {"name": DEFAULT_CUSTOMER_NAME},
        ).mappings().first()
        if not row:
            raise ValueError(
                f'Customer "{DEFAULT_CUSTOMER_NAME}" not found in Customer Master.'
            )
        return {
            "customer_id": int(row["CustomerID"]),
            "customer_name": (row["CustomerName"] or DEFAULT_CUSTOMER_NAME).strip(),
            "mobile": (row["MobileNumber"] or "").strip(),
            "state": (row["State"] or "").strip(),
            "matched_by": "daily_customer",
            "match_count": 0,
        }

    def _resolve_billing_customer(self, mobile: str | None) -> dict:
        """Prefer Customer Master row(s) for print mobile; else Daily Customer."""
        self.customers.ensure_schema()
        normalized = self.customers._normalize_mobile(mobile or "")
        if normalized:
            rows = self.customers.session.execute(
                text(
                    """
                    SELECT CustomerID, CustomerName, MobileNumber,
                           ISNULL(State, '') AS State
                    FROM dbo.CustomerMaster
                    WHERE MobileNumber = :mobile
                      AND CustomerStatus <> N'Inactive'
                    ORDER BY CustomerID
                    """
                ),
                {"mobile": normalized},
            ).mappings().all()
            if rows:
                row = rows[0]
                return {
                    "customer_id": int(row["CustomerID"]),
                    "customer_name": (row["CustomerName"] or "").strip()
                    or DEFAULT_CUSTOMER_NAME,
                    "mobile": (row["MobileNumber"] or normalized).strip(),
                    "state": (row["State"] or "").strip(),
                    "matched_by": "mobile",
                    "match_count": len(rows),
                }
        return self._resolve_daily_customer()

    @staticmethod
    def extract_print_public_id(*texts: str | None) -> str | None:
        for text_val in texts:
            if not text_val:
                continue
            match = PRINT_TAG_RE.search(str(text_val))
            if match:
                return match.group(1).upper()
        return None

    @staticmethod
    def ui_delete_blocked_message(public_id: str) -> str:
        pid = (public_id or "").strip().upper() or "JTCS-P-XXXXXX"
        return (
            f"Ye entry print.ukdscwala.com se aayi hai — yahan se delete nahi hogi. "
            f"Path: https://print.ukdscwala.com/admin/jobs/{pid} "
            f"Wahan se delete karne par Misc + Invoice + Money In/Out yahan se bhi delete ho jayenge."
        )

    def assert_ui_delete_allowed(self, *texts: str | None) -> None:
        """Block ERP UI deletes for print-origin rows; Print app API bypasses this."""
        public_id = self.extract_print_public_id(*texts)
        if public_id:
            raise ValueError(self.ui_delete_blocked_message(public_id))

    def _ensure_work(self) -> tuple[int, int | None]:
        self.works.ensure_schema()
        work = self.works.find_by_name_kind(DEFAULT_WORK_NAME, "Misc.")
        if work is None or not work.ActiveStatus:

            def _create() -> int:
                existing = self.works.find_by_name_kind(DEFAULT_WORK_NAME, "Misc.")
                if existing is not None:
                    if not existing.ActiveStatus:
                        existing.ActiveStatus = True
                        db.session.flush()
                    return int(existing.WorkID)
                row = self.works.create(
                    {
                        "WorkName": DEFAULT_WORK_NAME,
                        "LedgerKind": "Misc.",
                        "ActiveStatus": True,
                    }
                )
                return int(row.WorkID)

            work_id = persist(_create)
            work = self.works.get_by_id(work_id)
        if work is None:
            raise ValueError(f'Work category "{DEFAULT_WORK_NAME}" could not be created.')
        work_type_id = None
        subs = self.oie.master_repo.list_sub_works_for_parent(work.WorkName)
        if subs:
            work_type_id = int(subs[0].WorkTypeID)
        return int(work.WorkID), work_type_id

    def _invoice_for_entry(self, entry: OthersIncomeExpenseMaster):
        return self.gst.repo.find_by_misc_entries([int(entry.EntryID)]).get(int(entry.EntryID))

    def _money_allocation_exists(self, invoice_id: int) -> bool:
        from app.models.bank_cash import OthersBankCashInvoiceAllocation

        row = db.session.scalars(
            select(OthersBankCashInvoiceAllocation)
            .where(OthersBankCashInvoiceAllocation.InvoiceID == int(invoice_id))
            .limit(1)
        ).first()
        return row is not None

    def _ensure_money_for_existing(
        self,
        entry: OthersIncomeExpenseMaster,
        inv,
        *,
        upi_vpa: str | None = None,
    ) -> dict | None:
        if inv is None:
            return None
        invoice_id = int(inv.InvoiceID)
        if self._money_allocation_exists(invoice_id):
            return None
        customer_id = int(getattr(entry, "CustomerID", 0) or getattr(inv, "CustomerID", 0) or 0)
        amount_raw = getattr(inv, "InvoiceValue", None) or getattr(entry, "Amount", None) or 0
        work_date = getattr(inv, "InvoiceDate", None) or getattr(entry, "WorkDate", None) or date.today()
        remarks = (getattr(entry, "Remarks", None) or f"[PRINT] invoice {inv.InvoiceNo}")[:500]
        invoice_no = inv.InvoiceNo
        if customer_id <= 0:
            customer = self._resolve_daily_customer()
            customer_id = int(customer["customer_id"])
        amount = self._money(amount_raw)
        return self._post_money_inout(
            work_date=work_date if isinstance(work_date, date) else date.today(),
            amount=amount,
            customer_id=customer_id,
            invoice_id=invoice_id,
            upi_vpa=upi_vpa,
            remarks=remarks or f"[PRINT] invoice {invoice_no}",
        )

    def _serialize_existing(
        self,
        entry: OthersIncomeExpenseMaster,
        *,
        upi_vpa: str | None = None,
        ensure_money: bool = False,
    ) -> dict:
        inv = self._invoice_for_entry(entry)
        # Capture scalars before Money In/Out persist expires the ORM row.
        entry_id = int(entry.EntryID)
        misc_bill_no = entry.BillNo
        customer_name = entry.CustomerName or DEFAULT_CUSTOMER_NAME
        amount_val = float(entry.Amount or 0)
        tally_fallback = entry.TallyBillNo
        invoice_id = int(inv.InvoiceID) if inv else None
        invoice_no = (inv.InvoiceNo if inv else None) or tally_fallback
        bill_approved = bool(getattr(inv, "BillApproved", False)) if inv else False
        money = None
        if ensure_money:
            money = self._ensure_money_for_existing(entry, inv, upi_vpa=upi_vpa)
        return {
            "ok": True,
            "created": False,
            "entry_id": entry_id,
            "misc_bill_no": misc_bill_no,
            "invoice_id": invoice_id,
            "invoice_no": invoice_no,
            "customer_name": customer_name,
            "amount": amount_val,
            "bill_approved": bill_approved,
            "money_voucher_no": (money or {}).get("money_voucher_no"),
            "money_entry_id": (money or {}).get("money_entry_id"),
            "purpose": (money or {}).get("purpose"),
            "message": (
                "Print job already billed; Money In/Out tagged."
                if money
                else "Print job already billed."
            ),
        }

    def status(self, public_id: str) -> dict:
        key = (public_id or "").strip().upper()
        if not key:
            raise ValueError("public_id is required.")
        entry = self._find_existing(key)
        if entry is None:
            return {
                "ok": True,
                "found": False,
                "public_id": key,
                "bill_approved": False,
                "can_delete": True,
            }
        data = self._serialize_existing(entry)
        approved = bool(data.get("bill_approved"))
        return {
            **data,
            "found": True,
            "public_id": key,
            "can_delete": not approved,
        }

    def delete_if_unapproved(self, public_id: str) -> dict:
        """Delete Misc + invoice only when Bill Approved is still No."""
        key = (public_id or "").strip().upper()
        if not key:
            raise ValueError("public_id is required.")
        entry = self._find_existing(key)
        if entry is None:
            return {
                "ok": True,
                "deleted": False,
                "public_id": key,
                "message": "No ERP print billing found.",
            }
        inv = self._invoice_for_entry(entry)
        if inv is not None and bool(getattr(inv, "BillApproved", False)):
            raise ValueError(
                "Invoice already approved — print entry cannot be deleted. "
                f"Invoice {inv.InvoiceNo}."
            )
        entry_id = int(entry.EntryID)
        misc_bill = entry.BillNo
        invoice_no = (inv.InvoiceNo if inv else None) or entry.TallyBillNo
        # Cascade from Print app: Money In/Out → Misc → invoice
        self._delete_linked_money(key, inv)
        message = self.oie.delete_entry(entry_id, allow_print_source=True)
        return {
            "ok": True,
            "deleted": True,
            "public_id": key,
            "entry_id": entry_id,
            "misc_bill_no": misc_bill,
            "invoice_no": invoice_no,
            "message": message,
        }

    def _delete_linked_money(self, public_id: str, inv) -> None:
        """Remove Money In/Out vouchers tagged to this print job / invoice."""
        from app.models.bank_cash import (
            OthersBankCashInvoiceAllocation,
            OthersBankCashTransaction,
        )
        from app.services.others_bank_cash_service import OthersBankCashService

        obc = OthersBankCashService()
        entry_ids: set[int] = set()
        if inv is not None:
            for eid in db.session.scalars(
                select(OthersBankCashInvoiceAllocation.EntryID).where(
                    OthersBankCashInvoiceAllocation.InvoiceID == int(inv.InvoiceID)
                )
            ).all():
                entry_ids.add(int(eid))
        tag = self._tag(public_id)
        for row in db.session.scalars(
            select(OthersBankCashTransaction)
            .where(
                OthersBankCashTransaction.IsActive == True,  # noqa: E712
                OthersBankCashTransaction.Remarks.like(f"%{tag}%"),
            )
            .order_by(OthersBankCashTransaction.EntryID.desc())
        ).all():
            entry_ids.add(int(row.EntryID))
        for eid in entry_ids:
            try:
                obc.delete_entry(eid, allow_print_source=True)
            except ValueError:
                continue

    def create_from_print_job(self, payload: dict) -> dict:
        public_id = (payload.get("public_id") or payload.get("job_id") or "").strip().upper()
        if not public_id:
            raise ValueError("public_id is required.")
        amount = self._money(payload.get("amount"))
        pages = payload.get("pages") or payload.get("total_printed_pages") or ""
        utr = (payload.get("utr") or payload.get("utr_reference") or "").strip()
        mobile = (payload.get("mobile") or "").strip()
        work_date_raw = (payload.get("work_date") or payload.get("completed_at") or "").strip()
        try:
            work_date = date.fromisoformat(work_date_raw[:10]) if work_date_raw else date.today()
        except ValueError:
            work_date = date.today()

        upi_vpa = (
            payload.get("upi_vpa")
            or payload.get("upi_id")
            or DEFAULT_UPI_VPA
        )
        existing = self._find_existing(public_id)
        if existing is not None:
            return self._serialize_existing(
                existing, upi_vpa=str(upi_vpa), ensure_money=True
            )

        customer = self._resolve_billing_customer(mobile)
        work_id, work_type_id = self._ensure_work()
        bank_account_id = self._resolve_upi_bank_account_id(str(upi_vpa))
        tag = self._tag(public_id)
        remarks_parts = [tag, "Document print"]
        if pages not in (None, ""):
            remarks_parts.append(f"{pages} pages")
        if utr:
            remarks_parts.append(f"UTR {utr}")
        if mobile:
            remarks_parts.append(f"Mob {mobile}")
        if customer.get("matched_by") == "mobile" and int(customer.get("match_count") or 0) > 1:
            remarks_parts.append(f"{customer['match_count']} CRM matches")
        remarks = " · ".join(remarks_parts)[:500]

        form = {
            "LedgerKind": OthersIncomeExpenseService.LEDGER_MISC,
            "WorkDate": work_date.isoformat(),
            "WorkID": str(work_id),
            "Amount": str(amount),
            "CategoryAmount": str(amount),
            "CustomerID": str(customer["customer_id"]),
            "CustomerName": customer["customer_name"],
            "MobileNumber": customer["mobile"] or mobile or "",
            "Remarks": remarks,
            "MiscInvoiceWorkflow": "1",
            "WorkDone": "1",
        }
        if work_type_id:
            form["WorkTypeID"] = str(work_type_id)

        save = self.oie.save_entry(form, created_by="Print App")
        entry_id = int(save.entry_id)
        entry = self.oie.entry_repo.get_by_id(entry_id)
        if entry is None:
            raise ValueError("Misc entry could not be loaded after save.")
        misc_bill_no = entry.BillNo

        place = customer.get("state") or DEFAULT_PLACE
        place_code = (
            self.gst.state_code_from_name(place) or DEFAULT_PLACE_CODE
        )
        invoice_payload = {
            "invoice_date": work_date.isoformat(),
            "invoice_kind": GstInvoiceService.INVOICE_KIND_NON_GST,
            "voucher_type": GstInvoiceService.VOUCHER_SALE,
            "customer_id": customer["customer_id"],
            "customer_name": customer["customer_name"],
            "contact_person": customer["customer_name"],
            "contact_mobile": customer["mobile"] or mobile or "",
            "place_of_supply": place,
            "place_of_supply_code": place_code,
            "bill_source": GstInvoiceService.BILL_SOURCE_MISCELLANEOUS,
            "misc_entry_id": entry_id,
            "tally_bill_no": misc_bill_no,
            "bill_approved": False,
            "payment_received": True,
            "payment_bank_account_ids": [bank_account_id],
            "notes": remarks,
            "gst_inclusive": False,
            "lines": [
                {
                    "particulars": "Document Print",
                    "hsn_sac": "",
                    "unit": "NOS",
                    "qty": "1",
                    "rate": str(amount),
                    "discount_amount": "0",
                    "gst_rate_percent": "0",
                }
            ],
        }
        record = self.gst.create_record(
            invoice_payload,
            created_by="Print App",
            require_payment_bank=False,
        )
        invoice_id = int(record["invoice_id"])
        money = self._post_money_inout(
            work_date=work_date,
            amount=amount,
            customer_id=int(customer["customer_id"]),
            invoice_id=invoice_id,
            upi_vpa=str(upi_vpa),
            remarks=remarks,
        )

        def _finish():
            row = self.oie.entry_repo.get_by_id(entry_id)
            if row is None:
                raise ValueError("Misc entry missing after invoice create.")
            row.WorkDone = True
            row.TallyBillGenerated = True
            row.TallyBillNo = record.get("invoice_no") or misc_bill_no
            row.PaymentReceived = True
            db.session.flush()
            return {
                "ok": True,
                "created": True,
                "entry_id": entry_id,
                "misc_bill_no": misc_bill_no,
                "invoice_id": invoice_id,
                "invoice_no": record.get("invoice_no"),
                "customer_name": customer["customer_name"],
                "customer_matched_by": customer.get("matched_by"),
                "amount": float(amount),
                "bill_approved": False,
                "money_voucher_no": money.get("money_voucher_no"),
                "money_entry_id": money.get("money_entry_id"),
                "purpose": money.get("purpose"),
                "message": (
                    "Misc + invoice + Money In/Out (Customer Paid) created. "
                    "Approve invoice manually in Sales."
                ),
            }

        return persist(_finish)
