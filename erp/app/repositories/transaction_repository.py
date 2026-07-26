from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.transactions import (
    CustomerMaster,
    JTCSDailyTransaction,
    JTCSDailyTransactionPayment,
    JtcsBankAccountMaster,
    JtcsBankTransaction,
    PaymentModeMaster,
    WorkTypeMaster,
)


@dataclass
class BankAccountSnapshot:
    account_id: int
    bank_name: str
    masked_account_number: str


class DailyTransactionRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def create(self, data: dict) -> JTCSDailyTransaction:
        row = JTCSDailyTransaction(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def get_by_id(self, transaction_id: int) -> JTCSDailyTransaction | None:
        return self.session.get(JTCSDailyTransaction, transaction_id)

    def update_bank_link(self, daily: JTCSDailyTransaction, bank_id: int) -> None:
        daily.BankTransactionID = bank_id
        daily.ModifiedDate = datetime.utcnow()
        self.session.flush()

    def delete(self, daily: JTCSDailyTransaction) -> None:
        self.session.delete(daily)


class BankTransactionRepository:
    SOURCE_TABLE = "JTCSDailyTransaction"

    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def create(self, data: dict) -> JtcsBankTransaction:
        row = JtcsBankTransaction(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def get_by_id(self, bank_id: int) -> JtcsBankTransaction | None:
        return self.session.get(JtcsBankTransaction, bank_id)

    def find_by_daily_id(self, daily_id: int) -> JtcsBankTransaction | None:
        rows = self.find_all_by_daily_id(daily_id)
        return rows[0] if rows else None

    def find_all_by_daily_id(self, daily_id: int) -> list[JtcsBankTransaction]:
        stmt = (
            select(JtcsBankTransaction)
            .where(
                JtcsBankTransaction.SourceTable == self.SOURCE_TABLE,
                or_(
                    JtcsBankTransaction.SourceRecordID == daily_id,
                    JtcsBankTransaction.SourceID == daily_id,
                ),
            )
            .order_by(
                JtcsBankTransaction.PaymentSequence.asc(),
                JtcsBankTransaction.JtcsBankTransactionID.asc(),
            )
        )
        rows = list(self.session.scalars(stmt).all())
        seen = {row.JtcsBankTransactionID for row in rows}

        payment_bank_ids = self.session.scalars(
            select(JTCSDailyTransactionPayment.BankTransactionID)
            .where(JTCSDailyTransactionPayment.TransactionID == daily_id)
            .where(JTCSDailyTransactionPayment.BankTransactionID.isnot(None))
        ).all()
        for bank_id in payment_bank_ids:
            if bank_id in seen:
                continue
            bank_row = self.session.get(JtcsBankTransaction, bank_id)
            if bank_row is not None:
                rows.append(bank_row)
                seen.add(bank_row.JtcsBankTransactionID)

        if rows:
            rows.sort(
                key=lambda row: (
                    row.PaymentSequence or 0,
                    row.JtcsBankTransactionID,
                )
            )
            return rows

        fallback = self.session.scalars(
            select(JtcsBankTransaction)
            .join(
                JTCSDailyTransaction,
                JtcsBankTransaction.JtcsBankTransactionID == JTCSDailyTransaction.BankTransactionID,
            )
            .where(JTCSDailyTransaction.TransactionID == daily_id)
        ).all()
        return list(fallback)

    def find_contra_pair(self, contra_ref: str) -> list[JtcsBankTransaction]:
        stmt = select(JtcsBankTransaction).where(JtcsBankTransaction.Remarks.like(f"%{contra_ref}%"))
        return list(self.session.scalars(stmt).all())

    def delete(self, bank_row: JtcsBankTransaction) -> None:
        self.session.delete(bank_row)


class DailyTransactionPaymentRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def create(self, data: dict) -> JTCSDailyTransactionPayment:
        data.setdefault("CreatedDate", datetime.utcnow())
        row = JTCSDailyTransactionPayment(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def list_by_transaction(self, transaction_id: int) -> list[JTCSDailyTransactionPayment]:
        stmt = (
            select(JTCSDailyTransactionPayment)
            .where(JTCSDailyTransactionPayment.TransactionID == transaction_id)
            .order_by(JTCSDailyTransactionPayment.PaymentSequence.asc())
        )
        return list(self.session.scalars(stmt).all())

    def delete_by_transaction(self, transaction_id: int) -> None:
        for row in self.list_by_transaction(transaction_id):
            self.session.delete(row)
        self.session.flush()


class MasterRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def get_payment_mode(self, payment_mode_id: int) -> PaymentModeMaster | None:
        return self.session.get(PaymentModeMaster, payment_mode_id)

    def list_payment_modes(self) -> list[PaymentModeMaster]:
        stmt = (
            select(PaymentModeMaster)
            .where(PaymentModeMaster.IsActive == True)  # noqa: E712
            .order_by(PaymentModeMaster.PaymentModeName)
        )
        return list(self.session.scalars(stmt).all())

    def list_active_bank_accounts(self) -> list[JtcsBankAccountMaster]:
        self.session.execute(
            text(
                """
                IF COL_LENGTH(N'dbo.JtcsBankAccountMaster', N'DisplayOrder') IS NULL
                BEGIN
                    ALTER TABLE dbo.JtcsBankAccountMaster
                    ADD DisplayOrder INT NOT NULL
                        CONSTRAINT DF_JtcsBankAccountMaster_DisplayOrder DEFAULT (100);
                END
                """
            )
        )
        self.session.commit()
        stmt = (
            select(JtcsBankAccountMaster)
            .where(JtcsBankAccountMaster.ActiveStatus == True)  # noqa: E712
            .order_by(
                JtcsBankAccountMaster.DisplayOrder,
                JtcsBankAccountMaster.BankName,
                JtcsBankAccountMaster.JtcsBankAccountID,
            )
        )
        return list(self.session.scalars(stmt).all())

    @staticmethod
    def _stamp_account_number(account: JtcsBankAccountMaster) -> str:
        return (account.AccountNumber or account.MaskedAccountNumber or "").strip()

    @staticmethod
    def _stamp_account_display(account: JtcsBankAccountMaster) -> str | None:
        """Display label for Stamp Activity payment mode from bank master account number."""
        bank_name = (account.BankName or "").strip()
        account_number = MasterRepository._stamp_account_number(account)

        if bank_name.lower() == "cash" or account_number.lower() == "cash":
            return "Cash"
        if account_number and account_number.upper() != "NA":
            return account_number
        if bank_name:
            return bank_name
        return None

    @staticmethod
    def _is_primary_stamp_account(account: JtcsBankAccountMaster) -> bool:
        primary_display = "58250200000396"
        account_number = MasterRepository._stamp_account_number(account)
        digits = "".join(ch for ch in account_number if ch.isdigit())
        return account_number == primary_display or digits.endswith("0396")

    def list_stamp_bank_payment_modes(self, *, qr_bill_received_only: bool = True) -> list[dict]:
        """Payment / receive account options from JtcsBankAccountMaster.

        By default only accounts with QR/Bill Received = true are listed
        (used by Payment Received / Make Payment flows). Pass
        qr_bill_received_only=False for unfiltered lists.
        Bank/Cash Transactions uses a separate account list and is not affected.
        """
        from app.repositories.bank_master_repository import BankMasterRepository

        BankMasterRepository(self.session).ensure_schema()
        items: list[dict] = []
        for account in self.list_active_bank_accounts():
            if qr_bill_received_only and not bool(getattr(account, "QrBillReceived", False)):
                continue
            account_number = self._stamp_account_number(account)
            display = (
                self._stamp_account_display(account)
                or (account.BankName or "").strip()
                or account_number
                or str(account.JtcsBankAccountID)
            )
            items.append(
                {
                    "bank_account_id": account.JtcsBankAccountID,
                    "bank_name": account.BankName,
                    "account_number": account_number,
                    "masked_account_number": account.MaskedAccountNumber or account_number,
                    "display_account_number": display,
                    "display_order": int(getattr(account, "DisplayOrder", 100) or 100),
                    "qr_bill_received": bool(getattr(account, "QrBillReceived", False)),
                }
            )
        items.sort(
            key=lambda row: (
                int(row.get("display_order") or 100),
                (row["bank_name"] or "").lower(),
                row["display_account_number"] or "",
            )
        )
        return items

    def get_bank_account(self, account_id: int) -> JtcsBankAccountMaster | None:
        return self.session.get(JtcsBankAccountMaster, account_id)

    def resolve_payment_mode_for_bank_account(self, bank_account_id: int) -> int:
        account = self.get_bank_account(bank_account_id)
        if account is None:
            raise ValueError("Bank account not found.")

        stmt = (
            select(PaymentModeMaster)
            .where(PaymentModeMaster.BankAccountID == bank_account_id)
            .where(PaymentModeMaster.IsActive == True)  # noqa: E712
            .limit(1)
        )
        mode = self.session.scalars(stmt).first()
        if mode:
            return mode.PaymentModeID

        label = (account.BankName or account.AccountNumber or f"Bank {bank_account_id}").strip()
        linked = PaymentModeMaster(
            PaymentModeName=label[:100],
            BankAccountID=bank_account_id,
            IsActive=True,
        )
        self.session.add(linked)
        self.session.flush()
        return linked.PaymentModeID

    def resolve_bank_account_by_id(self, bank_account_id: int) -> BankAccountSnapshot:
        account = self.get_bank_account(bank_account_id)
        if account is None:
            raise ValueError("Bank account not found.")

        account_number = self._stamp_account_number(account)
        masked = (account.MaskedAccountNumber or "").strip()
        if account.BankName.strip().lower() == "cash" or account_number.lower() == "cash":
            masked = masked or account_number or "CASH"
        elif not masked:
            masked = account_number or "NA"

        return BankAccountSnapshot(
            account_id=account.JtcsBankAccountID,
            bank_name=account.BankName,
            masked_account_number=masked,
        )

    def resolve_bank_account(self, payment_mode_id: int) -> BankAccountSnapshot:
        mode = self.get_payment_mode(payment_mode_id)
        if mode is None:
            raise ValueError("Payment mode not found.")

        if mode.BankAccountID:
            account = self.get_bank_account(mode.BankAccountID)
            if account is None:
                raise ValueError("Linked bank account not found.")
            return BankAccountSnapshot(
                account_id=account.JtcsBankAccountID,
                bank_name=account.BankName,
                masked_account_number=account.MaskedAccountNumber or "NA",
            )

        if mode.PaymentModeName.lower() == "cash":
            account = self.session.scalars(
                select(JtcsBankAccountMaster)
                .where(JtcsBankAccountMaster.BankName == "Cash")
                .where(JtcsBankAccountMaster.ActiveStatus == True)  # noqa: E712
                .limit(1)
            ).first()
            if account:
                return BankAccountSnapshot(
                    account_id=account.JtcsBankAccountID,
                    bank_name=account.BankName,
                    masked_account_number=account.MaskedAccountNumber or "CASH",
                )
            return BankAccountSnapshot(
                account_id=0,
                bank_name="Cash",
                masked_account_number="CASH",
            )

        return BankAccountSnapshot(
            account_id=0,
            bank_name=mode.PaymentModeName,
            masked_account_number="NA",
        )

    def list_customers(self, limit: int = 500) -> list[CustomerMaster]:
        stmt = select(CustomerMaster).order_by(CustomerMaster.CustomerName).limit(limit)
        return list(self.session.scalars(stmt).all())

    @staticmethod
    def _normalize_mobile(mobile: str) -> str:
        digits = "".join(ch for ch in (mobile or "") if ch.isdigit())
        return digits[-10:] if len(digits) >= 10 else digits

    def list_customers_by_mobile(self, mobile: str) -> list[CustomerMaster]:
        normalized = self._normalize_mobile(mobile)
        if len(normalized) != 10:
            return []
        stmt = (
            select(CustomerMaster)
            .where(CustomerMaster.MobileNumber == normalized)
            .order_by(CustomerMaster.CustomerName)
        )
        return list(self.session.scalars(stmt).all())

    def find_customer_by_name_and_mobile(self, name: str, mobile: str) -> CustomerMaster | None:
        normalized_name = (name or "").strip()
        normalized_mobile = self._normalize_mobile(mobile)
        if not normalized_name or len(normalized_mobile) != 10:
            return None
        stmt = (
            select(CustomerMaster)
            .where(CustomerMaster.MobileNumber == normalized_mobile)
            .where(func.lower(CustomerMaster.CustomerName) == normalized_name.lower())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def find_or_create_customer(self, name: str, mobile: str) -> CustomerMaster:
        normalized_name = (name or "").strip()
        normalized_mobile = self._normalize_mobile(mobile)
        if not normalized_name:
            raise ValueError("Customer name is required.")
        if len(normalized_mobile) != 10:
            raise ValueError("Valid 10-digit mobile number is required.")

        existing = self.find_customer_by_name_and_mobile(normalized_name, normalized_mobile)
        if existing:
            return existing

        customer = CustomerMaster(
            CustomerName=normalized_name,
            MobileNumber=normalized_mobile,
            CustomerStatus="Active",
            CreatedDate=datetime.utcnow(),
        )
        self.session.add(customer)
        self.session.flush()
        return customer

    def list_work_types(self) -> list[WorkTypeMaster]:
        stmt = (
            select(WorkTypeMaster)
            .where(WorkTypeMaster.ActiveStatus == True)  # noqa: E712
            .order_by(WorkTypeMaster.WorkTypeName, WorkTypeMaster.SubWorkType)
        )
        return list(self.session.scalars(stmt).all())

    def list_sub_works_for_parent(self, work_type_name: str) -> list[WorkTypeMaster]:
        name = (work_type_name or "").strip()
        if not name:
            return []
        stmt = (
            select(WorkTypeMaster)
            .where(WorkTypeMaster.ActiveStatus == True)  # noqa: E712
            .where(WorkTypeMaster.WorkTypeName == name)
            .order_by(WorkTypeMaster.SubWorkType)
        )
        return list(self.session.scalars(stmt).all())

    def get_work_type(self, work_type_id: int) -> WorkTypeMaster | None:
        return self.session.get(WorkTypeMaster, work_type_id)

    def get_customer(self, customer_id: int) -> CustomerMaster | None:
        return self.session.get(CustomerMaster, customer_id)
