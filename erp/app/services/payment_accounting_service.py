"""Central Payment Received / invoice accounting.

All modules that record a customer invoice or a payment received must use this
service so Customer Ledger is always:

    Invoice / Sale / Service  → Debit
    Payment Received          → Credit
    Advance Payment           → Credit

A payment transaction never posts another Customer Debit (SaleAmount).
Double-entry for receipts: Bank/UPI/Cash Dr → Customer Cr.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, or_, select

from app.extensions import db
from app.models.transactions import JTCSDailyTransaction, JtcsBankTransaction
from app.repositories.transaction_repository import (
    BankTransactionRepository,
    DailyTransactionPaymentRepository,
    DailyTransactionRepository,
    MasterRepository,
)

FOLLOWUP_MODULES = ("ITR", "GST", "TDS", "DSC")
GST_SALE_WORK_TYPE = "Accounting"
GST_SALE_SUB_WORK_TYPE = "Sale / Service Invoice"
RECEIPT_SUB_SUFFIX = "Followup Receipt"


def sql_not_udhaar_bank(alias: str = "b") -> str:
    """SQL predicate: bank row is a real cash/bank receipt, not credit/udhaar."""
    return f"""
        NOT (
            {alias}.BankName LIKE N'%उधार%'
            OR LOWER(ISNULL({alias}.BankName, N'')) LIKE N'%udhaar%'
            OR LOWER(ISNULL({alias}.BankName, N'')) LIKE N'%udhar%'
            OR LOWER(ISNULL({alias}.BankName, N'')) IN (
                N'credit', N'on credit', N'credit sale', N'receivable'
            )
            OR {alias}.MaskedAccountNumber LIKE N'%उधार%'
            OR LOWER(ISNULL({alias}.MaskedAccountNumber, N'')) LIKE N'%udhaar%'
            OR LOWER(ISNULL({alias}.MaskedAccountNumber, N'')) LIKE N'%udhar%'
        )
    """


def sql_customer_receipt_expr(daily_alias: str = "d", linked_bank_alias: str | None = "b") -> str:
    """Customer Credit amount for a daily row (actual money received).

    Prefers SUM of linked bank Debits (all payment lines), excluding udhaar.
    Falls back to the daily's BankTransactionID debit, then payment-line total.
    """
    bank_sum = f"""
        ISNULL((
            SELECT SUM(ISNULL(bx.Debit, 0))
            FROM dbo.JtcsBankTransaction bx
            WHERE bx.SourceTable = N'JTCSDailyTransaction'
              AND (
                    bx.SourceRecordID = {daily_alias}.TransactionID
                    OR bx.SourceID = {daily_alias}.TransactionID
              )
              AND ISNULL(bx.Debit, 0) <> 0
              AND {sql_not_udhaar_bank("bx")}
        ), 0)
    """
    payment_total = f"""
        ISNULL((
            SELECT SUM(p.Amount)
            FROM dbo.JTCSDailyTransactionPayment p
            WHERE p.TransactionID = {daily_alias}.TransactionID
        ), 0)
    """
    linked = (
        f"ISNULL({linked_bank_alias}.Debit, 0)" if linked_bank_alias else "CAST(0 AS DECIMAL(18,2))"
    )
    return f"""
        CASE
            WHEN {bank_sum} <> 0 THEN {bank_sum}
            WHEN {linked} <> 0 THEN {linked}
            ELSE {payment_total}
        END
    """


def sql_unpaid_followup_exclusion() -> str:
    """Exclude FollowupEntryMaster virtual debits when a real sale or receipt exists.

    A receipt-only daily (payment first) must still exclude the virtual bill so
    we do not invent a fake invoice debit. A GST sale invoice for the same
    Tally Bill Number also excludes the virtual row (prevents double debit).
    """
    return """
        AND NOT EXISTS (
            SELECT 1
            FROM dbo.JTCSDailyTransaction d
            WHERE d.Status = N'Posted'
              AND UPPER(LTRIM(RTRIM(ISNULL(d.ReferenceNo, N''))))
                  = UPPER(LTRIM(RTRIM(f.BillNo)))
              AND (
                    d.WorkType = f.ModuleCode
                    OR ISNULL(d.SaleAmount, 0) + ISNULL(d.IncomeAmount, 0) <> 0
                    OR UPPER(LTRIM(RTRIM(ISNULL(d.Remarks, N''))))
                       = UPPER(LTRIM(RTRIM(f.BillNo)))
              )
        )
        AND NOT EXISTS (
            SELECT 1
            FROM dbo.GstInvoice i
            WHERE ISNULL(i.InvoiceValue, 0) <> 0
              AND ISNULL(i.VoucherType, N'SALE') = N'SALE'
              AND UPPER(LTRIM(RTRIM(ISNULL(i.TallyBillNo, N''))))
                  = UPPER(LTRIM(RTRIM(f.BillNo)))
        )
    """


class PaymentAccountingService:
    """Reusable invoice-debit / payment-credit posting."""

    def __init__(
        self,
        module_code: str | None = None,
        *,
        daily_repo: DailyTransactionRepository | None = None,
        bank_repo: BankTransactionRepository | None = None,
        payment_repo: DailyTransactionPaymentRepository | None = None,
        master_repo: MasterRepository | None = None,
    ):
        self.module_code = (module_code or "").strip().upper()
        self.work_type = self.module_code
        self.sale_sub_work_type = f"{self.module_code} Followup" if self.module_code else ""
        self.receipt_sub_work_type = (
            f"{self.module_code} {RECEIPT_SUB_SUFFIX}" if self.module_code else ""
        )
        self.daily_repo = daily_repo or DailyTransactionRepository()
        self.bank_repo = bank_repo or BankTransactionRepository()
        self.payment_repo = payment_repo or DailyTransactionPaymentRepository()
        self.master_repo = master_repo or MasterRepository()

    @staticmethod
    def money(value) -> Decimal:
        try:
            return Decimal(str(value or 0)).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0.00")

    @staticmethod
    def norm_ref(value) -> str:
        return (value or "").strip().upper()

    @staticmethod
    def is_udhaar_text(value: str | None) -> bool:
        raw = (value or "").strip()
        if not raw:
            return False
        if "उधार" in raw:
            return True
        lower = raw.lower()
        if "udhaar" in lower or "udhar" in lower:
            return True
        if lower in {"credit", "on credit", "credit sale", "receivable"}:
            return True
        return False

    @classmethod
    def is_udhaar_account(cls, account) -> bool:
        if account is None:
            return False
        return any(
            cls.is_udhaar_text(getattr(account, attr, None))
            for attr in ("BankName", "MaskedAccountNumber", "AccountNumber")
        )

    def _dailies_for_reference(
        self,
        reference_no: str,
        *,
        work_type: str | None = None,
        customer_id: int | None = None,
    ) -> list[JTCSDailyTransaction]:
        ref = self.norm_ref(reference_no)
        if not ref:
            return []
        stmt = select(JTCSDailyTransaction).where(
            JTCSDailyTransaction.ReferenceNo == ref,
            JTCSDailyTransaction.Status == "Posted",
        )
        wt = (work_type or self.work_type or "").strip()
        if wt:
            stmt = stmt.where(
                or_(
                    JTCSDailyTransaction.WorkType == wt,
                    JTCSDailyTransaction.Remarks == ref,
                )
            )
        if customer_id:
            stmt = stmt.where(
                or_(
                    JTCSDailyTransaction.CustomerID == int(customer_id),
                    JTCSDailyTransaction.CustomerID.is_(None),
                )
            )
        stmt = stmt.order_by(JTCSDailyTransaction.TransactionID.asc())
        rows = list(db.session.scalars(stmt).all())
        if wt:
            extra = db.session.scalars(
                select(JTCSDailyTransaction)
                .where(
                    JTCSDailyTransaction.Status == "Posted",
                    JTCSDailyTransaction.ReferenceNo == ref,
                    JTCSDailyTransaction.WorkType == wt,
                )
                .order_by(JTCSDailyTransaction.TransactionID.asc())
            ).all()
            seen = {r.TransactionID for r in rows}
            for row in extra:
                if row.TransactionID not in seen:
                    rows.append(row)
        return rows

    def _module_dailies(self, reference_no: str) -> list[JTCSDailyTransaction]:
        ref = self.norm_ref(reference_no)
        if not ref or not self.work_type:
            return []
        return list(
            db.session.scalars(
                select(JTCSDailyTransaction)
                .where(
                    JTCSDailyTransaction.ReferenceNo == ref,
                    JTCSDailyTransaction.WorkType == self.work_type,
                    JTCSDailyTransaction.Status == "Posted",
                )
                .order_by(JTCSDailyTransaction.TransactionID.asc())
            ).all()
        )

    def _has_payment_lines(self, daily: JTCSDailyTransaction) -> bool:
        return bool(self.payment_repo.list_by_transaction(daily.TransactionID))

    def _received_on_daily(self, daily: JTCSDailyTransaction) -> Decimal:
        total = Decimal("0.00")
        for bank in self._collect_bank_rows(daily):
            if self.is_udhaar_text(bank.BankName) or self.is_udhaar_text(bank.MaskedAccountNumber):
                continue
            total += self.money(bank.Debit)
        if total > 0:
            return total
        for row in self.payment_repo.list_by_transaction(daily.TransactionID):
            account = (
                self.master_repo.get_bank_account(row.BankAccountID) if row.BankAccountID else None
            )
            if self.is_udhaar_account(account):
                continue
            total += self.money(row.Amount)
        return total

    def _is_gst_sale_daily(self, daily: JTCSDailyTransaction) -> bool:
        return (
            (daily.WorkType or "") == GST_SALE_WORK_TYPE
            and (daily.SubWorkType or "") == GST_SALE_SUB_WORK_TYPE
        )

    def _is_followup_sale_daily(self, daily: JTCSDailyTransaction) -> bool:
        if self._is_gst_sale_daily(daily):
            return False
        sale = self.money(daily.SaleAmount) + self.money(daily.IncomeAmount)
        if sale <= 0:
            return False
        sub = (daily.SubWorkType or "").strip()
        if sub == self.receipt_sub_work_type:
            return False
        return True

    def _is_receipt_daily(self, daily: JTCSDailyTransaction) -> bool:
        if self._is_gst_sale_daily(daily):
            return False
        sub = (daily.SubWorkType or "").strip()
        if sub == self.receipt_sub_work_type:
            return True
        sale = self.money(daily.SaleAmount) + self.money(daily.IncomeAmount)
        if sale == 0 and (self._has_payment_lines(daily) or self._received_on_daily(daily) > 0):
            return True
        return False

    def _is_combined_daily(self, daily: JTCSDailyTransaction) -> bool:
        """Legacy cash-sale row: SaleAmount AND a real receipt on the same daily."""
        if self._is_gst_sale_daily(daily):
            return False
        sale = self.money(daily.SaleAmount) + self.money(daily.IncomeAmount)
        if sale <= 0:
            return False
        if self._has_payment_lines(daily) or self._received_on_daily(daily) > 0:
            return True
        return False

    def find_gst_invoice(self, tally_bill_no: str):
        ref = self.norm_ref(tally_bill_no)
        if not ref:
            return None
        try:
            from app.models.gst_billing import GstInvoice

            return db.session.scalars(
                select(GstInvoice)
                .where(func.upper(func.ltrim(func.rtrim(func.coalesce(GstInvoice.TallyBillNo, "")))) == ref)
                .order_by(GstInvoice.InvoiceID.desc())
            ).first()
        except Exception:
            return None

    def find_gst_sale_daily(self, tally_bill_no: str) -> JTCSDailyTransaction | None:
        ref = self.norm_ref(tally_bill_no)
        if not ref:
            return None
        inv = self.find_gst_invoice(ref)
        if inv is not None:
            daily_id = getattr(inv, "DailyTransactionID", None)
            if daily_id:
                daily = db.session.get(JTCSDailyTransaction, int(daily_id))
                if daily is not None and self.money(daily.SaleAmount) != 0:
                    return daily
            invoice_no = self.norm_ref(getattr(inv, "InvoiceNo", None))
            if invoice_no:
                own = db.session.scalars(
                    select(JTCSDailyTransaction)
                    .where(
                        JTCSDailyTransaction.WorkType == GST_SALE_WORK_TYPE,
                        JTCSDailyTransaction.SubWorkType == GST_SALE_SUB_WORK_TYPE,
                        JTCSDailyTransaction.ReferenceNo == invoice_no,
                        JTCSDailyTransaction.Status == "Posted",
                    )
                    .order_by(JTCSDailyTransaction.TransactionID.desc())
                ).first()
                if own is not None and self.money(own.SaleAmount) != 0:
                    return own
        return db.session.scalars(
            select(JTCSDailyTransaction)
            .where(
                JTCSDailyTransaction.WorkType == GST_SALE_WORK_TYPE,
                JTCSDailyTransaction.SubWorkType == GST_SALE_SUB_WORK_TYPE,
                JTCSDailyTransaction.Status == "Posted",
                JTCSDailyTransaction.SaleAmount != 0,
                or_(
                    JTCSDailyTransaction.Remarks == ref,
                    JTCSDailyTransaction.ReferenceNo == ref,
                ),
            )
            .order_by(JTCSDailyTransaction.TransactionID.desc())
        ).first()

    def find_sale_daily(self, bill_no: str) -> JTCSDailyTransaction | None:
        gst = self.find_gst_sale_daily(bill_no)
        if gst is not None:
            return gst
        for daily in self._module_dailies(bill_no):
            if self._is_followup_sale_daily(daily) and not self._is_combined_daily(daily):
                return daily
        for daily in reversed(self._module_dailies(bill_no)):
            if self._is_followup_sale_daily(daily):
                return daily
        return None

    def _dailies_for_bill_any_work_type(self, bill_no: str) -> list[JTCSDailyTransaction]:
        """All posted dailies for a tally bill, including leftover wrong-WorkType receipts."""
        ref = self.norm_ref(bill_no)
        if not ref:
            return []
        seen: dict[int, JTCSDailyTransaction] = {}
        for daily in self._module_dailies(ref):
            seen[int(daily.TransactionID)] = daily
        extras = db.session.scalars(
            select(JTCSDailyTransaction)
            .where(
                JTCSDailyTransaction.Status == "Posted",
                or_(
                    JTCSDailyTransaction.ReferenceNo == ref,
                    JTCSDailyTransaction.Remarks == ref,
                ),
            )
            .order_by(JTCSDailyTransaction.TransactionID.asc())
        ).all()
        for daily in extras:
            seen.setdefault(int(daily.TransactionID), daily)
        return list(seen.values())

    def _cannot_reuse_as_receipt(self, daily: JTCSDailyTransaction | None) -> bool:
        if daily is None:
            return True
        if self._is_gst_sale_daily(daily):
            return True
        if self._is_followup_sale_daily(daily) and not self._is_combined_daily(daily):
            return True
        return False

    def find_receipt_daily(self, bill_no: str) -> JTCSDailyTransaction | None:
        dailies = self._dailies_for_bill_any_work_type(bill_no)
        receipts = [d for d in dailies if self._is_receipt_daily(d)]
        if receipts:
            return receipts[-1]
        combined = [d for d in dailies if self._is_combined_daily(d)]
        if combined:
            return combined[-1]
        return None

    def find_receipt_dailies(self, bill_no: str) -> list[JTCSDailyTransaction]:
        return [
            d
            for d in self._dailies_for_bill_any_work_type(bill_no)
            if self._is_receipt_daily(d) or self._is_combined_daily(d)
        ]

    def allocated_receipt_amount(
        self,
        bill_no: str,
        *,
        exclude_daily_id: int | None = None,
    ) -> Decimal:
        total = Decimal("0.00")
        for daily in self.find_receipt_dailies(bill_no):
            if exclude_daily_id and daily.TransactionID == int(exclude_daily_id):
                continue
            total += self._received_on_daily(daily)
        return total

    def invoice_amount(self, bill_no: str, *, fallback: Decimal | None = None) -> Decimal:
        sale = self.find_sale_daily(bill_no)
        if sale is not None:
            amount = self.money(sale.SaleAmount) + self.money(sale.IncomeAmount)
            if amount > 0:
                return amount
        inv = self.find_gst_invoice(bill_no)
        if inv is not None:
            amount = self.money(getattr(inv, "InvoiceValue", 0))
            if amount > 0:
                return amount
        if fallback is not None:
            return self.money(fallback)
        return Decimal("0.00")

    def remaining_invoice_amount(
        self,
        bill_no: str,
        *,
        invoice_amount: Decimal | None = None,
        exclude_daily_id: int | None = None,
    ) -> Decimal:
        billed = self.invoice_amount(bill_no, fallback=invoice_amount)
        if billed <= 0:
            return Decimal("0.00")
        paid = self.allocated_receipt_amount(bill_no, exclude_daily_id=exclude_daily_id)
        remaining = billed - paid
        return remaining if remaining > 0 else Decimal("0.00")

    def _collect_bank_rows(
        self, daily: JTCSDailyTransaction, payment_rows: list | None = None
    ) -> list[JtcsBankTransaction]:
        payment_rows = (
            payment_rows
            if payment_rows is not None
            else self.payment_repo.list_by_transaction(daily.TransactionID)
        )
        bank_rows = self.bank_repo.find_all_by_daily_id(daily.TransactionID)
        seen = {row.JtcsBankTransactionID for row in bank_rows}
        for payment_row in payment_rows:
            if payment_row.BankTransactionID and payment_row.BankTransactionID not in seen:
                bank_row = self.bank_repo.get_by_id(payment_row.BankTransactionID)
                if bank_row is not None:
                    bank_rows.append(bank_row)
                    seen.add(bank_row.JtcsBankTransactionID)
        if daily.BankTransactionID and daily.BankTransactionID not in seen:
            bank_row = self.bank_repo.get_by_id(daily.BankTransactionID)
            if bank_row is not None:
                bank_rows.append(bank_row)
        bank_rows.sort(key=lambda row: (row.PaymentSequence or 0, row.JtcsBankTransactionID))
        return bank_rows

    def _clear_payments(self, daily: JTCSDailyTransaction) -> None:
        payment_rows = self.payment_repo.list_by_transaction(daily.TransactionID)
        bank_rows = self._collect_bank_rows(daily, payment_rows)
        self.payment_repo.delete_by_transaction(daily.TransactionID)
        daily.BankTransactionID = None
        daily.PaymentSplitCount = 1
        db.session.flush()
        for bank_row in bank_rows:
            self.bank_repo.delete(bank_row)

    def _delete_daily(self, daily: JTCSDailyTransaction) -> None:
        self._clear_payments(daily)
        self.daily_repo.delete(daily)

    def gst_invoice_exists(self, bill_no: str) -> bool:
        inv = self.find_gst_invoice(bill_no)
        return inv is not None and self.money(getattr(inv, "InvoiceValue", 0)) > 0

    def other_sale_exists(self, bill_no: str, *, exclude_daily_id: int | None = None) -> bool:
        gst = self.find_gst_sale_daily(bill_no)
        if gst is not None and (exclude_daily_id is None or gst.TransactionID != int(exclude_daily_id)):
            return True
        if self.gst_invoice_exists(bill_no):
            return True
        for daily in self._module_dailies(bill_no):
            if exclude_daily_id and daily.TransactionID == int(exclude_daily_id):
                continue
            if self._is_followup_sale_daily(daily) and not self._is_combined_daily(daily):
                return True
        return False

    def ensure_gst_invoice_posted(self, bill_no: str) -> bool:
        """Post the GST Sale / Service Invoice daily if a bill already has an invoice.

        Does not invent a follow-up debit. Safe to call from payment/follow-up flows.
        """
        inv = self.find_gst_invoice(bill_no)
        if inv is None or self.money(getattr(inv, "InvoiceValue", 0)) <= 0:
            return False
        from app.services.gst_invoice_service import GstInvoiceService

        return bool(GstInvoiceService()._sync_sale_daily(inv))

    def _zero_sale_keep_receipt(self, daily: JTCSDailyTransaction) -> None:
        daily.SaleAmount = Decimal("0.00")
        daily.IncomeAmount = Decimal("0.00")
        received = self._received_on_daily(daily)
        daily.TotalAmount = received
        daily.SubWorkType = self.receipt_sub_work_type or daily.SubWorkType
        daily.ModifiedDate = datetime.utcnow()

    def reconcile_reference(self, bill_no: str) -> dict:
        """Heal duplicate Customer Debits for one bill without deleting receipts.

        When a GST invoice exists for the Tally Bill Number, any follow-up
        SaleAmount is a duplicate receivable and is removed (sale-only rows)
        or zeroed (receipt/combined rows). Receipts stay as Customer Credit.
        Historical follow-up sales with no invoice are left untouched.
        """
        ref = self.norm_ref(bill_no)
        if not ref:
            return {
                "cleared_sale_on_receipts": 0,
                "removed_followup_sales": 0,
                "removed_extra_receipts": 0,
            }
        invoice_exists = self.gst_invoice_exists(ref) or self.find_gst_sale_daily(ref) is not None
        cleared = 0
        removed = 0
        for daily in list(self._module_dailies(ref)):
            if self._is_gst_sale_daily(daily):
                continue
            if invoice_exists:
                if self._is_combined_daily(daily) or (
                    self._is_receipt_daily(daily) and self.money(daily.SaleAmount) + self.money(daily.IncomeAmount) > 0
                ):
                    self._zero_sale_keep_receipt(daily)
                    cleared += 1
                    continue
                if self._is_followup_sale_daily(daily):
                    self._delete_daily(daily)
                    removed += 1
                    continue
                continue
            if not self._is_combined_daily(daily) and not (
                self._is_receipt_daily(daily) and self.money(daily.SaleAmount) > 0
            ):
                continue
            if not self.other_sale_exists(ref, exclude_daily_id=daily.TransactionID):
                continue
            self._zero_sale_keep_receipt(daily)
            cleared += 1
        db.session.flush()
        return {
            "cleared_sale_on_receipts": cleared,
            "removed_followup_sales": removed,
            "removed_extra_receipts": 0,
        }

    def reconcile_all_followup_duplicates(self) -> dict:
        """Heal leftover follow-up SaleAmount rows when a GST invoice already exists."""
        stmt = (
            select(JTCSDailyTransaction)
            .where(
                JTCSDailyTransaction.Status == "Posted",
                JTCSDailyTransaction.WorkType.in_(FOLLOWUP_MODULES),
                JTCSDailyTransaction.SaleAmount != 0,
            )
            .order_by(JTCSDailyTransaction.TransactionID.asc())
        )
        seen: set[str] = set()
        totals = {
            "cleared_sale_on_receipts": 0,
            "removed_followup_sales": 0,
            "invoices_posted": 0,
            "bills": 0,
        }
        for daily in db.session.scalars(stmt).all():
            ref = self.norm_ref(daily.ReferenceNo)
            if not ref or ref in seen:
                continue
            svc = PaymentAccountingService(daily.WorkType)
            invoice_exists = svc.gst_invoice_exists(ref) or svc.find_gst_sale_daily(ref) is not None
            has_receipt = svc._has_payment_lines(daily) or svc._received_on_daily(daily) > 0
            if not invoice_exists and not has_receipt:
                continue
            seen.add(ref)
            if invoice_exists and svc.ensure_gst_invoice_posted(ref):
                totals["invoices_posted"] += 1
            result = svc.reconcile_reference(ref)
            totals["cleared_sale_on_receipts"] += int(result.get("cleared_sale_on_receipts") or 0)
            totals["removed_followup_sales"] += int(result.get("removed_followup_sales") or 0)
            totals["bills"] += 1
        try:
            from app.models.followup import FollowupEntryMaster
            from app.models.gst_billing import GstInvoice

            unposted = db.session.scalars(
                select(GstInvoice)
                .where(
                    GstInvoice.DailyTransactionID.is_(None),
                    GstInvoice.InvoiceValue != 0,
                )
                .order_by(GstInvoice.InvoiceID.asc())
            ).all()
            for inv in unposted:
                voucher = (getattr(inv, "VoucherType", None) or "SALE").strip().upper()
                if voucher != "SALE":
                    continue
                ref = self.norm_ref(getattr(inv, "TallyBillNo", None))
                if not ref or ref in seen:
                    continue
                module = None
                entry = db.session.scalars(
                    select(FollowupEntryMaster)
                    .where(
                        func.upper(func.ltrim(func.rtrim(func.coalesce(FollowupEntryMaster.BillNo, ""))))
                        == ref
                    )
                    .order_by(FollowupEntryMaster.EntryID.desc())
                ).first()
                if entry is not None:
                    module = (entry.ModuleCode or "").strip().upper() or None
                if module is None:
                    linked = db.session.scalars(
                        select(JTCSDailyTransaction)
                        .where(
                            JTCSDailyTransaction.ReferenceNo == ref,
                            JTCSDailyTransaction.Status == "Posted",
                            JTCSDailyTransaction.WorkType.in_(FOLLOWUP_MODULES),
                        )
                        .order_by(JTCSDailyTransaction.TransactionID.desc())
                    ).first()
                    if linked is not None:
                        module = (linked.WorkType or "").strip().upper() or None
                svc = PaymentAccountingService(module)
                seen.add(ref)
                if svc.ensure_gst_invoice_posted(ref):
                    totals["invoices_posted"] += 1
                result = svc.reconcile_reference(ref)
                totals["cleared_sale_on_receipts"] += int(result.get("cleared_sale_on_receipts") or 0)
                totals["removed_followup_sales"] += int(result.get("removed_followup_sales") or 0)
                totals["bills"] += 1
        except Exception:
            pass
        return totals

    def post_sale(
        self,
        *,
        bill_no: str,
        work_date: date,
        amount: Decimal,
        customer_name: str | None,
        customer_id: int | None,
        remarks: str | None,
        created_by: str,
        description: str | None = None,
    ) -> JTCSDailyTransaction | None:
        """Follow-up is workflow-only. Never posts a Customer Debit.

        If a GST invoice already exists for this Tally Bill Number, post/keep
        that invoice daily and strip leftover follow-up SaleAmount rows.
        """
        ref = self.norm_ref(bill_no)
        if not ref:
            return None
        self.ensure_gst_invoice_posted(ref)
        self.reconcile_reference(ref)
        return self.find_gst_sale_daily(ref)

    def _split_combined_keep_sale(self, combined: JTCSDailyTransaction) -> None:
        """Turn a legacy sale+receipt daily into a sale-only daily."""
        self._clear_payments(combined)
        combined.SubWorkType = self.sale_sub_work_type
        combined.ModifiedDate = datetime.utcnow()
        db.session.flush()

    def _write_receipt_lines(
        self,
        daily: JTCSDailyTransaction,
        payment_lines: list[dict],
        *,
        bill_no: str,
        work_date: date,
        created_by: str,
    ) -> None:
        bank_ids: list[int] = []
        sequence = 0
        for payment_line in payment_lines:
            sequence += 1
            bank_account = self.master_repo.resolve_bank_account_by_id(payment_line["bank_account_id"])
            is_udhaar = self.is_udhaar_account(
                self.master_repo.get_bank_account(payment_line["bank_account_id"])
            )
            bank_txn_id = None
            if not is_udhaar:
                line_date = payment_line.get("payment_date") or work_date
                bank = self.bank_repo.create(
                    {
                        "JtcsBankAccountID": bank_account.account_id or 0,
                        "BankName": bank_account.bank_name,
                        "MaskedAccountNumber": bank_account.masked_account_number,
                        "TransactionDate": line_date,
                        "Description": self.receipt_sub_work_type or "Payment Received",
                        "Debit": payment_line["amount"],
                        "Credit": None,
                        "ClosingBalance": Decimal("0"),
                        "ImportedBy": created_by,
                        "ImportedDate": datetime.utcnow(),
                        "Remarks": bill_no,
                        "IsLocked": False,
                        "SourceTable": self.bank_repo.SOURCE_TABLE,
                        "SourceRecordID": daily.TransactionID,
                        "SourceType": self.work_type,
                        "SourceID": daily.TransactionID,
                        "LedgerKind": "RECEIPT",
                        "PaymentModeID": payment_line["payment_mode_id"],
                        "PaymentSequence": sequence,
                    }
                )
                bank_txn_id = bank.JtcsBankTransactionID
                bank_ids.append(bank_txn_id)
            self.payment_repo.create(
                {
                    "TransactionID": daily.TransactionID,
                    "PaymentSequence": sequence,
                    "PaymentModeID": payment_line["payment_mode_id"],
                    "BankAccountID": payment_line["bank_account_id"],
                    "Amount": payment_line["amount"],
                    "BankTransactionID": bank_txn_id,
                }
            )
        if bank_ids:
            self.daily_repo.update_bank_link(daily, bank_ids[0])

    def post_receipt(
        self,
        *,
        bill_no: str,
        work_date: date,
        payment_lines: list[dict],
        customer_name: str | None,
        customer_id: int | None,
        remarks: str | None,
        created_by: str,
        invoice_amount: Decimal | None = None,
        allow_overpayment: bool = True,
        existing_daily: JTCSDailyTransaction | None = None,
    ) -> JTCSDailyTransaction:
        """Customer Credit only. Bank/UPI/Cash Dr. Never writes SaleAmount."""
        ref = self.norm_ref(bill_no)
        if not ref:
            raise ValueError("Bill / invoice reference is required for Payment Received.")
        if not payment_lines:
            raise ValueError("Add at least one payment mode with amount.")
        if not customer_id:
            raise ValueError("Customer is required for Payment Received.")

        received = Decimal("0.00")
        for line in payment_lines:
            amount = self.money(line.get("amount"))
            if amount <= 0:
                raise ValueError("Each payment amount must be greater than zero.")
            account = self.master_repo.get_bank_account(line["bank_account_id"])
            if not self.is_udhaar_account(account):
                received += amount

        self.ensure_gst_invoice_posted(ref)
        billed = self.invoice_amount(ref)
        canonical = existing_daily
        if self._cannot_reuse_as_receipt(canonical):
            canonical = None
        if canonical is None:
            canonical = self.find_receipt_daily(ref)
        if self._cannot_reuse_as_receipt(canonical):
            canonical = None

        exclude_id = canonical.TransactionID if canonical is not None else None
        already_paid = self.allocated_receipt_amount(ref, exclude_daily_id=exclude_id)
        remaining = billed - already_paid if billed > 0 else Decimal("0.00")
        if billed > 0 and received > remaining and not allow_overpayment:
            raise ValueError(
                f"Payment received ({received}) exceeds remaining invoice amount ({remaining})."
            )

        is_advance = billed <= 0
        description = (
            f"Advance Payment — {ref}"
            if is_advance
            else f"Payment Received — {ref}"
        )

        if canonical is not None and self._is_combined_daily(canonical):
            if self.other_sale_exists(ref, exclude_daily_id=canonical.TransactionID):
                self._clear_payments(canonical)
                canonical.SaleAmount = Decimal("0.00")
                canonical.IncomeAmount = Decimal("0.00")
            else:
                self._split_combined_keep_sale(canonical)
                canonical = None

        extras = [
            d
            for d in self.find_receipt_dailies(ref)
            if canonical is None or d.TransactionID != canonical.TransactionID
        ]
        for extra in extras:
            if extra.TransactionID == (canonical.TransactionID if canonical else -1):
                continue
            if self._is_combined_daily(extra) and not self.other_sale_exists(
                ref, exclude_daily_id=extra.TransactionID
            ):
                self._split_combined_keep_sale(extra)
                continue
            self._delete_daily(extra)

        if canonical is None:
            canonical = self.find_receipt_daily(ref)
        if self._cannot_reuse_as_receipt(canonical):
            canonical = None

        payload_header = {
            "TransactionDate": work_date,
            "CustomerID": customer_id,
            "CustomerName": customer_name,
            "ReferenceNo": ref,
            "Description": description,
            "IncomeAmount": Decimal("0"),
            "ExpenseAmount": Decimal("0"),
            "SaleAmount": Decimal("0"),
            "PurchaseAmount": Decimal("0"),
            "GSTAmount": Decimal("0"),
            "TDSAmount": Decimal("0"),
            "TotalAmount": received,
            "PaymentModeID": payment_lines[0]["payment_mode_id"],
            "PaymentSplitCount": len(payment_lines),
            "Remarks": remarks,
            "SubWorkType": self.receipt_sub_work_type,
        }

        if canonical is not None:
            self._clear_payments(canonical)
            canonical.TransactionDate = work_date
            canonical.WorkType = self.work_type or canonical.WorkType
            canonical.CustomerID = customer_id
            canonical.CustomerName = customer_name
            canonical.ReferenceNo = ref
            canonical.Description = description
            canonical.IncomeAmount = Decimal("0")
            canonical.ExpenseAmount = Decimal("0")
            canonical.SaleAmount = Decimal("0")
            canonical.PurchaseAmount = Decimal("0")
            canonical.GSTAmount = Decimal("0")
            canonical.TDSAmount = Decimal("0")
            canonical.TotalAmount = received
            canonical.PaymentModeID = payment_lines[0]["payment_mode_id"]
            canonical.PaymentSplitCount = len(payment_lines)
            canonical.Remarks = remarks
            canonical.SubWorkType = self.receipt_sub_work_type
            canonical.ModifiedDate = datetime.utcnow()
            db.session.flush()
            daily = canonical
        else:
            daily = self.daily_repo.create(
                {
                    **payload_header,
                    "WorkType": self.work_type,
                    "Status": "Posted",
                    "CreatedBy": created_by,
                    "CreatedDate": datetime.utcnow(),
                }
            )

        self._write_receipt_lines(
            daily,
            payment_lines,
            bill_no=ref,
            work_date=work_date,
            created_by=created_by,
        )
        self.reconcile_reference(ref)
        return daily

    def remove_receipts(self, bill_no: str) -> None:
        for daily in list(self.find_receipt_dailies(bill_no)):
            if self._is_combined_daily(daily) and not self.other_sale_exists(
                bill_no, exclude_daily_id=daily.TransactionID
            ):
                self._split_combined_keep_sale(daily)
                continue
            self._delete_daily(daily)

    def remove_followup_sale(self, bill_no: str) -> None:
        for daily in list(self._module_dailies(bill_no)):
            if self._is_gst_sale_daily(daily):
                continue
            if self._is_receipt_daily(daily):
                continue
            if self._is_followup_sale_daily(daily) and not self._is_combined_daily(daily):
                self._delete_daily(daily)

    def remove_followup_accounting(self, bill_no: str) -> None:
        """Remove followup sale + receipts. Never deletes a GST invoice sale daily."""
        self.remove_receipts(bill_no)
        self.remove_followup_sale(bill_no)
        leftover = self.find_receipt_daily(bill_no)
        if leftover is not None and not self._is_gst_sale_daily(leftover):
            if self._is_combined_daily(leftover):
                self._delete_daily(leftover)
            elif self._is_receipt_daily(leftover):
                self._delete_daily(leftover)

    def bills_with_posted_payment(self, bill_nos: set[str]) -> set[str]:
        paid: set[str] = set()
        for raw in bill_nos:
            ref = self.norm_ref(raw)
            if not ref:
                continue
            if self.allocated_receipt_amount(ref) > 0:
                paid.add(ref)
        return paid
