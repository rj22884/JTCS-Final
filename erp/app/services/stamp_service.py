from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from flask import request
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.exceptions.stamp_exceptions import StampDuplicateError
from app.models.transactions import JTCSDailyTransaction
from app.utils.shcil_bank_accounts import find_stamp_purchase_bank
from app.repositories.stamp_ocr_repository import StampOcrRepository
from app.repositories.stamp_repository import StampGridFilters, StampRepository
from app.repositories.transaction_repository import (
    BankTransactionRepository,
    DailyTransactionPaymentRepository,
    DailyTransactionRepository,
    MasterRepository,
)


@dataclass
class StampSaveResult:
    stamp_id: int
    daily_transaction_id: int
    bank_transaction_id: int | None
    bank_transaction_ids: list[int]
    message: str


class StampService:
    """
    SHCIL Stamp Activity — central ERP posting pattern:

        StampMaster (module certificate data)
            → JTCSDailyTransaction (business work)
            → JTCSBankTransaction (money movement, only when SaleAmount > 0)

    All ERP modules must post through JTCSDailyTransaction + JTCSBankTransaction only.
    """

    WORK_TYPE = "SHCIL"
    SUB_WORK_TYPE = "Stamp Activity"
    _logger = logging.getLogger(__name__)

    def __init__(
        self,
        stamp_repo: StampRepository | None = None,
        daily_repo: DailyTransactionRepository | None = None,
        bank_repo: BankTransactionRepository | None = None,
        payment_repo: DailyTransactionPaymentRepository | None = None,
        master_repo: MasterRepository | None = None,
        ocr_repo: StampOcrRepository | None = None,
    ):
        self.stamp_repo = stamp_repo or StampRepository()
        self.daily_repo = daily_repo or DailyTransactionRepository()
        self.bank_repo = bank_repo or BankTransactionRepository()
        self.payment_repo = payment_repo or DailyTransactionPaymentRepository()
        self.master_repo = master_repo or MasterRepository()
        self.ocr_repo = ocr_repo or StampOcrRepository()

    def validate_form(self, form: dict, *, update_stamp_id: int | None = None) -> None:
        certificate_number = (form.get("CertificateNumber") or "").strip()
        if not certificate_number:
            raise ValueError("Certificate Number is required.")

        certificate_date = self._as_date(form.get("CertificateIssuedDate"))
        if not certificate_date:
            raise ValueError("Certificate Date is required.")

        entry_mode = (form.get("EntryMode") or "manual").strip().lower()
        if entry_mode != "manual" and not self._clean(form.get("FirstPartyName")):
            raise ValueError("First Party is required.")

        if entry_mode == "manual" and not self._clean(form.get("StampDutyPaidBy")):
            raise ValueError("Stamp Duty Paid By is required.")

        stamp_duty = self._decimal_or_none(form.get("StampDutyAmount"))
        if stamp_duty is None:
            raise ValueError("Stamp Duty Amount is required.")
        if stamp_duty <= 0:
            raise ValueError("Stamp Duty Amount must be greater than zero.")

        sale_amount = self._decimal(form.get("SaleAmount"))
        if sale_amount <= 0:
            raise ValueError("Sale Amount must be greater than zero.")
        if sale_amount <= stamp_duty:
            raise ValueError("Sale Amount must be greater than Stamp Duty Amount.")

        payment_lines = self._parse_payment_lines(form, sale_amount)
        if not payment_lines:
            raise ValueError("At least one payment mode is required.")

        exclude_id = update_stamp_id if update_stamp_id is not None else self._stamp_id_from_form(form)
        existing = self.stamp_repo.find_existing(
            certificate_number,
            exclude_id=exclude_id,
        )
        if existing:
            raise StampDuplicateError(existing)

    @staticmethod
    def _stamp_id_from_form(form: dict) -> int | None:
        for key in ("StampID", "EditStampID"):
            raw = form.get(key)
            if raw in (None, ""):
                continue
            try:
                stamp_id = int(raw)
                if stamp_id > 0:
                    return stamp_id
            except (TypeError, ValueError):
                continue
        return None

    def _remove_daily_transaction(self, daily: JTCSDailyTransaction) -> None:
        payment_rows = self.payment_repo.list_by_transaction(daily.TransactionID)
        bank_rows = self._collect_bank_rows_for_daily(daily, payment_rows)
        self.payment_repo.delete_by_transaction(daily.TransactionID)
        daily.BankTransactionID = None
        db.session.flush()
        for bank_row in bank_rows:
            self.bank_repo.delete(bank_row)
        self.daily_repo.delete(daily)

    def _collect_bank_rows_for_daily(
        self, daily: JTCSDailyTransaction, payment_rows: list | None = None
    ) -> list:
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
        bank_rows.sort(
            key=lambda row: (
                row.PaymentSequence or 0,
                row.JtcsBankTransactionID,
            )
        )
        return bank_rows

    def _remove_linked_transactions(self, stamp_id: int) -> None:
        for daily in self.stamp_repo.list_daily_for_stamp(stamp_id):
            self._remove_daily_transaction(daily)

    def _list_bank_rows_for_daily(self, daily: JTCSDailyTransaction) -> list:
        payment_rows = self.payment_repo.list_by_transaction(daily.TransactionID)
        return self._collect_bank_rows_for_daily(daily, payment_rows)

    @staticmethod
    def _payment_lines_from_rows(payment_rows: list, *, bank_rows: list | None = None, daily=None) -> list[dict]:
        if payment_rows:
            return [
                {
                    "bank_account_id": row.BankAccountID,
                    "amount": str(row.Amount),
                    "payment_mode_id": row.PaymentModeID,
                }
                for row in payment_rows
            ]
        if bank_rows:
            # Sale receipts only (Debit In). Skip stamp-purchase Credit Out rows.
            sale_rows = [
                row
                for row in bank_rows
                if (getattr(row, "Debit", None) or Decimal("0")) > 0
                and (getattr(row, "LedgerKind", None) or "").strip().upper() != "PAYMENT"
            ]
            return [
                {
                    "bank_account_id": row.JtcsBankAccountID,
                    "amount": str(row.Debit or (daily.SaleAmount if daily else "")),
                    "payment_mode_id": row.PaymentModeID or (daily.PaymentModeID if daily else None),
                }
                for row in sale_rows
            ]
        return []

    def _load_payment_lines(self, daily: JTCSDailyTransaction) -> list[dict]:
        payment_rows = self.payment_repo.list_by_transaction(daily.TransactionID)
        bank_rows = self._list_bank_rows_for_daily(daily)

        payment_lines = self._payment_lines_from_rows(payment_rows) if payment_rows else []
        bank_lines = (
            self._payment_lines_from_rows([], bank_rows=bank_rows, daily=daily) if bank_rows else []
        )

        if len(bank_lines) > len(payment_lines):
            loaded = bank_lines
        else:
            loaded = payment_lines if payment_lines else bank_lines

        self._logger.info(
            "Load payment lines daily_id=%s payment_rows=%s bank_rows=%s loaded=%s split_count=%s",
            daily.TransactionID,
            len(payment_rows),
            len(bank_rows),
            len(loaded),
            daily.PaymentSplitCount,
        )
        return loaded

    def _resolve_stamp_purchase_bank(self):
        """Stamp duty purchase wallet (alias SHCILStamp).

        Account Number / Bank Name may be real bank details. Match alias on
        Masked Account Number and other master fields, then fall back to the
        last Stamp Purchase ledger row. Does not call list_active_bank_accounts
        (that commits the session and breaks begin_nested() during save).
        """
        account = find_stamp_purchase_bank(self.master_repo.session)
        if account is None:
            raise ValueError(
                "Stamp purchase bank account not found in Bank Master. "
                "Use account number 0213UK1423304 (SHCILStamp) for stamp-duty purchase."
            )
        return self.master_repo.resolve_bank_account_by_id(account.JtcsBankAccountID)

    def _repost_stamp_transactions(
        self,
        stamp,
        *,
        txn_date: date,
        sale_amount: Decimal,
        purchase_amount: Decimal,
        payment_lines: list[dict],
        customer_id,
        customer_name,
        reference_no: str,
        narration: str,
        remarks,
        created_by: str,
        certificate_number: str,
        existing_daily: JTCSDailyTransaction | None = None,
    ) -> tuple[JTCSDailyTransaction, list[int]]:
        purchase_amount = purchase_amount if purchase_amount > 0 else Decimal("0")
        if existing_daily is not None:
            bank_rows = self._collect_bank_rows_for_daily(existing_daily)
            self.payment_repo.delete_by_transaction(existing_daily.TransactionID)
            existing_daily.BankTransactionID = None
            db.session.flush()
            for bank_row in bank_rows:
                self.bank_repo.delete(bank_row)

            existing_daily.TransactionDate = txn_date
            existing_daily.CustomerID = int(customer_id) if customer_id else None
            existing_daily.CustomerName = customer_name
            existing_daily.ReferenceNo = reference_no
            existing_daily.Description = narration
            existing_daily.SaleAmount = sale_amount
            existing_daily.PurchaseAmount = purchase_amount
            existing_daily.TotalAmount = sale_amount
            existing_daily.PaymentModeID = payment_lines[0]["payment_mode_id"]
            existing_daily.PaymentSplitCount = len(payment_lines)
            existing_daily.Remarks = remarks
            existing_daily.ModifiedDate = datetime.utcnow()
            db.session.flush()
            daily = existing_daily
        else:
            daily = self.daily_repo.create(
                {
                    "TransactionDate": txn_date,
                    "WorkType": self.WORK_TYPE,
                    "SubWorkType": self.SUB_WORK_TYPE,
                    "CustomerID": int(customer_id) if customer_id else None,
                    "CustomerName": customer_name,
                    "StampID": stamp.StampID,
                    "ReferenceNo": reference_no,
                    "Description": narration,
                    "IncomeAmount": Decimal("0"),
                    "ExpenseAmount": Decimal("0"),
                    "SaleAmount": sale_amount,
                    "PurchaseAmount": purchase_amount,
                    "GSTAmount": Decimal("0"),
                    "TDSAmount": Decimal("0"),
                    "TotalAmount": sale_amount,
                    "PaymentModeID": payment_lines[0]["payment_mode_id"],
                    "PaymentSplitCount": len(payment_lines),
                    "Status": "Posted",
                    "CreatedBy": created_by,
                    "CreatedDate": datetime.utcnow(),
                    "Remarks": remarks,
                }
            )

        bank_ids: list[int] = []
        for index, line in enumerate(payment_lines, start=1):
            bank_account = self.master_repo.resolve_bank_account_by_id(line["bank_account_id"])
            bank = self.bank_repo.create(
                {
                    "JtcsBankAccountID": bank_account.account_id or 0,
                    "BankName": bank_account.bank_name,
                    "MaskedAccountNumber": bank_account.masked_account_number,
                    "TransactionDate": txn_date,
                    "Description": "Stamp Sale",
                    "Debit": line["amount"],
                    "Credit": None,
                    "ClosingBalance": Decimal("0"),
                    "ImportedBy": created_by,
                    "ImportedDate": datetime.utcnow(),
                    "Remarks": certificate_number,
                    "IsLocked": False,
                    "SourceTable": self.bank_repo.SOURCE_TABLE,
                    "SourceRecordID": daily.TransactionID,
                    "SourceType": self.WORK_TYPE,
                    "SourceID": daily.TransactionID,
                    "LedgerKind": "RECEIPT",
                    "PaymentModeID": line["payment_mode_id"],
                    "PaymentSequence": index,
                }
            )
            bank_ids.append(bank.JtcsBankTransactionID)
            self.payment_repo.create(
                {
                    "TransactionID": daily.TransactionID,
                    "PaymentSequence": index,
                    "PaymentModeID": line["payment_mode_id"],
                    "BankAccountID": line["bank_account_id"],
                    "Amount": line["amount"],
                    "BankTransactionID": bank.JtcsBankTransactionID,
                }
            )

        # Stamp duty purchase → Credit (Out) from Axis Bank SHCILStamp
        if purchase_amount > 0:
            purchase_bank = self._resolve_stamp_purchase_bank()
            purchase_mode_id = self.master_repo.resolve_payment_mode_for_bank_account(
                purchase_bank.account_id or 0
            )
            purchase_txn = self.bank_repo.create(
                {
                    "JtcsBankAccountID": purchase_bank.account_id or 0,
                    "BankName": purchase_bank.bank_name,
                    "MaskedAccountNumber": purchase_bank.masked_account_number,
                    "TransactionDate": txn_date,
                    "Description": "Stamp Purchase",
                    "Debit": None,
                    "Credit": purchase_amount,
                    "ClosingBalance": Decimal("0"),
                    "ImportedBy": created_by,
                    "ImportedDate": datetime.utcnow(),
                    "Remarks": certificate_number,
                    "IsLocked": False,
                    "SourceTable": self.bank_repo.SOURCE_TABLE,
                    "SourceRecordID": daily.TransactionID,
                    "SourceType": self.WORK_TYPE,
                    "SourceID": daily.TransactionID,
                    "LedgerKind": "PAYMENT",
                    "PaymentModeID": purchase_mode_id,
                    "PaymentSequence": len(payment_lines) + 1,
                }
            )
            bank_ids.append(purchase_txn.JtcsBankTransactionID)

        if bank_ids:
            self.daily_repo.update_bank_link(daily, bank_ids[0])

        return daily, bank_ids

    def save_stamp_activity(self, form: dict, *, created_by: str) -> StampSaveResult:
        stamp_id = self._stamp_id_from_form(form)
        is_update = stamp_id is not None
        self.validate_form(form, update_stamp_id=stamp_id)

        certificate_number = (form.get("CertificateNumber") or "").strip()
        sale_amount = self._decimal(form.get("SaleAmount"))
        purchase_amount = self._decimal(form.get("StampDutyAmount"))
        payment_lines = self._parse_payment_lines(form, sale_amount)

        existing_payment_lines: list[dict] = []
        if is_update and stamp_id:
            daily = self.stamp_repo.get_daily_for_stamp(stamp_id)
            if daily is not None:
                existing_payment_lines = self._load_payment_lines(daily)
        self._logger.info(
            "Payment save stamp_id=%s update=%s existing=%s submitted=%s",
            stamp_id,
            is_update,
            [(line.get("bank_account_id"), str(line.get("amount"))) for line in existing_payment_lines],
            [(line.get("bank_account_id"), str(line.get("amount"))) for line in payment_lines],
        )

        stamp_duty_paid_by = self._clean(form.get("StampDutyPaidBy")) or self._clean(
            form.get("FirstPartyName")
        )
        customer_name = stamp_duty_paid_by or None
        customer_id = None
        mobile_digits = "".join(ch for ch in (form.get("MobileNumber") or "") if ch.isdigit())[-10:]
        if len(mobile_digits) == 10:
            matches = self.master_repo.list_customers_by_mobile(mobile_digits)
            if matches:
                customer_id = matches[0].CustomerID
                if not customer_name:
                    customer_name = matches[0].CustomerName
        if customer_id is None and stamp_id:
            existing_for_customer = self.stamp_repo.get_daily_for_stamp(stamp_id)
            if existing_for_customer and existing_for_customer.CustomerID:
                customer_id = existing_for_customer.CustomerID
        txn_date = (
            self._as_date(form.get("TransactionDate"))
            or self._as_date(form.get("CertificateIssuedDate"))
            or date.today()
        )
        ocr_image_id = form.get("OcrImageID")
        machine_name, ip_address = self._audit_context()

        stamp_data = {
            "CertificateNumber": certificate_number,
            "CertificateIssuedDate": self._as_date(form.get("CertificateIssuedDate")),
            "AccountReference": self._clean(form.get("AccountReference")),
            "UniqueDocumentReference": self._clean(form.get("UniqueDocumentReference")),
            "PurchasedBy": self._clean(form.get("PurchasedBy")),
            "DescriptionOfDocument": self._clean(form.get("DescriptionOfDocument"), 1000),
            "PropertyDescription": self._clean(form.get("PropertyDescription"), 1000),
            "ConsiderationPrice": self._decimal_or_none(form.get("ConsiderationPrice")),
            "FirstPartyName": self._clean(form.get("FirstPartyName")),
            "SecondPartyName": self._clean(form.get("SecondPartyName")),
            "StampDutyPaidBy": self._clean(form.get("StampDutyPaidBy")),
            "StampDutyAmount": self._decimal_or_none(form.get("StampDutyAmount")),
            "CreatedBy": created_by,
            "CreatedDate": datetime.utcnow(),
            "IsActive": True,
            "Remarks": self._clean(form.get("Remarks"), 500),
            "MachineName": machine_name,
            "IPAddress": ip_address,
        }

        reference_no = (form.get("ReferenceNo") or certificate_number).strip()
        narration = (form.get("Narration") or "Stamp Sale").strip()
        remarks = (form.get("Remarks") or "").strip() or None

        def _write() -> StampSaveResult:
            existing_daily = None
            if is_update:
                stamp = self.stamp_repo.get_by_id(stamp_id)
                if stamp is None or not stamp.IsActive:
                    raise ValueError("Stamp record not found for update.")
                stamp = self.stamp_repo.update_stamp(stamp, stamp_data, modified_by=created_by)
                linked_dailies = self.stamp_repo.list_daily_for_stamp(stamp.StampID)
                if linked_dailies:
                    existing_daily = linked_dailies[-1]
                    for extra_daily in linked_dailies[:-1]:
                        self._remove_daily_transaction(extra_daily)
            else:
                stamp, _created = self.stamp_repo.reactivate_or_create(
                    stamp_data,
                    modified_by=created_by,
                )

            if ocr_image_id:
                self.ocr_repo.link_stamp(int(ocr_image_id), stamp.StampID)

            daily, bank_ids = self._repost_stamp_transactions(
                stamp,
                txn_date=txn_date,
                sale_amount=sale_amount,
                purchase_amount=purchase_amount,
                payment_lines=payment_lines,
                customer_id=customer_id,
                customer_name=customer_name,
                reference_no=reference_no,
                narration=narration,
                remarks=remarks,
                created_by=created_by,
                certificate_number=certificate_number,
                existing_daily=existing_daily,
            )

            final_lines = self._load_payment_lines(daily)
            self._logger.info(
                "Payment save complete daily_id=%s inserted=%s final=%s bank_ids=%s",
                daily.TransactionID,
                len(payment_lines),
                [(line.get("bank_account_id"), str(line.get("amount"))) for line in final_lines],
                bank_ids,
            )

            bank_summary = ", ".join(f"#{bank_id}" for bank_id in bank_ids)
            action = "updated" if is_update else "saved"
            return StampSaveResult(
                stamp_id=stamp.StampID,
                daily_transaction_id=daily.TransactionID,
                bank_transaction_id=bank_ids[0] if bank_ids else None,
                bank_transaction_ids=bank_ids,
                message=(
                    f"Stamp activity {action}. Daily Transaction #{daily.TransactionID}"
                    + (f", Bank Transaction(s) {bank_summary}." if bank_ids else ".")
                ),
            )

        try:
            with db.session.begin_nested():
                result = _write()
            db.session.commit()
            return result
        except IntegrityError as exc:
            db.session.rollback()
            if "CertificateNumber" in str(exc.orig):
                existing = self.stamp_repo.find_existing(certificate_number)
                if existing:
                    raise StampDuplicateError(existing) from exc
                raise ValueError("Certificate Number already exists.") from exc
            raise
        except Exception:
            db.session.rollback()
            raise
        finally:
            db.session.remove()

    def check_certificate(self, certificate_number: str) -> dict:
        existing = self.stamp_repo.find_existing(certificate_number)
        if not existing:
            return {"exists": False}
        return {
            "exists": True,
            "stamp_id": existing.stamp_id,
            "transaction_id": existing.transaction_id,
            "customer_name": existing.customer_name or "—",
            "transaction_date": existing.transaction_date,
            "certificate_number": existing.certificate_number,
        }

    def search_records(self, query: str, *, limit: int = 100) -> list[dict]:
        return self.stamp_repo.search_by_certificate(query, limit=limit)

    def grid_data(self, filters: StampGridFilters) -> dict:
        return self.stamp_repo.list_grid_data(filters)

    CARD_LABELS = {
        "total_sale_amount": "Total Stamp Sale Amount",
        "payment_received_amount": "Payment Received Amount",
        "received_cash": "Received in Cash",
        "received_non_cash": "Received Other Than Cash",
        "shcil_stamp_deposit": "Deposited in SHCILStamp",
    }

    def card_detail(self, card_key: str, filters: StampGridFilters) -> dict:
        key = (card_key or "").strip()
        label = self.CARD_LABELS.get(key)
        if not label:
            raise ValueError("Unknown period summary card.")

        summary = self.stamp_repo.period_summary(filters)
        total = summary.get(key) or "0.00"

        if key == "shcil_stamp_deposit":
            rows = self.stamp_repo.list_shcil_stamp_deposit_rows(filters)
            return {
                "card": key,
                "label": label,
                "row_type": "deposit",
                "total": total,
                "row_count": len(rows),
                "period_from": summary.get("period_from") or "",
                "period_to": summary.get("period_to") or "",
                "rows": rows,
            }

        all_rows = self.stamp_repo.grid_rows(filters)
        if key == "received_cash":
            rows = [row for row in all_rows if row.get("has_cash")]
        elif key == "received_non_cash":
            rows = [row for row in all_rows if row.get("has_non_cash")]
        else:
            rows = all_rows

        return {
            "card": key,
            "label": label,
            "row_type": "stamp",
            "total": total,
            "row_count": len(rows),
            "period_from": summary.get("period_from") or "",
            "period_to": summary.get("period_to") or "",
            "rows": rows,
        }

    @staticmethod
    def filters_from_request(args) -> StampGridFilters:
        def _parse_date(name: str) -> date | None:
            raw = (args.get(name) or "").strip()
            if not raw:
                return None
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return None

        return StampGridFilters(
            date_from=_parse_date("date_from"),
            date_to=_parse_date("date_to"),
            certificate=(args.get("certificate") or args.get("q") or "").strip(),
            mobile=(args.get("mobile") or "").strip(),
            customer=(args.get("customer") or "").strip(),
        )

    def get_record(self, stamp_id: int) -> dict:
        stamp = self.stamp_repo.get_by_id(stamp_id)
        if stamp is None or not stamp.IsActive:
            raise ValueError("Stamp record not found.")

        daily = self.stamp_repo.get_daily_for_stamp(stamp_id)
        payments: list[dict] = []
        if daily:
            payments = self._load_payment_lines(daily)

        return {
            "stamp_id": stamp.StampID,
            "transaction_id": daily.TransactionID if daily else None,
            "bank_transaction_id": daily.BankTransactionID if daily else None,
            "is_ocr_entry": self.ocr_repo.has_linked_stamp(stamp.StampID),
            "CertificateNumber": stamp.CertificateNumber,
            "CertificateIssuedDate": stamp.CertificateIssuedDate.isoformat()
            if stamp.CertificateIssuedDate
            else "",
            "AccountReference": stamp.AccountReference or "",
            "UniqueDocumentReference": stamp.UniqueDocumentReference or "",
            "PurchasedBy": stamp.PurchasedBy or "",
            "DescriptionOfDocument": stamp.DescriptionOfDocument or "",
            "PropertyDescription": stamp.PropertyDescription or "",
            "ConsiderationPrice": str(stamp.ConsiderationPrice or ""),
            "FirstPartyName": stamp.FirstPartyName or "",
            "SecondPartyName": stamp.SecondPartyName or "",
            "StampDutyPaidBy": stamp.StampDutyPaidBy or "",
            "StampDutyAmount": str(stamp.StampDutyAmount or ""),
            "SaleAmount": str(daily.SaleAmount if daily else ""),
            "TransactionDate": daily.TransactionDate.isoformat()
            if daily and daily.TransactionDate
            else "",
            "CustomerID": "",
            "ReferenceNo": daily.ReferenceNo if daily else "",
            "Narration": daily.Description if daily else "Stamp Sale",
            "Remarks": stamp.Remarks or daily.Remarks if daily else "",
            "BankAccountID": payments[0]["bank_account_id"] if payments else "",
            "payments": payments,
            "payment_split_count": daily.PaymentSplitCount if daily else 1,
        }

    def delete_stamp(self, stamp_id: int, *, deleted_by: str) -> str:
        stamp = self.stamp_repo.get_by_id(stamp_id)
        if stamp is None:
            raise ValueError("Stamp record not found.")

        certificate_number = stamp.CertificateNumber

        try:
            with db.session.begin_nested():
                self._remove_linked_transactions(stamp_id)
                self.ocr_repo.unlink_stamp(stamp_id)
                self.stamp_repo.delete(stamp)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        finally:
            db.session.remove()

        return f"Stamp record permanently deleted for certificate {certificate_number}."

    @staticmethod
    def _audit_context() -> tuple[str | None, str | None]:
        machine = socket.gethostname()
        ip = None
        if request:
            forwarded = request.headers.get("X-Forwarded-For", "")
            ip = forwarded.split(",")[0].strip() if forwarded else request.remote_addr
        return machine[:100] if machine else None, (ip or "")[:45] or None

    @staticmethod
    def _clean(value, max_len: int = 300) -> str | None:
        text = (value or "").strip()
        return text[:max_len] if text else None

    @staticmethod
    def _decimal(value) -> Decimal:
        if value in (None, ""):
            return Decimal("0")
        return Decimal(str(value)).quantize(Decimal("0.01"))

    @staticmethod
    def _decimal_or_none(value):
        if value in (None, ""):
            return None
        return Decimal(str(value)).quantize(Decimal("0.01"))

    @staticmethod
    def _as_date(value) -> date | None:
        if not value:
            return None
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value)[:10])

    @staticmethod
    def _get_form_list(form: dict, key: str) -> list:
        if hasattr(form, "getlist"):
            return list(form.getlist(key) or [])
        value = form.get(key)
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    def _parse_payment_lines(self, form: dict, sale_amount: Decimal) -> list[dict]:
        bank_ids = self._get_form_list(form, "PaymentBankAccountID[]")
        amounts = self._get_form_list(form, "PaymentAmount[]")

        self._logger.info(
            "Parse payment lines bank_count=%s amount_count=%s bank_ids=%s amounts=%s",
            len(bank_ids),
            len(amounts),
            bank_ids,
            amounts,
        )

        if not bank_ids:
            single_bank = form.get("BankAccountID") or form.get("PaymentModeID")
            if single_bank:
                bank_ids = [single_bank]
                amounts = [str(sale_amount)]

        if not bank_ids:
            return []

        if len(amounts) < len(bank_ids):
            amounts.extend([""] * (len(bank_ids) - len(amounts)))

        lines: list[dict] = []
        total = Decimal("0")
        for bank_id_raw, amount_raw in zip(bank_ids, amounts):
            bank_account_id = int(bank_id_raw or 0)
            if bank_account_id <= 0:
                raise ValueError("Each payment mode must be selected.")
            amount = self._decimal(amount_raw)
            if amount <= 0:
                raise ValueError("Each payment amount must be greater than zero.")
            payment_mode_id = self.master_repo.resolve_payment_mode_for_bank_account(bank_account_id)
            total += amount
            lines.append(
                {
                    "bank_account_id": bank_account_id,
                    "payment_mode_id": payment_mode_id,
                    "amount": amount,
                }
            )

        if total < sale_amount:
            raise ValueError(
                f"Payment total ({total}) must be greater than or equal to Sale Amount ({sale_amount})."
            )
        return lines
