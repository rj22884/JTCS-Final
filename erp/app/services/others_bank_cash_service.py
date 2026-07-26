from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select, update

from app.extensions import db
from app.models.auth import User
from app.models.transactions import JTCSDailyTransaction, JTCSDailyTransactionPayment
from app.repositories.bank_cash_repository import OthersBankCashRepository
from app.repositories.transaction_repository import (
    BankTransactionRepository,
    DailyTransactionRepository,
    MasterRepository,
)
from app.utils.db_session import persist
from app.utils.smtp_health import mask_email


@dataclass
class BankCashSaveResult:
    entry_id: int
    voucher_no: str
    bank_transaction_ids: list[int]
    message: str


class OthersBankCashService:
    WORK_TYPE = "Others"
    SUB_WORK_TYPE = "Other Bank/Cash Transactions"
    SOURCE_TYPE = "OTHERS_BANK_CASH"

    def __init__(
        self,
        entry_repo: OthersBankCashRepository | None = None,
        bank_repo: BankTransactionRepository | None = None,
        daily_repo: DailyTransactionRepository | None = None,
        master_repo: MasterRepository | None = None,
    ):
        self.entry_repo = entry_repo or OthersBankCashRepository()
        self.bank_repo = bank_repo or BankTransactionRepository()
        self.daily_repo = daily_repo or DailyTransactionRepository()
        self.master_repo = master_repo or MasterRepository()

    @staticmethod
    def _decimal(value) -> Decimal:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Invalid amount.") from None
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")
        return amount

    @staticmethod
    def _date(value) -> date:
        raw = (value or "").strip()
        if not raw:
            raise ValueError("Work date is required.")
        try:
            return date.fromisoformat(raw[:10])
        except ValueError as exc:
            raise ValueError("Invalid work date.") from exc

    @staticmethod
    def _clean(value, max_len: int | None = None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if max_len is not None:
            return text[:max_len]
        return text

    def list_accounts(self) -> list[dict]:
        rows = []
        for account in self.entry_repo.list_ledger_accounts(active_only=True):
            account_type = (account.AccountType or "OTH").strip() or "OTH"
            label_parts = [account.BankName or "Account"]
            if account.MaskedAccountNumber:
                label_parts.append(account.MaskedAccountNumber)
            elif account.AccountNumber:
                label_parts.append(account.AccountNumber)
            label_parts.append(f"[{account_type}]")
            rows.append(
                {
                    "account_id": account.JtcsBankAccountID,
                    "label": " · ".join(label_parts),
                    "bank_name": account.BankName or "",
                    "account_type": account_type,
                    "is_rd": account_type == "RD",
                    "is_cash": (account.BankName or "").strip().lower() == "cash",
                }
            )
        return rows

    def _account_label(self, account_id: int) -> str:
        account = self.master_repo.get_bank_account(account_id)
        if account is None:
            return f"#{account_id}"
        mask = account.MaskedAccountNumber or account.AccountNumber or ""
        account_type = account.AccountType or "OTH"
        return f"{account.BankName} · {mask} [{account_type}]".strip()

    @staticmethod
    def actor_login_email(*, user_id: int | None = None, fallback: str | None = None) -> str:
        if user_id:
            user = db.session.get(User, user_id)
            if user and user.EmailID:
                return user.EmailID.strip()
        return (fallback or "System").strip() or "System"

    def _entered_by_lookup(self) -> dict[str, str]:
        """Map FullName / EmailID -> masked login email for grid display."""
        mapping: dict[str, str] = {}
        for user in db.session.scalars(select(User)).all():
            email = (user.EmailID or "").strip()
            if not email:
                continue
            masked = mask_email(email)
            mapping[email.lower()] = masked
            name = (user.FullName or "").strip()
            if name:
                mapping[name.lower()] = masked
        return mapping

    def _mask_entered_by(self, created_by: str | None, lookup: dict[str, str]) -> str:
        value = (created_by or "").strip()
        if not value:
            return ""
        resolved = lookup.get(value.lower())
        if resolved:
            return resolved
        if "@" in value:
            return mask_email(value)
        return value

    def list_entries(self) -> list[dict]:
        lookup = self._entered_by_lookup()
        rows = []
        for row in self.entry_repo.list_active():
            rows.append(
                {
                    "entry_id": row.EntryID,
                    "voucher_no": row.VoucherNo,
                    "work_date": row.WorkDate.isoformat() if row.WorkDate else "",
                    "purpose": row.Purpose or "",
                    "credit_account_id": row.CreditBankAccountID,
                    "credit_account": self._account_label(row.CreditBankAccountID),
                    "debit_account_id": row.DebitBankAccountID,
                    "debit_account": self._account_label(row.DebitBankAccountID),
                    "amount": float(row.Amount or 0),
                    "remarks": row.Remarks or "",
                    "entered_by": self._mask_entered_by(row.CreatedBy, lookup),
                    "created_by": row.CreatedBy or "",
                    "created_date": row.CreatedDate.isoformat() if row.CreatedDate else "",
                }
            )
        return rows

    def next_voucher_no(self, work_date_raw: str | None = None) -> str:
        work_date = self._date(work_date_raw) if work_date_raw else date.today()
        return self.entry_repo.next_voucher_no(work_date)

    def _create_bank_leg(
        self,
        *,
        bank_account,
        txn_date: date,
        description: str,
        money_in: Decimal,
        money_out: Decimal,
        created_by: str,
        source_id: int | None,
        ledger_kind: str,
        remarks: str,
        daily_id: int | None,
    ):
        now = datetime.utcnow()
        return self.bank_repo.create(
            {
                "JtcsBankAccountID": bank_account.account_id or 0,
                "BankName": bank_account.bank_name,
                "MaskedAccountNumber": bank_account.masked_account_number,
                "TransactionDate": txn_date,
                "Description": description[:1000],
                "Debit": money_in if money_in > 0 else None,
                "Credit": money_out if money_out > 0 else None,
                "ClosingBalance": Decimal("0"),
                "ImportedBy": created_by,
                "ImportedDate": now,
                "Remarks": remarks,
                "IsLocked": False,
                "SourceTable": "OthersBankCashTransaction",
                "SourceRecordID": daily_id,
                "SourceType": self.SOURCE_TYPE,
                "SourceID": source_id,
                "LedgerKind": ledger_kind,
            }
        )

    def get_entry(self, entry_id: int) -> dict:
        row = self.entry_repo.get_by_id(entry_id)
        if row is None or not row.IsActive:
            raise ValueError("Transaction not found.")
        return {
            "entry_id": row.EntryID,
            "voucher_no": row.VoucherNo,
            "work_date": row.WorkDate.isoformat() if row.WorkDate else "",
            "purpose": row.Purpose or "",
            "credit_account_id": row.CreditBankAccountID,
            "credit_account": self._account_label(row.CreditBankAccountID),
            "debit_account_id": row.DebitBankAccountID,
            "debit_account": self._account_label(row.DebitBankAccountID),
            "amount": float(row.Amount or 0),
            "remarks": row.Remarks or "",
        }

    def _find_daily(self, voucher_no: str):
        return db.session.scalars(
            select(JTCSDailyTransaction)
            .where(
                JTCSDailyTransaction.ReferenceNo == voucher_no,
                JTCSDailyTransaction.WorkType == self.WORK_TYPE,
                JTCSDailyTransaction.SubWorkType.like(f"{self.SUB_WORK_TYPE}%"),
            )
            .order_by(JTCSDailyTransaction.TransactionID.desc())
        ).first()

    def _remove_bank_legs(self, entry, daily=None) -> None:
        # Delete In (dependent) before Out so any SourceID links stay valid during flush.
        bank_ids = [
            bank_id
            for bank_id in (entry.InBankTransactionID, entry.OutBankTransactionID)
            if bank_id
        ]
        if not bank_ids:
            return

        if daily is None:
            daily = self._find_daily(entry.VoucherNo)

        # Clear every daily/payment FK that still points at these bank rows
        # (FK_JTCSDailyTransaction_Bank / FK_JTCSDailyTransactionPayment_Bank).
        db.session.execute(
            update(JTCSDailyTransaction)
            .where(JTCSDailyTransaction.BankTransactionID.in_(bank_ids))
            .values(BankTransactionID=None)
        )
        db.session.execute(
            update(JTCSDailyTransactionPayment)
            .where(JTCSDailyTransactionPayment.BankTransactionID.in_(bank_ids))
            .values(BankTransactionID=None)
        )
        if daily is not None:
            daily.BankTransactionID = None
        entry.OutBankTransactionID = None
        entry.InBankTransactionID = None
        db.session.flush()

        for bank_id in bank_ids:
            bank_row = self.bank_repo.get_by_id(bank_id)
            if bank_row is not None:
                self.bank_repo.delete(bank_row)
        db.session.flush()

    def save_entry(self, form: dict, *, created_by: str) -> BankCashSaveResult:
        work_date = self._date(form.get("WorkDate"))
        purpose = self._clean(form.get("Purpose"), 200)
        if not purpose:
            raise ValueError("Purpose is required.")

        try:
            credit_id = int(form.get("CreditBankAccountID") or 0)
            debit_id = int(form.get("DebitBankAccountID") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("Credit and Debit accounts are required.") from exc

        if credit_id <= 0 or debit_id <= 0:
            raise ValueError("Credit and Debit accounts are required.")
        if credit_id == debit_id:
            raise ValueError("Credit and Debit accounts must be different.")

        amount = self._decimal(form.get("Amount"))
        remarks = self._clean(form.get("Remarks"), 500)
        entry_id_raw = form.get("EntryID") or form.get("entry_id")
        entry_id = None
        if entry_id_raw not in (None, ""):
            try:
                entry_id = int(entry_id_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid entry id.") from exc

        credit_account = self.master_repo.resolve_bank_account_by_id(credit_id)
        debit_account = self.master_repo.resolve_bank_account_by_id(debit_id)

        def _write() -> BankCashSaveResult:
            existing = None
            if entry_id:
                existing = self.entry_repo.get_by_id(entry_id)
                if existing is None or not existing.IsActive:
                    raise ValueError("Transaction not found.")
                voucher_no = existing.VoucherNo
                daily = self._find_daily(voucher_no)
                self._remove_bank_legs(existing, daily)
            else:
                voucher_no = (
                    self._clean(form.get("VoucherNo"), 50)
                    or self.entry_repo.next_voucher_no(work_date)
                )
                daily = None

            if daily is None:
                daily = self.daily_repo.create(
                    {
                        "TransactionDate": work_date,
                        "WorkType": self.WORK_TYPE,
                        "SubWorkType": f"{self.SUB_WORK_TYPE} - {purpose}",
                        "CustomerID": None,
                        "CustomerName": None,
                        "ReferenceNo": voucher_no,
                        "Description": purpose,
                        "IncomeAmount": Decimal("0"),
                        "ExpenseAmount": Decimal("0"),
                        "SaleAmount": Decimal("0"),
                        "PurchaseAmount": Decimal("0"),
                        "GSTAmount": Decimal("0"),
                        "TDSAmount": Decimal("0"),
                        "TotalAmount": amount,
                        "PaymentModeID": None,
                        "PaymentSplitCount": 2,
                        "Status": "Posted",
                        "CreatedBy": created_by,
                        "CreatedDate": datetime.utcnow(),
                        "Remarks": remarks,
                    }
                )
            else:
                daily.TransactionDate = work_date
                daily.SubWorkType = f"{self.SUB_WORK_TYPE} - {purpose}"
                daily.Description = purpose
                daily.TotalAmount = amount
                daily.Remarks = remarks
                daily.ModifiedDate = datetime.utcnow()

            out_row = self._create_bank_leg(
                bank_account=credit_account,
                txn_date=work_date,
                description=f"{purpose} (Credit / Out)",
                money_in=Decimal("0"),
                money_out=amount,
                created_by=created_by,
                source_id=None,
                ledger_kind="CONTRA_OUT",
                remarks=f"[OBC] Voucher={voucher_no}|Leg=CREDIT",
                daily_id=daily.TransactionID,
            )
            in_row = self._create_bank_leg(
                bank_account=debit_account,
                txn_date=work_date,
                description=f"{purpose} (Debit / In)",
                money_in=amount,
                money_out=Decimal("0"),
                created_by=created_by,
                source_id=out_row.JtcsBankTransactionID,
                ledger_kind="CONTRA_IN",
                remarks=f"[OBC] Voucher={voucher_no}|Leg=DEBIT",
                daily_id=daily.TransactionID,
            )

            daily.BankTransactionID = out_row.JtcsBankTransactionID
            payload = {
                "WorkDate": work_date,
                "Purpose": purpose,
                "CreditBankAccountID": credit_id,
                "DebitBankAccountID": debit_id,
                "Amount": amount,
                "Remarks": remarks,
                "OutBankTransactionID": out_row.JtcsBankTransactionID,
                "InBankTransactionID": in_row.JtcsBankTransactionID,
            }
            if existing is not None:
                entry = self.entry_repo.update(existing, payload)
                message = "Other Bank/Cash transaction updated successfully."
            else:
                entry = self.entry_repo.create(
                    {
                        **payload,
                        "VoucherNo": voucher_no,
                        "CreatedBy": created_by,
                    }
                )
                message = "Other Bank/Cash transaction saved successfully."

            return BankCashSaveResult(
                entry_id=entry.EntryID,
                voucher_no=voucher_no,
                bank_transaction_ids=[
                    out_row.JtcsBankTransactionID,
                    in_row.JtcsBankTransactionID,
                ],
                message=message,
            )

        return persist(_write)

    def delete_entry(self, entry_id: int) -> str:
        def _write() -> str:
            entry = self.entry_repo.get_by_id(entry_id)
            if entry is None or not entry.IsActive:
                raise ValueError("Transaction not found.")

            daily = self._find_daily(entry.VoucherNo)
            self._remove_bank_legs(entry, daily)
            if daily is not None:
                self.daily_repo.delete(daily)

            self.entry_repo.soft_delete(entry)
            return "Transaction deleted successfully."

        return persist(_write)
