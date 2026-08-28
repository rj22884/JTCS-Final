from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import or_, select

from app.extensions import db
from app.models.transactions import (
    JTCSDailyTransaction,
    JTCSDailyTransactionPayment,
    JtcsBankTransaction,
)
from app.repositories.transaction_repository import (
    BankTransactionRepository,
    DailyTransactionPaymentRepository,
    DailyTransactionRepository,
    MasterRepository,
)
from app.services.payment_accounting_service import PaymentAccountingService


class FollowupPaymentService:
    def __init__(
        self,
        module_code: str,
        *,
        daily_repo: DailyTransactionRepository | None = None,
        bank_repo: BankTransactionRepository | None = None,
        payment_repo: DailyTransactionPaymentRepository | None = None,
        master_repo: MasterRepository | None = None,
    ):
        self.module_code = (module_code or "").strip().upper()
        self.work_type = self.module_code
        self.sub_work_type = f"{self.module_code} Followup"
        self.receipt_sub_work_type = f"{self.module_code} Followup Receipt"
        self.daily_repo = daily_repo or DailyTransactionRepository()
        self.bank_repo = bank_repo or BankTransactionRepository()
        self.payment_repo = payment_repo or DailyTransactionPaymentRepository()
        self.master_repo = master_repo or MasterRepository()
        self.accounting = PaymentAccountingService(
            self.module_code,
            daily_repo=self.daily_repo,
            bank_repo=self.bank_repo,
            payment_repo=self.payment_repo,
            master_repo=self.master_repo,
        )

    @staticmethod
    def is_udhaar_text(value: str | None) -> bool:
        """True for credit / उधार payment modes (not real cash/bank received)."""
        return PaymentAccountingService.is_udhaar_text(value)

    @classmethod
    def is_udhaar_account(cls, account) -> bool:
        if account is None:
            return False
        return any(
            cls.is_udhaar_text(getattr(account, attr, None))
            for attr in ("BankName", "MaskedAccountNumber", "AccountNumber")
        )

    @classmethod
    def is_udhaar_payment_line(cls, payment: dict | None) -> bool:
        if not payment:
            return False
        if payment.get("is_udhaar") is True:
            return True
        for key in ("bank_name", "masked_account_number", "account_number", "label"):
            if cls.is_udhaar_text(payment.get(key)):
                return True
        return False

    @staticmethod
    def _decimal(value) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Invalid amount.") from None

    @staticmethod
    def _parse_date(value) -> date | None:
        raw = (str(value or "")).strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            raise ValueError("Invalid payment date.") from None

    @staticmethod
    def _get_list(payload: dict, key: str) -> list:
        value = payload.get(key)
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def parse_payment_lines(self, payload: dict, entry_amount: Decimal) -> list[dict]:
        lines_raw = payload.get("payment_lines")
        payment_dates: list[str] = []
        if isinstance(lines_raw, list) and lines_raw:
            bank_ids = [str(item.get("bank_account_id") or item.get("BankAccountID") or "") for item in lines_raw]
            amounts = [str(item.get("amount") or item.get("Amount") or "") for item in lines_raw]
            payment_dates = [
                str(item.get("payment_date") or item.get("PaymentDate") or "") for item in lines_raw
            ]
        else:
            bank_ids = self._get_list(payload, "PaymentBankAccountID[]") or self._get_list(
                payload, "payment_bank_account_id"
            )
            amounts = self._get_list(payload, "PaymentAmount[]") or self._get_list(payload, "payment_amount")
            payment_dates = self._get_list(payload, "PaymentDate[]") or self._get_list(payload, "payment_date")

        if not bank_ids:
            single_bank = payload.get("BankAccountID") or payload.get("bank_account_id")
            if single_bank:
                bank_ids = [str(single_bank)]
                amounts = [str(entry_amount)]
                payment_dates = [
                    str(payload.get("payment_date") or payload.get("PaymentDate") or "")
                ]

        if not bank_ids:
            return []

        if len(amounts) < len(bank_ids):
            amounts.extend([""] * (len(bank_ids) - len(amounts)))
        if len(payment_dates) < len(bank_ids):
            payment_dates.extend([""] * (len(bank_ids) - len(payment_dates)))

        if self.module_code in ("ITR", "DSC", "GST", "TDS"):
            fallback_date = self._parse_date(payload.get("work_date") or payload.get("WorkDate"))
            if fallback_date is None:
                fallback_date = self._parse_date(payload.get("bill_date") or payload.get("BillDate"))
        else:
            fallback_date = self._parse_date(
                payload.get("bill_date") or payload.get("BillDate") or payload.get("work_date") or payload.get("WorkDate")
            )

        lines: list[dict] = []
        total = Decimal("0")
        for index, (bank_id_raw, amount_raw) in enumerate(zip(bank_ids, amounts)):
            bank_account_id = int(bank_id_raw or 0)
            if bank_account_id <= 0:
                raise ValueError("Each payment mode must be selected.")
            amount = self._decimal(amount_raw)
            if amount <= 0:
                raise ValueError("Each payment amount must be greater than zero.")
            payment_mode_id = self.master_repo.resolve_payment_mode_for_bank_account(bank_account_id)
            payment_date = self._parse_date(payment_dates[index]) or fallback_date
            total += amount
            line_data = {
                "bank_account_id": bank_account_id,
                "payment_mode_id": payment_mode_id,
                "amount": amount,
            }
            if payment_date is not None:
                line_data["payment_date"] = payment_date
            lines.append(line_data)

        return lines

    def find_daily_for_bill(self, bill_no: str) -> JTCSDailyTransaction | None:
        """Prefer the receipt daily so edit forms load payment lines, not the invoice debit."""
        receipt = self.accounting.find_receipt_daily(bill_no)
        if receipt is not None:
            return receipt
        return self.accounting.find_sale_daily(bill_no)

    def bills_with_posted_payment(self, bill_nos: set[str]) -> set[str]:
        """Return normalized bill numbers that already have a posted cash/bank receipt."""
        return self.accounting.bills_with_posted_payment(bill_nos)

    def payment_dates_by_bills(self, bill_nos: set[str]) -> dict[str, list[str]]:
        """Unique payment dates (ISO) per bill no, oldest→newest.

        Prefers bank transaction dates; falls back to daily transaction date.
        """
        normalized = {(b or "").strip().upper() for b in bill_nos if (b or "").strip()}
        if not normalized:
            return {}

        # All followup sale + receipt dailies per bill (not only the latest row).
        daily_rows = db.session.execute(
            select(
                JTCSDailyTransaction.ReferenceNo,
                JTCSDailyTransaction.TransactionID,
                JTCSDailyTransaction.TransactionDate,
            )
            .where(
                JTCSDailyTransaction.ReferenceNo.in_(normalized),
                JTCSDailyTransaction.WorkType == self.work_type,
                or_(
                    JTCSDailyTransaction.SubWorkType == self.sub_work_type,
                    JTCSDailyTransaction.SubWorkType == self.receipt_sub_work_type,
                ),
            )
            .order_by(
                JTCSDailyTransaction.ReferenceNo.asc(),
                JTCSDailyTransaction.TransactionID.desc(),
            )
        ).all()

        bill_daily: dict[str, tuple[int, date | None]] = {}
        txn_to_bill: dict[int, str] = {}
        txn_ids: list[int] = []
        for ref, txn_id, txn_date in daily_rows:
            key = (ref or "").strip().upper()
            if not key:
                continue
            txn_to_bill[int(txn_id)] = key
            txn_ids.append(int(txn_id))
            if key not in bill_daily:
                bill_daily[key] = (int(txn_id), txn_date)

        if not bill_daily:
            return {}

        # Dates from payment lines → linked bank rows.
        pay_rows = db.session.execute(
            select(
                JTCSDailyTransactionPayment.TransactionID,
                JtcsBankTransaction.TransactionDate,
            )
            .outerjoin(
                JtcsBankTransaction,
                JtcsBankTransaction.JtcsBankTransactionID
                == JTCSDailyTransactionPayment.BankTransactionID,
            )
            .where(JTCSDailyTransactionPayment.TransactionID.in_(txn_ids))
        ).all()

        # Also include bank rows linked by SourceRecordID / SourceID.
        bank_rows = db.session.execute(
            select(
                JtcsBankTransaction.SourceRecordID,
                JtcsBankTransaction.SourceID,
                JtcsBankTransaction.TransactionDate,
            ).where(
                JtcsBankTransaction.SourceTable == self.bank_repo.SOURCE_TABLE,
                or_(
                    JtcsBankTransaction.SourceRecordID.in_(txn_ids),
                    JtcsBankTransaction.SourceID.in_(txn_ids),
                ),
            )
        ).all()

        dates_by_bill: dict[str, set[str]] = {bill: set() for bill in bill_daily}
        for txn_id, txn_date in pay_rows:
            bill = txn_to_bill.get(int(txn_id))
            if not bill or not txn_date:
                continue
            dates_by_bill[bill].add(txn_date.isoformat())

        for source_record_id, source_id, txn_date in bank_rows:
            if not txn_date:
                continue
            for candidate in (source_record_id, source_id):
                if candidate is None:
                    continue
                bill = txn_to_bill.get(int(candidate))
                if bill:
                    dates_by_bill[bill].add(txn_date.isoformat())
                    break

        # Fallback: daily work/transaction date when no bank dates exist.
        for bill, (_, daily_date) in bill_daily.items():
            if dates_by_bill[bill]:
                continue
            if daily_date:
                dates_by_bill[bill].add(daily_date.isoformat())

        return {
            bill: sorted(date_set)
            for bill, date_set in dates_by_bill.items()
            if date_set
        }

    @classmethod
    def format_payment_account_label(
        cls,
        *,
        bank_name: str | None,
        account_number: str | None = None,
        masked_account_number: str | None = None,
    ) -> str:
        bank = (bank_name or "").strip()
        number = (account_number or "").strip()
        masked = (masked_account_number or "").strip()
        if number in {"-", "—", "–"}:
            number = ""
        if masked in {"-", "—", "–"}:
            masked = ""
        if cls.is_udhaar_text(bank) or cls.is_udhaar_text(masked) or cls.is_udhaar_text(number):
            return "Udhaar"
        if bank.lower() == "cash" or number.lower() == "cash" or masked.lower() == "cash":
            return "Cash"
        if masked and masked.upper() not in {"NA", ""}:
            return masked
        digits = "".join(ch for ch in number if ch.isdigit())
        if len(digits) >= 4:
            return ("X" * (len(digits) - 4)) + digits[-4:]
        if number:
            return number
        return bank

    def payment_account_for_letter(self, bill_no: str) -> str:
        """Account labels for Thank You letter — excludes उधार / credit lines."""
        daily = self.find_daily_for_bill(bill_no)
        if daily is None:
            return ""
        labels: list[str] = []
        payment_rows = self.payment_repo.list_by_transaction(daily.TransactionID)
        for row in payment_rows:
            label = ""
            if row.BankAccountID:
                account = self.master_repo.get_bank_account(row.BankAccountID)
                if account is not None:
                    if self.is_udhaar_account(account):
                        continue
                    label = self.format_payment_account_label(
                        bank_name=account.BankName,
                        account_number=account.AccountNumber,
                        masked_account_number=account.MaskedAccountNumber,
                    )
            if not label and row.PaymentModeID:
                mode = self.master_repo.get_payment_mode(row.PaymentModeID)
                mode_name = (mode.PaymentModeName or "").strip() if mode else ""
                if self.is_udhaar_text(mode_name):
                    continue
                if mode and mode_name.lower() == "cash":
                    label = "Cash"
            if not label and row.BankTransactionID:
                bank_row = self.bank_repo.get_by_id(row.BankTransactionID)
                if bank_row is not None:
                    if self.is_udhaar_text(bank_row.BankName) or self.is_udhaar_text(
                        bank_row.MaskedAccountNumber
                    ):
                        continue
                    label = self.format_payment_account_label(
                        bank_name=bank_row.BankName,
                        masked_account_number=bank_row.MaskedAccountNumber,
                    )
            if label and label != "Udhaar" and label not in labels:
                labels.append(label)
        if not labels:
            for bank_row in self._collect_bank_rows(daily):
                if self.is_udhaar_text(bank_row.BankName) or self.is_udhaar_text(
                    bank_row.MaskedAccountNumber
                ):
                    continue
                label = self.format_payment_account_label(
                    bank_name=bank_row.BankName,
                    masked_account_number=bank_row.MaskedAccountNumber,
                )
                if label and label != "Udhaar" and label not in labels:
                    labels.append(label)
        return ", ".join(labels)

    def load_payment_lines(self, daily: JTCSDailyTransaction) -> list[dict]:
        payment_rows = self.payment_repo.list_by_transaction(daily.TransactionID)
        lines: list[dict] = []
        for row in payment_rows:
            payment_date = None
            if row.BankTransactionID:
                bank_row = self.bank_repo.get_by_id(row.BankTransactionID)
                if bank_row and bank_row.TransactionDate:
                    payment_date = bank_row.TransactionDate.isoformat()
            account = (
                self.master_repo.get_bank_account(row.BankAccountID)
                if row.BankAccountID
                else None
            )
            bank_name = (account.BankName if account is not None else "") or ""
            masked = (account.MaskedAccountNumber if account is not None else "") or ""
            account_number = (account.AccountNumber if account is not None else "") or ""
            is_udhaar = self.is_udhaar_account(account)
            line_data = {
                "bank_account_id": row.BankAccountID,
                "amount": str(row.Amount),
                "payment_mode_id": row.PaymentModeID,
                "bank_name": bank_name,
                "masked_account_number": masked,
                "account_number": account_number,
                "is_udhaar": is_udhaar,
                "label": self.format_payment_account_label(
                    bank_name=bank_name,
                    account_number=account_number,
                    masked_account_number=masked,
                ),
            }
            if payment_date:
                line_data["payment_date"] = payment_date
            lines.append(line_data)
        return lines

    def _collect_bank_rows(self, daily: JTCSDailyTransaction, payment_rows: list | None = None) -> list:
        payment_rows = payment_rows if payment_rows is not None else self.payment_repo.list_by_transaction(
            daily.TransactionID
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

    def remove_daily_transaction(self, daily: JTCSDailyTransaction) -> None:
        payment_rows = self.payment_repo.list_by_transaction(daily.TransactionID)
        bank_rows = self._collect_bank_rows(daily, payment_rows)
        self.payment_repo.delete_by_transaction(daily.TransactionID)
        daily.BankTransactionID = None
        db.session.flush()
        for bank_row in bank_rows:
            self.bank_repo.delete(bank_row)
        self.daily_repo.delete(daily)

    def remove_linked_transactions(self, bill_no: str) -> None:
        """Backward-compatible name: remove Payment Received receipts only, keep the invoice debit."""
        self.remove_receipts(bill_no)

    def remove_receipts(self, bill_no: str) -> None:
        self.accounting.remove_receipts(bill_no)

    def remove_followup_accounting(self, bill_no: str) -> None:
        self.accounting.remove_followup_accounting(bill_no)

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
    ) -> JTCSDailyTransaction | None:
        """Follow-up is not a receivable. Delegates to accounting (no SaleAmount debit)."""
        return self.accounting.post_sale(
            bill_no=bill_no,
            work_date=work_date,
            amount=amount,
            customer_name=customer_name,
            customer_id=customer_id,
            remarks=remarks,
            created_by=created_by,
        )

    def post_payment(
        self,
        *,
        bill_no: str,
        work_date: date,
        entry_amount: Decimal,
        payment_lines: list[dict],
        customer_name: str | None,
        customer_id: int | None,
        remarks: str | None,
        created_by: str,
        existing_daily: JTCSDailyTransaction | None = None,
    ) -> JTCSDailyTransaction:
        """Record Payment Received as Customer Credit only (Bank/UPI/Cash Dr)."""
        return self.accounting.post_receipt(
            bill_no=bill_no,
            work_date=work_date,
            payment_lines=payment_lines,
            customer_name=customer_name,
            customer_id=customer_id,
            remarks=remarks,
            created_by=created_by,
            invoice_amount=entry_amount,
            allow_overpayment=True,
            existing_daily=existing_daily,
        )
