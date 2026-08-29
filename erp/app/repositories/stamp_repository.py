from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.exceptions.stamp_exceptions import ExistingStampRecord
from app.models.bank_cash import OthersBankCashTransaction
from app.models.stamp import StampMaster, StampOcrImage
from app.models.transactions import (
    CustomerMaster,
    JTCSDailyTransaction,
    JTCSDailyTransactionPayment,
    JtcsBankAccountMaster,
    JtcsBankTransaction,
)
from app.utils.shcil_bank_accounts import stamp_purchase_account_id

_STAMP_SCHEMA_READY = False


@dataclass
class StampGridFilters:
    date_from: date | None = None
    date_to: date | None = None
    certificate: str = ""
    mobile: str = ""
    customer: str = ""


class StampRepository:
    @staticmethod
    def _display_name(*parts: str) -> str:
        for part in parts:
            text = re.sub(r"^[\s:>|]+", "", (part or "").strip())
            if text:
                return text
        return ""

    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self.ensure_schema()

    def ensure_schema(self) -> None:
        global _STAMP_SCHEMA_READY
        if _STAMP_SCHEMA_READY:
            return
        self.session.execute(
            text(
                """
                IF COL_LENGTH(N'dbo.StampMaster', N'MobileNumber') IS NULL
                    ALTER TABLE dbo.StampMaster ADD MobileNumber NVARCHAR(15) NULL;
                """
            )
        )
        self.session.commit()
        _STAMP_SCHEMA_READY = True

    def get_by_id(self, stamp_id: int) -> StampMaster | None:
        return self.session.get(StampMaster, stamp_id)

    def get_by_certificate_number(
        self, certificate_number: str, *, active_only: bool = True
    ) -> StampMaster | None:
        normalized = (certificate_number or "").strip()
        stmt = select(StampMaster).where(StampMaster.CertificateNumber == normalized)
        if active_only:
            stmt = stmt.where(StampMaster.IsActive == True)  # noqa: E712
        return self.session.scalars(stmt).first()

    def find_any_by_certificate_number(self, certificate_number: str) -> StampMaster | None:
        return self.get_by_certificate_number(certificate_number, active_only=False)

    def certificate_exists(self, certificate_number: str, *, exclude_id: int | None = None) -> bool:
        return self.find_existing(certificate_number, exclude_id=exclude_id) is not None

    def find_existing(
        self, certificate_number: str, *, exclude_id: int | None = None
    ) -> ExistingStampRecord | None:
        stamp = self.get_by_certificate_number(certificate_number)
        if stamp is None:
            return None
        if exclude_id is not None and stamp.StampID == exclude_id:
            return None

        daily = self.session.scalars(
            select(JTCSDailyTransaction)
            .where(JTCSDailyTransaction.StampID == stamp.StampID)
            .order_by(JTCSDailyTransaction.TransactionID.desc())
        ).first()

        txn_date = daily.TransactionDate if daily else stamp.CreatedDate.date()
        return ExistingStampRecord(
            stamp_id=stamp.StampID,
            transaction_id=daily.TransactionID if daily else None,
            customer_name=daily.CustomerName if daily else None,
            transaction_date=txn_date.isoformat() if isinstance(txn_date, date) else str(txn_date)[:10],
            certificate_number=stamp.CertificateNumber,
        )

    def update_stamp(self, stamp: StampMaster, data: dict, *, modified_by: str) -> StampMaster:
        preserve = {"CreatedBy", "CreatedDate"}
        for key, value in data.items():
            if key not in preserve:
                setattr(stamp, key, value)
        stamp.ModifiedBy = modified_by
        stamp.ModifiedDate = datetime.utcnow()
        self.session.flush()
        return stamp

    def reactivate_or_create(self, data: dict, *, modified_by: str) -> tuple[StampMaster, bool]:
        """Return (stamp, created_new). Reuses inactive orphan with same certificate number."""
        certificate_number = (data.get("CertificateNumber") or "").strip()
        existing = self.find_any_by_certificate_number(certificate_number)
        if existing is None:
            return self.create(data), True
        if existing.IsActive:
            raise ValueError("Active certificate already exists.")

        preserve = {"CreatedBy", "CreatedDate"}
        for key, value in data.items():
            if key not in preserve:
                setattr(existing, key, value)
        existing.IsActive = True
        existing.ModifiedBy = modified_by
        existing.ModifiedDate = datetime.utcnow()
        self.session.flush()
        return existing, False

    def create(self, data: dict) -> StampMaster:
        now = datetime.utcnow()
        data.setdefault("CreatedDate", now)
        row = StampMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def list_active(self, limit: int = 5000) -> list[StampMaster]:
        stmt = (
            select(StampMaster)
            .where(StampMaster.IsActive == True)  # noqa: E712
            .order_by(StampMaster.CreatedDate.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def list_daily_for_stamp(self, stamp_id: int) -> list[JTCSDailyTransaction]:
        stmt = (
            select(JTCSDailyTransaction)
            .where(JTCSDailyTransaction.StampID == stamp_id)
            .order_by(JTCSDailyTransaction.TransactionID.asc())
        )
        return list(self.session.scalars(stmt).all())

    def get_daily_for_stamp(self, stamp_id: int) -> JTCSDailyTransaction | None:
        stmt = (
            select(JTCSDailyTransaction)
            .where(JTCSDailyTransaction.StampID == stamp_id)
            .order_by(JTCSDailyTransaction.TransactionID.desc())
        )
        return self.session.scalars(stmt).first()

    def search_by_certificate(self, query: str, limit: int = 100) -> list[dict]:
        normalized = self._normalize_certificate_query(query)
        if not normalized:
            return []

        stmt = (
            select(StampMaster, JTCSDailyTransaction, JtcsBankTransaction)
            .outerjoin(JTCSDailyTransaction, JTCSDailyTransaction.StampID == StampMaster.StampID)
            .outerjoin(
                JtcsBankTransaction,
                JtcsBankTransaction.JtcsBankTransactionID == JTCSDailyTransaction.BankTransactionID,
            )
            .where(StampMaster.IsActive == True)  # noqa: E712
            .where(
                func.replace(func.upper(StampMaster.CertificateNumber), " ", "").like(f"%{normalized}%")
            )
            .order_by(StampMaster.CreatedDate.desc(), JTCSDailyTransaction.TransactionID.desc())
            .limit(limit)
        )

        seen: set[int] = set()
        rows: list[dict] = []
        for stamp, daily, bank in self.session.execute(stmt).all():
            if stamp.StampID in seen:
                continue
            seen.add(stamp.StampID)
            payment_mode = ""
            bank_account_id = None
            if daily is not None:
                payment_lines = self.session.scalars(
                    select(JTCSDailyTransactionPayment)
                    .where(JTCSDailyTransactionPayment.TransactionID == daily.TransactionID)
                    .order_by(JTCSDailyTransactionPayment.PaymentSequence.asc())
                ).all()
                if payment_lines:
                    bank_account_id = payment_lines[0].BankAccountID
                    labels: list[str] = []
                    for line in payment_lines:
                        account = self.session.get(JtcsBankAccountMaster, line.BankAccountID)
                        if account is not None:
                            labels.append(
                                (account.AccountNumber or account.MaskedAccountNumber or account.BankName or "").strip()
                            )
                        else:
                            labels.append(str(line.BankAccountID))
                    payment_mode = " + ".join(label for label in labels if label)
                elif bank is not None:
                    bank_account_id = bank.JtcsBankAccountID
                    payment_mode = (bank.MaskedAccountNumber or bank.BankName or "").strip()
            rows.append(
                {
                    "stamp_id": stamp.StampID,
                    "transaction_id": daily.TransactionID if daily else None,
                    "bank_transaction_id": daily.BankTransactionID if daily else None,
                    "certificate_number": stamp.CertificateNumber,
                    "certificate_date": stamp.CertificateIssuedDate.isoformat()
                    if stamp.CertificateIssuedDate
                    else "",
                    "first_party": stamp.FirstPartyName or "",
                    "stamp_duty_amount": str(stamp.StampDutyAmount or ""),
                    "sale_amount": str(daily.SaleAmount if daily else ""),
                    "transaction_date": daily.TransactionDate.isoformat()
                    if daily and daily.TransactionDate
                    else "",
                    "payment_mode": payment_mode,
                    "bank_account_id": bank_account_id,
                    "customer_name": self._display_name(
                        daily.CustomerName if daily else "",
                        stamp.StampDutyPaidBy,
                        stamp.FirstPartyName,
                    ),
                    "created_by": stamp.CreatedBy,
                }
            )
        return rows

    @staticmethod
    def _normalize_certificate_query(value: str) -> str:
        """Uppercase + strip spaces so UI / OCR spacing variants still match."""
        return "".join((value or "").strip().upper().split())

    def _apply_transaction_filters(
        self,
        stmt,
        filters: StampGridFilters,
        *,
        apply_dates: bool = True,
    ):
        cert = self._normalize_certificate_query(filters.certificate)
        customer = (filters.customer or "").strip()
        mobile = "".join(ch for ch in (filters.mobile or "") if ch.isdigit())
        # Certificate / customer / mobile search must find the row anywhere in JTCS
        # (period must not hide an integrated stamp).
        if cert:
            stmt = stmt.where(
                func.replace(func.upper(StampMaster.CertificateNumber), " ", "").like(f"%{cert}%")
            )
        elif apply_dates and not customer and not mobile:
            if filters.date_from:
                stmt = stmt.where(JTCSDailyTransaction.TransactionDate >= filters.date_from)
            if filters.date_to:
                stmt = stmt.where(JTCSDailyTransaction.TransactionDate <= filters.date_to)
        if customer:
            needle = f"%{customer}%"
            stmt = stmt.where(
                or_(
                    StampMaster.FirstPartyName.like(needle),
                    StampMaster.SecondPartyName.like(needle),
                    StampMaster.PurchasedBy.like(needle),
                    StampMaster.StampDutyPaidBy.like(needle),
                    JTCSDailyTransaction.CustomerName.like(needle),
                )
            )
        return stmt

    def _grid_base_stmt(self, filters: StampGridFilters):
        stmt = (
            select(StampMaster, JTCSDailyTransaction)
            .outerjoin(JTCSDailyTransaction, JTCSDailyTransaction.StampID == StampMaster.StampID)
            .outerjoin(CustomerMaster, CustomerMaster.CustomerID == JTCSDailyTransaction.CustomerID)
            .where(StampMaster.IsActive == True)  # noqa: E712
        )
        stmt = self._apply_transaction_filters(stmt, filters)
        mobile = "".join(ch for ch in (filters.mobile or "") if ch.isdigit())
        if mobile:
            needle = f"%{mobile}%"
            stmt = stmt.where(
                or_(
                    CustomerMaster.MobileNumber.like(needle),
                    StampMaster.MobileNumber.like(needle),
                )
            )
        return stmt

    def _cash_account_match(self):
        return or_(
            func.lower(func.coalesce(JtcsBankAccountMaster.BankName, "")) == "cash",
            func.lower(func.coalesce(JtcsBankAccountMaster.AccountNumber, "")) == "cash",
            func.lower(func.coalesce(JtcsBankAccountMaster.MaskedAccountNumber, "")) == "cash",
        )

    @staticmethod
    def _account_is_cash(account: JtcsBankAccountMaster | None) -> bool:
        if account is None:
            return False
        return (
            (account.BankName or "").strip().lower() == "cash"
            or (account.AccountNumber or "").strip().lower() == "cash"
            or (account.MaskedAccountNumber or "").strip().lower() == "cash"
        )

    def _payment_account_label(
        self,
        account: JtcsBankAccountMaster | None = None,
        bank: JtcsBankTransaction | None = None,
    ) -> str:
        bank_name = (account.BankName if account is not None else "") or (
            bank.BankName if bank is not None else ""
        )
        account_number = ""
        if account is not None:
            account_number = (account.AccountNumber or account.MaskedAccountNumber or "").strip()
        if not account_number and bank is not None:
            account_number = (bank.MaskedAccountNumber or "").strip()
        if self._account_is_cash(account) or (bank_name or "").strip().lower() == "cash" or (
            account_number or ""
        ).strip().lower() == "cash":
            return "Cash"
        digits = "".join(ch for ch in account_number if ch.isdigit())
        if len(digits) >= 4:
            return digits[-4:]
        if digits:
            return digits
        return account_number or (bank_name or "").strip()

    def _bank_daily_join(self):
        return or_(
            JtcsBankTransaction.SourceRecordID == JTCSDailyTransaction.TransactionID,
            JtcsBankTransaction.SourceID == JTCSDailyTransaction.TransactionID,
        )

    def _sum_bank_payments(self, filters: StampGridFilters, *, cash_only: bool = False) -> Decimal:
        stmt = (
            select(func.coalesce(func.sum(JtcsBankTransaction.Debit), 0))
            .select_from(JtcsBankTransaction)
            .join(JTCSDailyTransaction, self._bank_daily_join())
            .join(StampMaster, JTCSDailyTransaction.StampID == StampMaster.StampID)
            .where(JtcsBankTransaction.SourceTable == "JTCSDailyTransaction")
            .where(StampMaster.IsActive == True)  # noqa: E712
        )
        if cash_only:
            stmt = stmt.join(
                JtcsBankAccountMaster,
                JtcsBankAccountMaster.JtcsBankAccountID == JtcsBankTransaction.JtcsBankAccountID,
            ).where(self._cash_account_match())
        stmt = self._apply_transaction_filters(stmt, filters)
        return Decimal(str(self.session.scalar(stmt) or 0))

    def _shcil_stamp_account_match(self):
        account_id = stamp_purchase_account_id(self.session)
        if account_id is None:
            return JtcsBankAccountMaster.JtcsBankAccountID == 0
        return JtcsBankAccountMaster.JtcsBankAccountID == account_id

    def _sum_shcil_stamp_deposits(self, filters: StampGridFilters) -> Decimal:
        """Jama (Debit/In) into SHCILStamp for the period.

        Uses OthersBankCashTransaction deposits plus any SHCILStamp bank CONTRA_IN
        legs that are not already linked from those OBC rows (keeps admin/stamp aligned).
        """
        obc_stmt = (
            select(func.coalesce(func.sum(OthersBankCashTransaction.Amount), 0))
            .select_from(OthersBankCashTransaction)
            .join(
                JtcsBankAccountMaster,
                JtcsBankAccountMaster.JtcsBankAccountID
                == OthersBankCashTransaction.DebitBankAccountID,
            )
            .where(OthersBankCashTransaction.IsActive == True)  # noqa: E712
            .where(self._shcil_stamp_account_match())
        )
        if filters.date_from:
            obc_stmt = obc_stmt.where(OthersBankCashTransaction.WorkDate >= filters.date_from)
        if filters.date_to:
            obc_stmt = obc_stmt.where(OthersBankCashTransaction.WorkDate <= filters.date_to)
        obc_total = Decimal(str(self.session.scalar(obc_stmt) or 0))

        linked_in_ids = select(OthersBankCashTransaction.InBankTransactionID).where(
            OthersBankCashTransaction.IsActive == True,  # noqa: E712
            OthersBankCashTransaction.InBankTransactionID.isnot(None),
        )

        bank_stmt = (
            select(func.coalesce(func.sum(JtcsBankTransaction.Debit), 0))
            .select_from(JtcsBankTransaction)
            .join(
                JtcsBankAccountMaster,
                JtcsBankAccountMaster.JtcsBankAccountID == JtcsBankTransaction.JtcsBankAccountID,
            )
            .where(self._shcil_stamp_account_match())
            .where(func.coalesce(JtcsBankTransaction.Debit, 0) > 0)
            .where(
                or_(
                    func.upper(func.coalesce(JtcsBankTransaction.LedgerKind, "")) == "CONTRA_IN",
                    func.upper(func.coalesce(JtcsBankTransaction.SourceTable, ""))
                    == "OTHERSBANKCASHTRANSACTION",
                    func.upper(func.coalesce(JtcsBankTransaction.SourceType, ""))
                    == "OTHERS_BANK_CASH",
                )
            )
            .where(JtcsBankTransaction.JtcsBankTransactionID.not_in(linked_in_ids))
        )
        if filters.date_from:
            bank_stmt = bank_stmt.where(JtcsBankTransaction.TransactionDate >= filters.date_from)
        if filters.date_to:
            bank_stmt = bank_stmt.where(JtcsBankTransaction.TransactionDate <= filters.date_to)
        bank_only_total = Decimal(str(self.session.scalar(bank_stmt) or 0))

        return obc_total + bank_only_total

    def list_shcil_stamp_deposit_rows(self, filters: StampGridFilters, *, limit: int = 500) -> list[dict]:
        """Deposit (jama) rows into SHCILStamp for period card drill-down."""
        stmt = (
            select(OthersBankCashTransaction, JtcsBankAccountMaster)
            .select_from(OthersBankCashTransaction)
            .join(
                JtcsBankAccountMaster,
                JtcsBankAccountMaster.JtcsBankAccountID
                == OthersBankCashTransaction.DebitBankAccountID,
            )
            .where(OthersBankCashTransaction.IsActive == True)  # noqa: E712
            .where(self._shcil_stamp_account_match())
            .order_by(OthersBankCashTransaction.WorkDate.desc(), OthersBankCashTransaction.EntryID.desc())
            .limit(limit)
        )
        if filters.date_from:
            stmt = stmt.where(OthersBankCashTransaction.WorkDate >= filters.date_from)
        if filters.date_to:
            stmt = stmt.where(OthersBankCashTransaction.WorkDate <= filters.date_to)

        rows: list[dict] = []
        linked_in_ids: set[int] = set()
        for entry, debit_account in self.session.execute(stmt).all():
            if entry.InBankTransactionID:
                linked_in_ids.add(int(entry.InBankTransactionID))
            credit_account = self.session.get(JtcsBankAccountMaster, entry.CreditBankAccountID)
            rows.append(
                {
                    "entry_id": entry.EntryID,
                    "voucher_no": entry.VoucherNo or "",
                    "work_date": entry.WorkDate.isoformat() if entry.WorkDate else "",
                    "purpose": entry.Purpose or "",
                    "credit_account": (
                        (
                            credit_account.AccountNumber
                            or credit_account.MaskedAccountNumber
                            or credit_account.BankName
                            or ""
                        ).strip()
                        if credit_account is not None
                        else ""
                    ),
                    "debit_account": (
                        debit_account.AccountNumber
                        or debit_account.MaskedAccountNumber
                        or debit_account.BankName
                        or "SHCILStamp"
                    ).strip(),
                    "amount": str(entry.Amount or "0"),
                    "remarks": entry.Remarks or "",
                    "entered_by": entry.CreatedBy or "",
                }
            )

        linked_subq = select(OthersBankCashTransaction.InBankTransactionID).where(
            OthersBankCashTransaction.IsActive == True,  # noqa: E712
            OthersBankCashTransaction.InBankTransactionID.isnot(None),
        )

        if len(rows) < limit:
            bank_stmt = (
                select(JtcsBankTransaction, JtcsBankAccountMaster)
                .select_from(JtcsBankTransaction)
                .join(
                    JtcsBankAccountMaster,
                    JtcsBankAccountMaster.JtcsBankAccountID == JtcsBankTransaction.JtcsBankAccountID,
                )
                .where(self._shcil_stamp_account_match())
                .where(func.coalesce(JtcsBankTransaction.Debit, 0) > 0)
                .where(
                    or_(
                        func.upper(func.coalesce(JtcsBankTransaction.LedgerKind, "")) == "CONTRA_IN",
                        func.upper(func.coalesce(JtcsBankTransaction.SourceTable, ""))
                        == "OTHERSBANKCASHTRANSACTION",
                        func.upper(func.coalesce(JtcsBankTransaction.SourceType, ""))
                        == "OTHERS_BANK_CASH",
                    )
                )
                .where(JtcsBankTransaction.JtcsBankTransactionID.not_in(linked_subq))
                .order_by(
                    JtcsBankTransaction.TransactionDate.desc(),
                    JtcsBankTransaction.JtcsBankTransactionID.desc(),
                )
                .limit(limit - len(rows))
            )
            if filters.date_from:
                bank_stmt = bank_stmt.where(JtcsBankTransaction.TransactionDate >= filters.date_from)
            if filters.date_to:
                bank_stmt = bank_stmt.where(JtcsBankTransaction.TransactionDate <= filters.date_to)

            for bank, debit_account in self.session.execute(bank_stmt).all():
                if bank.JtcsBankTransactionID in linked_in_ids:
                    continue
                rows.append(
                    {
                        "entry_id": bank.JtcsBankTransactionID,
                        "voucher_no": f"BT-{bank.JtcsBankTransactionID}",
                        "work_date": bank.TransactionDate.isoformat() if bank.TransactionDate else "",
                        "purpose": (bank.Description or "Bank Transfer").strip(),
                        "credit_account": "",
                        "debit_account": (
                            debit_account.AccountNumber
                            or debit_account.MaskedAccountNumber
                            or debit_account.BankName
                            or "SHCILStamp"
                        ).strip(),
                        "amount": str(bank.Debit or "0"),
                        "remarks": bank.Remarks or "",
                        "entered_by": bank.ImportedBy or "",
                    }
                )

        rows.sort(key=lambda r: (r.get("work_date") or "", r.get("voucher_no") or ""), reverse=True)
        return rows[:limit]

    def period_summary(self, filters: StampGridFilters) -> dict:
        sale_stmt = (
            select(
                func.count(func.distinct(JTCSDailyTransaction.StampID)),
                func.coalesce(func.sum(JTCSDailyTransaction.SaleAmount), 0),
            )
            .select_from(JTCSDailyTransaction)
            .join(StampMaster, JTCSDailyTransaction.StampID == StampMaster.StampID)
            .where(StampMaster.IsActive == True)  # noqa: E712
        )
        sale_stmt = self._apply_transaction_filters(sale_stmt, filters)
        stamp_count, sale_total = self.session.execute(sale_stmt).one()

        duty_stmt = (
            select(func.coalesce(func.sum(StampMaster.StampDutyAmount), 0))
            .select_from(JTCSDailyTransaction)
            .join(StampMaster, JTCSDailyTransaction.StampID == StampMaster.StampID)
            .where(StampMaster.IsActive == True)  # noqa: E712
        )
        duty_stmt = self._apply_transaction_filters(duty_stmt, filters)
        duty_total = Decimal(str(self.session.scalar(duty_stmt) or 0))

        payment_base = (
            select(func.coalesce(func.sum(JTCSDailyTransactionPayment.Amount), 0))
            .select_from(JTCSDailyTransactionPayment)
            .join(
                JTCSDailyTransaction,
                JTCSDailyTransactionPayment.TransactionID == JTCSDailyTransaction.TransactionID,
            )
            .join(StampMaster, JTCSDailyTransaction.StampID == StampMaster.StampID)
            .where(StampMaster.IsActive == True)  # noqa: E712
        )
        payment_base = self._apply_transaction_filters(payment_base, filters)
        payment_received = Decimal(str(self.session.scalar(payment_base) or 0))

        cash_stmt = (
            select(func.coalesce(func.sum(JTCSDailyTransactionPayment.Amount), 0))
            .select_from(JTCSDailyTransactionPayment)
            .join(
                JTCSDailyTransaction,
                JTCSDailyTransactionPayment.TransactionID == JTCSDailyTransaction.TransactionID,
            )
            .join(StampMaster, JTCSDailyTransaction.StampID == StampMaster.StampID)
            .join(
                JtcsBankAccountMaster,
                JtcsBankAccountMaster.JtcsBankAccountID == JTCSDailyTransactionPayment.BankAccountID,
            )
            .where(StampMaster.IsActive == True)  # noqa: E712
            .where(self._cash_account_match())
        )
        cash_stmt = self._apply_transaction_filters(cash_stmt, filters)
        received_cash = Decimal(str(self.session.scalar(cash_stmt) or 0))

        if payment_received <= 0:
            payment_received = self._sum_bank_payments(filters, cash_only=False)
            received_cash = self._sum_bank_payments(filters, cash_only=True)

        received_non_cash = payment_received - received_cash
        if received_non_cash < 0:
            received_non_cash = Decimal("0")

        shcil_stamp_deposit = self._sum_shcil_stamp_deposits(filters)

        def _money(value) -> str:
            return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))

        return {
            "stamp_count": int(stamp_count or 0),
            "total_sale_amount": _money(sale_total),
            "payment_received_amount": _money(duty_total),
            "received_cash": _money(received_cash),
            "received_non_cash": _money(received_non_cash),
            "shcil_stamp_deposit": _money(shcil_stamp_deposit),
            "period_from": filters.date_from.isoformat() if filters.date_from else "",
            "period_to": filters.date_to.isoformat() if filters.date_to else "",
        }

    def _ocr_stamp_ids(self) -> set[int]:
        stmt = select(StampOcrImage.StampID).where(StampOcrImage.StampID.isnot(None)).distinct()
        return {int(stamp_id) for stamp_id in self.session.scalars(stmt).all() if stamp_id}

    @staticmethod
    def _id_chunks(values: list[int], size: int = 1000):
        for i in range(0, len(values), size):
            yield values[i : i + size]

    def _payment_lookup(self, daily_ids: list[int]) -> dict[int, tuple[str, bool, bool]]:
        """Map daily TransactionID → (payment_mode, has_cash, has_non_cash)."""
        result: dict[int, tuple[str, bool, bool]] = {}
        if not daily_ids:
            return result

        payment_lines: list[JTCSDailyTransactionPayment] = []
        for chunk in self._id_chunks(daily_ids):
            payment_lines.extend(
                self.session.scalars(
                    select(JTCSDailyTransactionPayment)
                    .where(JTCSDailyTransactionPayment.TransactionID.in_(chunk))
                    .order_by(
                        JTCSDailyTransactionPayment.TransactionID.asc(),
                        JTCSDailyTransactionPayment.PaymentSequence.asc(),
                    )
                ).all()
            )
        account_ids = {line.BankAccountID for line in payment_lines}
        accounts: dict[int, JtcsBankAccountMaster] = {}
        for chunk in self._id_chunks(list(account_ids)):
            for account in self.session.scalars(
                select(JtcsBankAccountMaster).where(
                    JtcsBankAccountMaster.JtcsBankAccountID.in_(chunk)
                )
            ).all():
                accounts[account.JtcsBankAccountID] = account

        lines_by_txn: dict[int, list[JTCSDailyTransactionPayment]] = {}
        for line in payment_lines:
            lines_by_txn.setdefault(line.TransactionID, []).append(line)

        missing = [tid for tid in daily_ids if tid not in lines_by_txn]
        banks_by_txn: dict[int, list[JtcsBankTransaction]] = {}
        if missing:
            bank_rows: list[JtcsBankTransaction] = []
            for chunk in self._id_chunks(missing):
                bank_rows.extend(
                    self.session.scalars(
                        select(JtcsBankTransaction)
                        .where(JtcsBankTransaction.SourceTable == "JTCSDailyTransaction")
                        .where(
                            or_(
                                JtcsBankTransaction.SourceRecordID.in_(chunk),
                                JtcsBankTransaction.SourceID.in_(chunk),
                            )
                        )
                        .order_by(JtcsBankTransaction.PaymentSequence.asc())
                    ).all()
                )
            for bank in bank_rows:
                key = bank.SourceRecordID or bank.SourceID
                if key:
                    banks_by_txn.setdefault(int(key), []).append(bank)
            missing_account_ids = [
                bank.JtcsBankAccountID
                for bank in bank_rows
                if bank.JtcsBankAccountID and bank.JtcsBankAccountID not in accounts
            ]
            for chunk in self._id_chunks(list(dict.fromkeys(missing_account_ids))):
                for account in self.session.scalars(
                    select(JtcsBankAccountMaster).where(
                        JtcsBankAccountMaster.JtcsBankAccountID.in_(chunk)
                    )
                ).all():
                    accounts[account.JtcsBankAccountID] = account

        for txn_id in daily_ids:
            labels: list[str] = []
            has_cash = False
            has_non_cash = False
            for line in lines_by_txn.get(txn_id, []):
                account = accounts.get(line.BankAccountID)
                label = self._payment_account_label(account=account)
                if label:
                    labels.append(label)
                if self._account_is_cash(account) or label == "Cash":
                    has_cash = True
                elif label:
                    has_non_cash = True
            if not labels:
                for bank in banks_by_txn.get(txn_id, []):
                    account = accounts.get(bank.JtcsBankAccountID)
                    label = self._payment_account_label(account=account, bank=bank)
                    if label:
                        labels.append(label)
                    if self._account_is_cash(account) or label == "Cash":
                        has_cash = True
                    elif label:
                        has_non_cash = True
            payment_mode = " + ".join(label for label in labels if label)
            if not has_cash and not has_non_cash and payment_mode:
                if payment_mode.strip().lower() == "cash":
                    has_cash = True
                else:
                    has_non_cash = True
            result[txn_id] = (payment_mode, has_cash, has_non_cash)
        return result

    def grid_rows(self, filters: StampGridFilters, *, limit: int | None = None) -> list[dict]:
        ocr_stamp_ids = self._ocr_stamp_ids()
        stmt = self._grid_base_stmt(filters).order_by(
            JTCSDailyTransaction.TransactionDate.desc(), StampMaster.CreatedDate.desc()
        )
        if limit is not None and limit > 0:
            stmt = stmt.limit(limit)
        pairs = self.session.execute(stmt).all()
        daily_ids = [daily.TransactionID for _, daily in pairs if daily is not None]
        payments = self._payment_lookup(daily_ids)
        customer_ids = [
            daily.CustomerID for _, daily in pairs if daily is not None and daily.CustomerID
        ]
        mobiles: dict[int, str] = {}
        for chunk in self._id_chunks(list(dict.fromkeys(customer_ids))):
            for customer in self.session.scalars(
                select(CustomerMaster).where(CustomerMaster.CustomerID.in_(chunk))
            ).all():
                mobiles[customer.CustomerID] = (customer.MobileNumber or "").strip()

        rows: list[dict] = []
        for stamp, daily in pairs:
            payment_mode = ""
            has_cash = False
            has_non_cash = False
            mobile_number = ""
            if daily is not None:
                payment_mode, has_cash, has_non_cash = payments.get(
                    daily.TransactionID, ("", False, False)
                )
                if daily.CustomerID:
                    mobile_number = mobiles.get(daily.CustomerID, "")
            stamp_mobile = (getattr(stamp, "MobileNumber", None) or "").strip()
            if stamp_mobile:
                mobile_number = stamp_mobile
            rows.append(
                {
                    "stamp_id": stamp.StampID,
                    "transaction_id": daily.TransactionID if daily else None,
                    "certificate_number": stamp.CertificateNumber,
                    "certificate_date": stamp.CertificateIssuedDate.isoformat()
                    if stamp.CertificateIssuedDate
                    else "",
                    "stamp_duty_amount": str(stamp.StampDutyAmount or ""),
                    "sale_amount": str(daily.SaleAmount if daily else ""),
                    "transaction_date": daily.TransactionDate.isoformat()
                    if daily and daily.TransactionDate
                    else "",
                    "customer_name": self._display_name(
                        daily.CustomerName if daily else "",
                        stamp.StampDutyPaidBy,
                        stamp.FirstPartyName,
                    ),
                    "mobile_number": mobile_number,
                    "first_party": self._display_name(stamp.FirstPartyName),
                    "payment_mode": payment_mode,
                    "stamp_duty_paid_by": self._display_name(stamp.StampDutyPaidBy),
                    "is_ocr_entry": stamp.StampID in ocr_stamp_ids,
                    "has_cash": has_cash,
                    "has_non_cash": has_non_cash,
                }
            )
        return rows

    def duty_grouping(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        """Group active stamps by duty value. Blank dates = all dates."""
        work_date = func.coalesce(
            JTCSDailyTransaction.TransactionDate,
            StampMaster.CertificateIssuedDate,
        )
        base = (
            select(StampMaster.StampID, StampMaster.StampDutyAmount)
            .select_from(StampMaster)
            .outerjoin(JTCSDailyTransaction, JTCSDailyTransaction.StampID == StampMaster.StampID)
            .where(StampMaster.IsActive == True)  # noqa: E712
            .where(StampMaster.StampDutyAmount.is_not(None))
            .where(StampMaster.StampDutyAmount > 0)
        )
        if date_from:
            base = base.where(work_date >= date_from)
        if date_to:
            base = base.where(work_date <= date_to)
        subq = base.distinct().subquery()
        stmt = (
            select(subq.c.StampDutyAmount, func.count())
            .group_by(subq.c.StampDutyAmount)
            .order_by(subq.c.StampDutyAmount.asc())
        )
        rows: list[dict] = []
        total_nos = 0
        total_amount = Decimal("0.00")
        for value, nos in self.session.execute(stmt).all():
            duty = Decimal(str(value or 0)).quantize(Decimal("0.01"))
            count = int(nos or 0)
            amount = (duty * Decimal(count)).quantize(Decimal("0.01"))
            rows.append({"value": str(duty), "nos": count, "amount": str(amount)})
            total_nos += count
            total_amount += amount
        return {
            "rows": rows,
            "total_nos": total_nos,
            "total_amount": str(total_amount.quantize(Decimal("0.01"))),
            "date_from": date_from.isoformat() if date_from else "",
            "date_to": date_to.isoformat() if date_to else "",
        }

    def list_grid_data(self, filters: StampGridFilters) -> dict:
        rows = self.grid_rows(filters)
        period_summary = self.period_summary(filters)
        if period_summary["stamp_count"] == 0 and rows:
            period_summary["stamp_count"] = len(rows)
        if Decimal(period_summary["total_sale_amount"]) == 0 and rows:
            sale_total = sum(Decimal(str(row.get("sale_amount") or 0)) for row in rows)
            period_summary["total_sale_amount"] = str(sale_total.quantize(Decimal("0.01")))
        if Decimal(period_summary["payment_received_amount"]) == 0 and rows:
            duty_total = sum(Decimal(str(row.get("stamp_duty_amount") or 0)) for row in rows)
            period_summary["payment_received_amount"] = str(duty_total.quantize(Decimal("0.01")))
        return {
            "period_summary": period_summary,
            "rows": rows,
        }

    def delete(self, stamp: StampMaster) -> None:
        self.session.delete(stamp)
        self.session.flush()

    def deactivate(self, stamp: StampMaster, *, modified_by: str) -> None:
        stamp.IsActive = False
        stamp.ModifiedBy = modified_by
        stamp.ModifiedDate = datetime.utcnow()
        self.session.flush()
