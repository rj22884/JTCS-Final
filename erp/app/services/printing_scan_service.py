from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.transactions import JTCSDailyTransaction
from app.repositories.others_repository import PrintingScanRepository, WorkMasterRepository
from app.repositories.transaction_repository import (
    BankTransactionRepository,
    DailyTransactionPaymentRepository,
    DailyTransactionRepository,
    MasterRepository,
)


@dataclass
class PrintingScanSaveResult:
    printing_scan_id: int
    daily_transaction_id: int
    bank_transaction_ids: list[int]
    message: str


class PrintingScanService:
    WORK_TYPE = "Others"
    SUB_WORK_TYPE = "Printing and Scanning"
    LEDGER_INCOME = "Income"
    LEDGER_EXPENSE = "Expense"

    def __init__(
        self,
        printing_repo: PrintingScanRepository | None = None,
        work_repo: WorkMasterRepository | None = None,
        daily_repo: DailyTransactionRepository | None = None,
        bank_repo: BankTransactionRepository | None = None,
        payment_repo: DailyTransactionPaymentRepository | None = None,
        master_repo: MasterRepository | None = None,
    ):
        self.printing_repo = printing_repo or PrintingScanRepository()
        self.work_repo = work_repo or WorkMasterRepository()
        self.daily_repo = daily_repo or DailyTransactionRepository()
        self.bank_repo = bank_repo or BankTransactionRepository()
        self.payment_repo = payment_repo or DailyTransactionPaymentRepository()
        self.master_repo = master_repo or MasterRepository()

    @staticmethod
    def _decimal(value) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Invalid amount.") from None

    @staticmethod
    def _date(value) -> date | None:
        raw = (value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None

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

    @staticmethod
    def _entry_id_from_form(form: dict) -> int | None:
        raw = form.get("PrintingScanID") or form.get("printing_scan_id")
        if raw in (None, ""):
            return None
        try:
            entry_id = int(raw)
            return entry_id if entry_id > 0 else None
        except (TypeError, ValueError):
            return None

    def _parse_payment_lines(self, form: dict, sale_amount: Decimal) -> list[dict]:
        bank_ids = self._get_form_list(form, "PaymentBankAccountID[]")
        amounts = self._get_form_list(form, "PaymentAmount[]")

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
                f"Received amount ({total}) must be greater than or equal to Sale Value ({sale_amount})."
            )
        return lines

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

    def _load_payment_lines(self, daily: JTCSDailyTransaction) -> list[dict]:
        payment_rows = self.payment_repo.list_by_transaction(daily.TransactionID)
        return [
            {
                "bank_account_id": row.BankAccountID,
                "amount": str(row.Amount),
                "payment_mode_id": row.PaymentModeID,
            }
            for row in payment_rows
        ]

    def _find_daily_for_bill(self, bill_no: str) -> JTCSDailyTransaction | None:
        normalized = (bill_no or "").strip().upper()
        stmt = (
            select(JTCSDailyTransaction)
            .where(
                JTCSDailyTransaction.ReferenceNo == normalized,
                JTCSDailyTransaction.WorkType == self.WORK_TYPE,
                JTCSDailyTransaction.SubWorkType.like(f"{self.SUB_WORK_TYPE}%"),
            )
            .order_by(JTCSDailyTransaction.TransactionID.desc())
        )
        return db.session.scalars(stmt).first()

    def _list_dailies_for_bill(self, bill_no: str) -> list[JTCSDailyTransaction]:
        normalized = (bill_no or "").strip().upper()
        stmt = (
            select(JTCSDailyTransaction)
            .where(
                JTCSDailyTransaction.ReferenceNo == normalized,
                JTCSDailyTransaction.WorkType == self.WORK_TYPE,
                JTCSDailyTransaction.SubWorkType.like(f"{self.SUB_WORK_TYPE}%"),
            )
            .order_by(JTCSDailyTransaction.TransactionID.asc())
        )
        return list(db.session.scalars(stmt).all())

    def _remove_daily_transaction(self, daily: JTCSDailyTransaction) -> None:
        payment_rows = self.payment_repo.list_by_transaction(daily.TransactionID)
        bank_rows = self._collect_bank_rows_for_daily(daily, payment_rows)
        self.payment_repo.delete_by_transaction(daily.TransactionID)
        daily.BankTransactionID = None
        db.session.flush()
        for bank_row in bank_rows:
            self.bank_repo.delete(bank_row)
        self.daily_repo.delete(daily)

    def _remove_linked_transactions(self, bill_no: str) -> None:
        for daily in self._list_dailies_for_bill(bill_no):
            self._remove_daily_transaction(daily)

    def _repost_transactions(
        self,
        *,
        bill_no: str,
        work_date: date,
        work_name: str,
        sale_amount: Decimal,
        payment_lines: list[dict],
        customer_name: str | None,
        remarks: str | None,
        created_by: str,
        existing_daily: JTCSDailyTransaction | None = None,
        ledger_kind: str = LEDGER_INCOME,
    ) -> tuple[JTCSDailyTransaction, list[int]]:
        description = f"Printing & Scanning — {work_name} — {bill_no}"
        is_expense = ledger_kind == self.LEDGER_EXPENSE

        if existing_daily is not None:
            bank_rows = self._collect_bank_rows_for_daily(existing_daily)
            self.payment_repo.delete_by_transaction(existing_daily.TransactionID)
            existing_daily.BankTransactionID = None
            db.session.flush()
            for bank_row in bank_rows:
                self.bank_repo.delete(bank_row)

            existing_daily.TransactionDate = work_date
            existing_daily.CustomerName = customer_name
            existing_daily.ReferenceNo = bill_no
            existing_daily.Description = description
            existing_daily.IncomeAmount = Decimal("0")
            existing_daily.ExpenseAmount = sale_amount if is_expense else Decimal("0")
            existing_daily.SaleAmount = Decimal("0") if is_expense else sale_amount
            existing_daily.TotalAmount = sale_amount
            existing_daily.PaymentModeID = payment_lines[0]["payment_mode_id"]
            existing_daily.PaymentSplitCount = len(payment_lines)
            existing_daily.Remarks = remarks
            existing_daily.SubWorkType = f"{self.SUB_WORK_TYPE} - {work_name}"
            existing_daily.ModifiedDate = datetime.utcnow()
            db.session.flush()
            daily = existing_daily
        else:
            daily = self.daily_repo.create(
                {
                    "TransactionDate": work_date,
                    "WorkType": self.WORK_TYPE,
                    "SubWorkType": f"{self.SUB_WORK_TYPE} - {work_name}",
                    "CustomerName": customer_name,
                    "ReferenceNo": bill_no,
                    "Description": description,
                    "IncomeAmount": Decimal("0"),
                    "ExpenseAmount": sale_amount if is_expense else Decimal("0"),
                    "SaleAmount": Decimal("0") if is_expense else sale_amount,
                    "PurchaseAmount": Decimal("0"),
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
        bank_ledger = "PAYMENT" if is_expense else "RECEIPT"
        for index, payment_line in enumerate(payment_lines, start=1):
            bank_account = self.master_repo.resolve_bank_account_by_id(payment_line["bank_account_id"])
            bank = self.bank_repo.create(
                {
                    "JtcsBankAccountID": bank_account.account_id or 0,
                    "BankName": bank_account.bank_name,
                    "MaskedAccountNumber": bank_account.masked_account_number,
                    "TransactionDate": work_date,
                    "Description": "Printing & Scanning",
                    "Debit": None if is_expense else payment_line["amount"],
                    "Credit": payment_line["amount"] if is_expense else None,
                    "ClosingBalance": Decimal("0"),
                    "ImportedBy": created_by,
                    "ImportedDate": datetime.utcnow(),
                    "Remarks": bill_no,
                    "IsLocked": False,
                    "SourceTable": self.bank_repo.SOURCE_TABLE,
                    "SourceRecordID": daily.TransactionID,
                    "SourceType": self.WORK_TYPE,
                    "SourceID": daily.TransactionID,
                    "LedgerKind": bank_ledger,
                    "PaymentModeID": payment_line["payment_mode_id"],
                    "PaymentSequence": index,
                }
            )
            bank_ids.append(bank.JtcsBankTransactionID)
            self.payment_repo.create(
                {
                    "TransactionID": daily.TransactionID,
                    "PaymentSequence": index,
                    "PaymentModeID": payment_line["payment_mode_id"],
                    "BankAccountID": payment_line["bank_account_id"],
                    "Amount": payment_line["amount"],
                    "BankTransactionID": bank.JtcsBankTransactionID,
                }
            )

        if bank_ids:
            self.daily_repo.update_bank_link(daily, bank_ids[0])

        return daily, bank_ids

    def next_bill_no(self, work_date: date, *, ledger_kind: str = LEDGER_INCOME) -> str:
        return self.printing_repo.next_bill_no(work_date, ledger_kind=ledger_kind)

    def list_work_types(self, *, ledger_kind: str) -> list[dict]:
        if ledger_kind not in (self.LEDGER_INCOME, self.LEDGER_EXPENSE):
            raise ValueError("Ledger kind must be Income or Expense.")
        return [
            {
                "work_id": row.WorkID,
                "work_name": row.WorkName,
                "ledger_kind": row.LedgerKind,
            }
            for row in self.work_repo.list_active(ledger_kind=ledger_kind)
        ]

    def list_income_work_types(self) -> list[dict]:
        return self.list_work_types(ledger_kind=self.LEDGER_INCOME)

    def list_expense_work_types(self) -> list[dict]:
        return self.list_work_types(ledger_kind=self.LEDGER_EXPENSE)

    def list_work_master(self, *, ledger_kind: str | None = None) -> list[dict]:
        rows = self.work_repo.list_active(ledger_kind=ledger_kind)
        return [
            {
                "work_id": row.WorkID,
                "work_name": row.WorkName,
                "ledger_kind": row.LedgerKind,
                "active_status": row.ActiveStatus,
            }
            for row in rows
        ]

    def save_work_master(self, payload: dict) -> dict:
        work_name = (payload.get("work_name") or payload.get("WorkName") or "").strip()
        ledger_kind = (payload.get("ledger_kind") or payload.get("LedgerKind") or "").strip()
        if not work_name:
            raise ValueError("Work name is required.")
        if ledger_kind not in ("Income", "Expense"):
            raise ValueError("Ledger kind must be Income or Expense.")

        work_id = payload.get("work_id") or payload.get("WorkID")
        if work_id:
            row = self.work_repo.get_by_id(int(work_id))
            if row is None:
                raise ValueError("Work type not found.")
            existing = self.work_repo.find_by_name_kind(work_name, ledger_kind)
            if existing and existing.WorkID != row.WorkID:
                raise ValueError(f"Work name '{work_name}' already exists for {ledger_kind}.")
            row = self.work_repo.update(row, {"WorkName": work_name, "LedgerKind": ledger_kind})
            return {"work_id": row.WorkID, "message": "Work type updated."}

        if self.work_repo.find_by_name_kind(work_name, ledger_kind):
            raise ValueError(f"Work name '{work_name}' already exists for {ledger_kind}.")
        row = self.work_repo.create(
            {
                "WorkName": work_name,
                "LedgerKind": ledger_kind,
                "ActiveStatus": True,
                "CreatedDate": datetime.utcnow(),
            }
        )
        return {"work_id": row.WorkID, "message": "Work type added."}

    def delete_work_master(self, work_id: int) -> dict:
        row = self.work_repo.get_by_id(work_id)
        if row is None:
            raise ValueError("Work type not found.")
        self.work_repo.deactivate(row)
        return {"work_id": row.WorkID, "message": "Work type deactivated."}

    def list_entries(self, *, ledger_kind: str | None = None) -> list[dict]:
        rows = self.printing_repo.list_recent(ledger_kind=ledger_kind or self.LEDGER_INCOME)
        return [self._entry_dict(row) for row in rows]

    def get_entry(self, printing_scan_id: int) -> dict:
        row = self.printing_repo.get_by_id(printing_scan_id)
        if row is None or not row.IsActive:
            raise ValueError("Printing & scanning record not found.")
        data = self._entry_dict(row)
        daily = self._find_daily_for_bill(row.BillNo)
        if daily:
            data["daily_transaction_id"] = daily.TransactionID
            data["payments"] = self._load_payment_lines(daily)
        else:
            data["daily_transaction_id"] = None
            data["payments"] = []
        return data

    def _entry_dict(self, row) -> dict:
        work = row.work_type
        return {
            "printing_scan_id": row.PrintingScanID,
            "bill_no": row.BillNo,
            "work_date": row.WorkDate.isoformat() if row.WorkDate else "",
            "work_id": row.WorkID,
            "work_name": work.WorkName if work else "",
            "sale_amount": str(row.SaleAmount),
            "customer_name": row.CustomerName or "",
            "mobile_number": row.MobileNumber or "",
            "remarks": row.Remarks or "",
            "created_date": row.CreatedDate.isoformat() if row.CreatedDate else "",
        }

    def save_entry(
        self,
        form: dict,
        *,
        created_by: str,
        ledger_kind: str = LEDGER_INCOME,
    ) -> PrintingScanSaveResult:
        if ledger_kind not in (self.LEDGER_INCOME, self.LEDGER_EXPENSE):
            raise ValueError("Ledger kind must be Income or Expense.")

        entry_id = self._entry_id_from_form(form)
        is_update = entry_id is not None

        work_date = self._date(form.get("WorkDate") or form.get("work_date"))
        if not work_date:
            raise ValueError("Work date is required.")

        work_id_raw = form.get("WorkID") or form.get("work_id")
        if not work_id_raw:
            raise ValueError("Work type is required.")
        work = self.work_repo.get_by_id(int(work_id_raw))
        if work is None or not work.ActiveStatus:
            raise ValueError("Selected work type is not valid.")
        if work.LedgerKind != ledger_kind:
            raise ValueError(f"Selected work type must be an {ledger_kind} type.")

        sale_amount = self._decimal(form.get("SaleAmount") or form.get("sale_amount"))
        if sale_amount <= 0:
            raise ValueError("Sale value must be greater than zero.")

        payment_lines = self._parse_payment_lines(form, sale_amount)
        if not payment_lines:
            raise ValueError("At least one payment mode is required.")

        received_total = sum((line["amount"] for line in payment_lines), Decimal("0"))
        customer_name = (form.get("CustomerName") or "").strip() or None
        mobile_number = (form.get("MobileNumber") or "").strip() or None
        remarks = (form.get("Remarks") or "").strip() or None

        existing_row = None
        if is_update:
            existing_row = self.printing_repo.get_by_id(entry_id)
            if existing_row is None or not existing_row.IsActive:
                raise ValueError("Printing & scanning record not found.")
            bill_no = existing_row.BillNo
        else:
            bill_no = self.printing_repo.next_bill_no(work_date, ledger_kind=ledger_kind)
            if self.printing_repo.find_by_bill_no(bill_no):
                raise ValueError(f"Bill number {bill_no} already exists.")

        bill_no = bill_no.strip().upper()

        def _write() -> PrintingScanSaveResult:
            existing_daily = None
            if is_update and existing_row:
                printing = self.printing_repo.update(
                    existing_row,
                    {
                        "WorkDate": work_date,
                        "WorkID": work.WorkID,
                        "SaleAmount": sale_amount,
                        "CustomerName": customer_name,
                        "MobileNumber": mobile_number,
                        "Remarks": remarks,
                    },
                )
                dailies = self._list_dailies_for_bill(printing.BillNo)
                if dailies:
                    existing_daily = dailies[-1]
                    for extra in dailies[:-1]:
                        self._remove_daily_transaction(extra)
            else:
                printing = self.printing_repo.create(
                    {
                        "BillNo": bill_no,
                        "WorkDate": work_date,
                        "WorkID": work.WorkID,
                        "SaleAmount": sale_amount,
                        "CustomerName": customer_name,
                        "MobileNumber": mobile_number,
                        "Remarks": remarks,
                        "CreatedBy": created_by,
                        "CreatedDate": datetime.utcnow(),
                        "IsActive": True,
                    }
                )

            daily, bank_ids = self._repost_transactions(
                bill_no=printing.BillNo,
                work_date=work_date,
                work_name=work.WorkName,
                sale_amount=sale_amount,
                payment_lines=payment_lines,
                customer_name=customer_name,
                remarks=remarks,
                created_by=created_by,
                existing_daily=existing_daily,
                ledger_kind=ledger_kind,
            )

            action = "updated" if is_update else "saved"
            return PrintingScanSaveResult(
                printing_scan_id=printing.PrintingScanID,
                daily_transaction_id=daily.TransactionID,
                bank_transaction_ids=bank_ids,
                message=(
                    f"{action.capitalize()} bill {printing.BillNo}. Sale {sale_amount}, received {received_total}. "
                    f"Daily Transaction #{daily.TransactionID}."
                ),
            )

        try:
            with db.session.begin_nested():
                result = _write()
            db.session.commit()
            return result
        except IntegrityError as exc:
            db.session.rollback()
            if "BillNo" in str(exc.orig):
                raise ValueError(f"Bill number {bill_no} already exists.") from exc
            raise
        except Exception:
            db.session.rollback()
            raise

    def delete_entry(self, printing_scan_id: int) -> str:
        row = self.printing_repo.get_by_id(printing_scan_id)
        if row is None or not row.IsActive:
            raise ValueError("Printing & scanning record not found.")

        bill_no = row.BillNo
        try:
            with db.session.begin_nested():
                self._remove_linked_transactions(bill_no)
                self.printing_repo.deactivate(row)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return f"Deleted bill {bill_no}."
