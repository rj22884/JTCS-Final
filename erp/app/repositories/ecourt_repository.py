from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.bank_cash import OthersBankCashTransaction
from app.models.ecourt import ECourtReceiptBatch, ECourtReceiptLine, ECourtSale
from app.models.transactions import (
    JTCSDailyTransaction,
    JTCSDailyTransactionPayment,
    JtcsBankAccountMaster,
    JtcsBankTransaction,
)
from app.utils.shcil_bank_accounts import ecourt_purchase_account_id


class ECourtRepository:
    # SQL Server / ODBC IN-parameter limit is ~2100; stay well under it.
    _IN_CHUNK_SIZE = 400

    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    @staticmethod
    def _chunks(values: list, size: int):
        for start in range(0, len(values), size):
            yield values[start : start + size]

    def create_batch(self, data: dict) -> ECourtReceiptBatch:
        data.setdefault("ImportedDate", datetime.utcnow())
        batch = ECourtReceiptBatch(**data)
        self.session.add(batch)
        self.session.flush()
        return batch

    def add_lines(self, import_id: int, lines: list[dict]) -> int:
        count = 0
        for line in lines:
            row = ECourtReceiptLine(ImportID=import_id, **line)
            self.session.add(row)
            count += 1
        self.session.flush()
        return count

    def get_batch(self, import_id: int) -> ECourtReceiptBatch | None:
        return self.session.get(ECourtReceiptBatch, import_id)

    def latest_batch(self) -> ECourtReceiptBatch | None:
        stmt = select(ECourtReceiptBatch).order_by(ECourtReceiptBatch.ImportID.desc()).limit(1)
        return self.session.scalars(stmt).first()

    def sold_receipt_numbers(self, receipt_numbers: list[str]) -> set[str]:
        if not receipt_numbers:
            return set()
        found: set[str] = set()
        for chunk in self._chunks(list(receipt_numbers), self._IN_CHUNK_SIZE):
            stmt = select(ECourtSale.ReceiptNo).where(ECourtSale.ReceiptNo.in_(chunk))
            found.update(self.session.scalars(stmt).all())
        return found

    def list_lines_for_stationery(
        self, stationery_no: str, *, import_id: int | None = None, exact: bool = False
    ) -> list[ECourtReceiptLine]:
        normalized = (stationery_no or "").strip()
        if not normalized:
            return []

        stmt = select(ECourtReceiptLine).where(ECourtReceiptLine.StationeryNumber == normalized)
        if import_id is not None:
            stmt = stmt.where(ECourtReceiptLine.ImportID == import_id)
        stmt = stmt.order_by(ECourtReceiptLine.ReceiptNo)
        lines = list(self.session.scalars(stmt).all())
        if lines or exact:
            return lines

        stmt = select(ECourtReceiptLine).where(
            ECourtReceiptLine.StationeryNumber.like(f"%{normalized}")
        )
        if import_id is not None:
            stmt = stmt.where(ECourtReceiptLine.ImportID == import_id)
        stmt = stmt.order_by(ECourtReceiptLine.StationeryNumber, ECourtReceiptLine.ReceiptNo)
        return list(self.session.scalars(stmt).all())

    def delete_lines(self, lines: list[ECourtReceiptLine]) -> int:
        count = 0
        for line in lines:
            self.session.delete(line)
            count += 1
        if count:
            self.session.flush()
        return count

    def delete_empty_batches(self, import_ids: list[int]) -> int:
        removed = 0
        for import_id in sorted({int(value) for value in import_ids if value}):
            remaining = self.session.scalar(
                select(func.count())
                .select_from(ECourtReceiptLine)
                .where(ECourtReceiptLine.ImportID == import_id)
            )
            if int(remaining or 0) > 0:
                continue
            batch = self.get_batch(import_id)
            if batch is None:
                continue
            self.session.delete(batch)
            removed += 1
        if removed:
            self.session.flush()
        return removed

    def list_all_lines(self) -> list[ECourtReceiptLine]:
        stmt = select(ECourtReceiptLine).order_by(
            ECourtReceiptLine.StationeryNumber,
            ECourtReceiptLine.ReceiptNo,
        )
        return list(self.session.scalars(stmt).all())

    def existing_receipt_stationery_pairs(
        self, pairs: list[tuple[str, str]]
    ) -> set[tuple[str, str]]:
        if not pairs:
            return set()
        receipt_numbers = sorted({receipt for receipt, _ in pairs})
        existing: set[tuple[str, str]] = set()
        for chunk in self._chunks(receipt_numbers, self._IN_CHUNK_SIZE):
            stmt = select(ECourtReceiptLine.ReceiptNo, ECourtReceiptLine.StationeryNumber).where(
                ECourtReceiptLine.ReceiptNo.in_(chunk)
            )
            for receipt_no, stationery_no in self.session.execute(stmt).all():
                existing.add(
                    (
                        (receipt_no or "").strip().upper(),
                        (stationery_no or "").strip(),
                    )
                )
        return existing

    def existing_receipt_numbers_in_db(self, receipt_numbers: list[str]) -> set[str]:
        return set(self.existing_imported_receipt_details(receipt_numbers).keys())

    def existing_imported_receipt_details(self, receipt_numbers: list[str]) -> dict[str, dict]:
        normalized = sorted({(value or "").strip().upper() for value in receipt_numbers if (value or "").strip()})
        if not normalized:
            return {}
        receipt_expr = func.upper(func.ltrim(func.rtrim(ECourtReceiptLine.ReceiptNo)))
        details: dict[str, dict] = {}
        for chunk in self._chunks(normalized, self._IN_CHUNK_SIZE):
            stmt = select(ECourtReceiptLine.ReceiptNo, ECourtReceiptLine.StationeryNumber).where(
                receipt_expr.in_(chunk)
            )
            for receipt_no, stationery_no in self.session.execute(stmt).all():
                key = (receipt_no or "").strip().upper()
                if not key:
                    continue
                details[key] = {
                    "receipt_no": key,
                    "stationerynumber": (stationery_no or "").strip(),
                }
        return details

    def fully_sold_stationery_numbers(self, stationery_numbers: list[str]) -> set[str]:
        """Stationery numbers where every receipt line is sold (ECourtSale)."""
        normalized = sorted({(value or "").strip() for value in stationery_numbers if (value or "").strip()})
        if not normalized:
            return set()

        by_stationery: dict[str, set[str]] = {}
        for chunk in self._chunks(normalized, self._IN_CHUNK_SIZE):
            stmt = select(ECourtReceiptLine.StationeryNumber, ECourtReceiptLine.ReceiptNo).where(
                ECourtReceiptLine.StationeryNumber.in_(chunk)
            )
            for stationery_no, receipt_no in self.session.execute(stmt).all():
                stn = (stationery_no or "").strip()
                receipt = (receipt_no or "").strip().upper()
                if not stn or not receipt:
                    continue
                by_stationery.setdefault(stn, set()).add(receipt)

        if not by_stationery:
            return set()

        all_receipts = sorted({receipt for receipts in by_stationery.values() for receipt in receipts})
        sold = self.sold_receipt_numbers(all_receipts)

        return {
            stn
            for stn, receipts in by_stationery.items()
            if receipts and receipts.issubset(sold)
        }

    def list_lines_for_import(self, import_id: int) -> list[ECourtReceiptLine]:
        stmt = (
            select(ECourtReceiptLine)
            .where(ECourtReceiptLine.ImportID == import_id)
            .order_by(ECourtReceiptLine.StationeryNumber, ECourtReceiptLine.ReceiptNo)
        )
        return list(self.session.scalars(stmt).all())

    def get_lines_by_receipts(self, receipt_numbers: list[str]) -> list[ECourtReceiptLine]:
        normalized = sorted({(value or "").strip().upper() for value in receipt_numbers if (value or "").strip()})
        if not normalized:
            return []
        rows: list[ECourtReceiptLine] = []
        for chunk in self._chunks(normalized, self._IN_CHUNK_SIZE):
            stmt = select(ECourtReceiptLine).where(ECourtReceiptLine.ReceiptNo.in_(chunk))
            rows.extend(self.session.scalars(stmt).all())
        return rows

    def create_sale(self, data: dict) -> ECourtSale:
        data.setdefault("CreatedDate", datetime.utcnow())
        row = ECourtSale(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def delete_sale(self, sale: ECourtSale) -> None:
        self.session.delete(sale)
        self.session.flush()

    def list_sales_for_daily(self, daily_transaction_id: int) -> list[ECourtSale]:
        stmt = select(ECourtSale).where(ECourtSale.DailyTransactionID == daily_transaction_id)
        return list(self.session.scalars(stmt).all())

    def list_sales_for_receipts(self, receipt_numbers: list[str]) -> list[ECourtSale]:
        normalized = sorted({(value or "").strip().upper() for value in receipt_numbers if (value or "").strip()})
        if not normalized:
            return []
        rows: list[ECourtSale] = []
        for chunk in self._chunks(normalized, self._IN_CHUNK_SIZE):
            stmt = select(ECourtSale).where(ECourtSale.ReceiptNo.in_(chunk))
            rows.extend(self.session.scalars(stmt).all())
        return rows

    def transaction_dates_by_receipt(self, receipt_numbers: list[str]) -> dict[str, str]:
        """Map ReceiptNo -> sale TransactionDate (ISO) from linked daily transaction."""
        sales = self.list_sales_for_receipts(receipt_numbers)
        if not sales:
            return {}

        daily_ids = sorted({sale.DailyTransactionID for sale in sales if sale.DailyTransactionID})
        daily_dates: dict[int, str] = {}
        for chunk in self._chunks(daily_ids, self._IN_CHUNK_SIZE):
            stmt = select(JTCSDailyTransaction).where(JTCSDailyTransaction.TransactionID.in_(chunk))
            for daily in self.session.scalars(stmt).all():
                if daily.TransactionDate:
                    daily_dates[daily.TransactionID] = daily.TransactionDate.isoformat()

        result: dict[str, str] = {}
        for sale in sales:
            key = (sale.ReceiptNo or "").strip().upper()
            if not key:
                continue
            txn = daily_dates.get(sale.DailyTransactionID) if sale.DailyTransactionID else None
            if txn:
                result[key] = txn
            elif sale.CreatedDate is not None:
                created = sale.CreatedDate
                result[key] = created.date().isoformat() if hasattr(created, "date") else str(created)[:10]
        return result

    def account_numbers_by_receipt(self, receipt_numbers: list[str]) -> dict[str, str]:
        """Map ReceiptNo -> sale payment bank account number(s).

        Grid Account Number shows where the sale was received (Cash / customer
        payment bank), not the SHCILECourt purchase ledger account.
        """
        sales = self.list_sales_for_receipts(receipt_numbers)
        if not sales:
            return {}

        daily_ids = sorted({sale.DailyTransactionID for sale in sales if sale.DailyTransactionID})
        if not daily_ids:
            return {}

        payments: list[JTCSDailyTransactionPayment] = []
        for chunk in self._chunks(daily_ids, self._IN_CHUNK_SIZE):
            payments.extend(
                self.session.scalars(
                    select(JTCSDailyTransactionPayment)
                    .where(JTCSDailyTransactionPayment.TransactionID.in_(chunk))
                    .order_by(
                        JTCSDailyTransactionPayment.TransactionID,
                        JTCSDailyTransactionPayment.PaymentSequence,
                    )
                ).all()
            )
        if not payments:
            return {}

        bank_ids = sorted({int(p.BankAccountID) for p in payments if p.BankAccountID})
        bank_labels: dict[int, str] = {}
        for chunk in self._chunks(bank_ids, self._IN_CHUNK_SIZE):
            for bank in self.session.scalars(
                select(JtcsBankAccountMaster).where(
                    JtcsBankAccountMaster.JtcsBankAccountID.in_(chunk)
                )
            ).all():
                label = (
                    (bank.AccountNumber or "").strip()
                    or (bank.MaskedAccountNumber or "").strip()
                    or (bank.BankName or "").strip()
                )
                if label:
                    bank_labels[int(bank.JtcsBankAccountID)] = label

        daily_accounts: dict[int, list[str]] = {}
        for payment in payments:
            label = bank_labels.get(int(payment.BankAccountID or 0), "")
            if not label:
                continue
            bucket = daily_accounts.setdefault(int(payment.TransactionID), [])
            if label not in bucket:
                bucket.append(label)

        result: dict[str, str] = {}
        for sale in sales:
            key = (sale.ReceiptNo or "").strip().upper()
            if not key or not sale.DailyTransactionID:
                continue
            accounts = daily_accounts.get(int(sale.DailyTransactionID), [])
            if accounts:
                result[key] = ", ".join(accounts)
        return result

    def get_sale_by_receipt(self, receipt_no: str) -> ECourtSale | None:
        stmt = select(ECourtSale).where(ECourtSale.ReceiptNo == receipt_no.strip().upper())
        return self.session.scalars(stmt).first()

    def list_recent_sales(self, *, limit: int = 100) -> list[ECourtSale]:
        stmt = select(ECourtSale).order_by(ECourtSale.CreatedDate.desc()).limit(limit)
        return list(self.session.scalars(stmt).all())

    def count_sales_for_stationery(self, stationery_no: str) -> int:
        normalized = (stationery_no or "").strip()
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(ECourtSale)
                .where(ECourtSale.StationeryNumber == normalized)
            )
            or 0
        )

    def _ecourt_daily_filter(self, stmt):
        return (
            stmt.where(JTCSDailyTransaction.WorkType == "SHCIL")
            .where(JTCSDailyTransaction.SubWorkType == "e-Court Activity")
            .where(JTCSDailyTransaction.Status == "Posted")
        )

    def _cash_account_match(self):
        return or_(
            func.lower(func.coalesce(JtcsBankAccountMaster.BankName, "")) == "cash",
            func.lower(func.coalesce(JtcsBankAccountMaster.AccountNumber, "")) == "cash",
            func.lower(func.coalesce(JtcsBankAccountMaster.MaskedAccountNumber, "")) == "cash",
        )

    def _shcil_ecourt_account_match(self):
        account_id = ecourt_purchase_account_id(self.session)
        if account_id is None:
            return JtcsBankAccountMaster.JtcsBankAccountID == 0
        return JtcsBankAccountMaster.JtcsBankAccountID == account_id

    def activity_summary(self) -> dict:
        """Summary cards for e-Court Activity (sale / payments / SHCILECourt deposits)."""
        sale_stmt = self._ecourt_daily_filter(
            select(
                func.count(JTCSDailyTransaction.TransactionID),
                func.coalesce(func.sum(JTCSDailyTransaction.SaleAmount), 0),
                func.coalesce(func.sum(JTCSDailyTransaction.PurchaseAmount), 0),
            ).select_from(JTCSDailyTransaction)
        )
        sale_count, sale_total, purchase_total = self.session.execute(sale_stmt).one()

        payment_stmt = self._ecourt_daily_filter(
            select(func.coalesce(func.sum(JTCSDailyTransactionPayment.Amount), 0))
            .select_from(JTCSDailyTransactionPayment)
            .join(
                JTCSDailyTransaction,
                JTCSDailyTransactionPayment.TransactionID == JTCSDailyTransaction.TransactionID,
            )
        )
        payment_received = Decimal(str(self.session.scalar(payment_stmt) or 0))

        cash_stmt = self._ecourt_daily_filter(
            select(func.coalesce(func.sum(JTCSDailyTransactionPayment.Amount), 0))
            .select_from(JTCSDailyTransactionPayment)
            .join(
                JTCSDailyTransaction,
                JTCSDailyTransactionPayment.TransactionID == JTCSDailyTransaction.TransactionID,
            )
            .join(
                JtcsBankAccountMaster,
                JtcsBankAccountMaster.JtcsBankAccountID == JTCSDailyTransactionPayment.BankAccountID,
            )
            .where(self._cash_account_match())
        )
        received_cash = Decimal(str(self.session.scalar(cash_stmt) or 0))

        if payment_received <= 0:
            bank_join = or_(
                JtcsBankTransaction.SourceRecordID == JTCSDailyTransaction.TransactionID,
                JtcsBankTransaction.SourceID == JTCSDailyTransaction.TransactionID,
            )
            bank_payment_stmt = self._ecourt_daily_filter(
                select(func.coalesce(func.sum(JtcsBankTransaction.Debit), 0))
                .select_from(JtcsBankTransaction)
                .join(JTCSDailyTransaction, bank_join)
                .where(JtcsBankTransaction.SourceTable == "JTCSDailyTransaction")
                .where(func.upper(func.coalesce(JtcsBankTransaction.LedgerKind, "")) == "RECEIPT")
            )
            payment_received = Decimal(str(self.session.scalar(bank_payment_stmt) or 0))

            cash_bank_stmt = self._ecourt_daily_filter(
                select(func.coalesce(func.sum(JtcsBankTransaction.Debit), 0))
                .select_from(JtcsBankTransaction)
                .join(JTCSDailyTransaction, bank_join)
                .join(
                    JtcsBankAccountMaster,
                    JtcsBankAccountMaster.JtcsBankAccountID == JtcsBankTransaction.JtcsBankAccountID,
                )
                .where(JtcsBankTransaction.SourceTable == "JTCSDailyTransaction")
                .where(func.upper(func.coalesce(JtcsBankTransaction.LedgerKind, "")) == "RECEIPT")
                .where(self._cash_account_match())
            )
            received_cash = Decimal(str(self.session.scalar(cash_bank_stmt) or 0))

        received_non_cash = payment_received - received_cash
        if received_non_cash < 0:
            received_non_cash = Decimal("0")

        deposit_stmt = (
            select(func.coalesce(func.sum(OthersBankCashTransaction.Amount), 0))
            .select_from(OthersBankCashTransaction)
            .join(
                JtcsBankAccountMaster,
                JtcsBankAccountMaster.JtcsBankAccountID
                == OthersBankCashTransaction.DebitBankAccountID,
            )
            .where(OthersBankCashTransaction.IsActive == True)  # noqa: E712
            .where(self._shcil_ecourt_account_match())
        )
        shcil_ecourt_deposit = Decimal(str(self.session.scalar(deposit_stmt) or 0))

        def _money(value) -> str:
            return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))

        return {
            "sale_count": int(sale_count or 0),
            "fee_sale_amount": _money(sale_total),
            "payment_received_amount": _money(payment_received if payment_received > 0 else sale_total),
            "fee_buy_amount": _money(purchase_total),
            "received_cash": _money(received_cash),
            "received_non_cash": _money(received_non_cash),
            "shcil_ecourt_deposit": _money(shcil_ecourt_deposit),
        }
