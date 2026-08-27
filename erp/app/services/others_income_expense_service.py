from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.transactions import (
    JTCSDailyTransaction,
    JTCSDailyTransactionPayment,
    JtcsBankAccountMaster,
)
from app.customer_master.constants import OTHER_CUSTOMER_TYPE
from app.repositories.customer_repository import CustomerRepository
from app.repositories.others_repository import (
    BILL_NO_PATTERNS,
    OthersIncomeExpenseRepository,
    WorkMasterRepository,
)
from app.repositories.transaction_repository import (
    BankTransactionRepository,
    DailyTransactionPaymentRepository,
    DailyTransactionRepository,
    MasterRepository,
)
from app.services.customer_group_service import CustomerGroupService
from app.services.customer_service import CustomerService
from app.utils.db_session import persist


@dataclass
class OthersIncomeExpenseSaveResult:
    entry_id: int
    bill_no: str
    daily_transaction_id: int | None
    bank_transaction_ids: list[int]
    message: str


class OthersIncomeExpenseService:
    WORK_TYPE = "Others"
    SUB_WORK_TYPE = "Income / Expense"
    LEDGER_INCOME = "Income"
    LEDGER_EXPENSE = "Expense"
    LEDGER_MISC = "Misc."
    LEDGER_KINDS = (LEDGER_INCOME, LEDGER_EXPENSE, LEDGER_MISC)

    def __init__(
        self,
        entry_repo: OthersIncomeExpenseRepository | None = None,
        work_repo: WorkMasterRepository | None = None,
        daily_repo: DailyTransactionRepository | None = None,
        bank_repo: BankTransactionRepository | None = None,
        payment_repo: DailyTransactionPaymentRepository | None = None,
        master_repo: MasterRepository | None = None,
        customer_repo: CustomerRepository | None = None,
        customer_service: CustomerService | None = None,
        group_service: CustomerGroupService | None = None,
    ):
        self.entry_repo = entry_repo or OthersIncomeExpenseRepository()
        self.work_repo = work_repo or WorkMasterRepository()
        self.daily_repo = daily_repo or DailyTransactionRepository()
        self.bank_repo = bank_repo or BankTransactionRepository()
        self.payment_repo = payment_repo or DailyTransactionPaymentRepository()
        self.master_repo = master_repo or MasterRepository()
        self.customer_repo = customer_repo or CustomerRepository()
        self.customer_service = customer_service or CustomerService(self.customer_repo)
        self.group_service = group_service or CustomerGroupService()

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
        raw = form.get("EntryID") or form.get("entry_id")
        if raw in (None, ""):
            return None
        try:
            entry_id = int(raw)
            return entry_id if entry_id > 0 else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _ledger_kind_from_form(form: dict) -> str:
        raw = (
            form.get("LedgerKind")
            or form.get("ledger_kind")
            or form.get("entry_type")
            or ""
        ).strip()
        lower = raw.lower()
        if lower in ("expense", "e") or raw == OthersIncomeExpenseService.LEDGER_EXPENSE:
            return OthersIncomeExpenseService.LEDGER_EXPENSE
        if lower in ("misc.", "misc", "m") or raw == OthersIncomeExpenseService.LEDGER_MISC:
            return OthersIncomeExpenseService.LEDGER_MISC
        if lower in ("income", "i") or raw == OthersIncomeExpenseService.LEDGER_INCOME:
            return OthersIncomeExpenseService.LEDGER_INCOME
        return OthersIncomeExpenseService.LEDGER_INCOME

    @staticmethod
    def _bool_from_form(form: dict, *keys: str) -> bool:
        for key in keys:
            raw = form.get(key)
            if raw is None:
                continue
            if str(raw).strip().lower() in ("1", "true", "on", "yes"):
                return True
        return False

    @staticmethod
    def _int_from_form(form: dict, *keys: str) -> int | None:
        for key in keys:
            raw = form.get(key)
            if raw in (None, ""):
                continue
            try:
                value = int(raw)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return None

    def _parse_payment_lines(
        self, form: dict, entry_amount: Decimal, *, required: bool = True
    ) -> list[dict]:
        bank_ids = self._get_form_list(form, "PaymentBankAccountID[]")
        amounts = self._get_form_list(form, "PaymentAmount[]")
        payment_dates = self._get_form_list(form, "PaymentDate[]")

        if not bank_ids:
            single_bank = form.get("BankAccountID") or form.get("PaymentModeID")
            if single_bank:
                bank_ids = [single_bank]
                amounts = [str(entry_amount)]

        if not bank_ids:
            return []

        if len(amounts) < len(bank_ids):
            amounts.extend([""] * (len(bank_ids) - len(amounts)))
        if len(payment_dates) < len(bank_ids):
            payment_dates.extend([""] * (len(bank_ids) - len(payment_dates)))

        fallback_date = self._date(form.get("WorkDate")) or date.today()
        lines: list[dict] = []
        total = Decimal("0")
        for bank_id_raw, amount_raw, payment_date_raw in zip(bank_ids, amounts, payment_dates):
            try:
                bank_account_id = int(bank_id_raw or 0)
            except (TypeError, ValueError):
                bank_account_id = 0
            try:
                amount = self._decimal(amount_raw)
            except ValueError:
                amount = Decimal("0")
            if bank_account_id <= 0 or amount <= 0:
                if required:
                    if bank_account_id <= 0:
                        raise ValueError("Each payment mode must be selected.")
                    raise ValueError("Each payment amount must be greater than zero.")
                continue
            payment_date = self._date(payment_date_raw) or fallback_date
            payment_mode_id = self.master_repo.resolve_payment_mode_for_bank_account(bank_account_id)
            total += amount
            lines.append(
                {
                    "bank_account_id": bank_account_id,
                    "payment_mode_id": payment_mode_id,
                    "amount": amount,
                    "payment_date": payment_date,
                }
            )

        if not lines:
            return []

        if total < entry_amount:
            kind = self._ledger_kind_from_form(form)
            if kind == self.LEDGER_EXPENSE:
                label = "Expense amount"
            elif kind == self.LEDGER_MISC:
                label = "Misc. amount"
            else:
                label = "Income amount"
            raise ValueError(
                f"Payment received ({total}) must be greater than or equal to {label} ({entry_amount})."
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
        lines: list[dict] = []
        for row in payment_rows:
            payment_date = daily.TransactionDate.isoformat() if daily.TransactionDate else ""
            if row.BankTransactionID:
                bank_row = self.bank_repo.get_by_id(row.BankTransactionID)
                if bank_row is not None and bank_row.TransactionDate:
                    payment_date = bank_row.TransactionDate.isoformat()
            lines.append(
                {
                    "bank_account_id": row.BankAccountID,
                    "amount": str(row.Amount),
                    "payment_mode_id": row.PaymentModeID,
                    "payment_date": payment_date,
                }
            )
        return lines

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
        entry_amount: Decimal,
        payment_lines: list[dict],
        customer_name: str | None,
        remarks: str | None,
        created_by: str,
        existing_daily: JTCSDailyTransaction | None = None,
        ledger_kind: str = LEDGER_INCOME,
    ) -> tuple[JTCSDailyTransaction, list[int]]:
        if ledger_kind == self.LEDGER_MISC:
            description = f"Misc. — {work_name} — {bill_no}"
        else:
            description = f"Income / Expense — {work_name} — {bill_no}"
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
            existing_daily.ExpenseAmount = entry_amount if is_expense else Decimal("0")
            existing_daily.SaleAmount = Decimal("0") if is_expense else entry_amount
            existing_daily.TotalAmount = entry_amount
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
                    "ExpenseAmount": entry_amount if is_expense else Decimal("0"),
                    "SaleAmount": Decimal("0") if is_expense else entry_amount,
                    "PurchaseAmount": Decimal("0"),
                    "GSTAmount": Decimal("0"),
                    "TDSAmount": Decimal("0"),
                    "TotalAmount": entry_amount,
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
            line_date = payment_line.get("payment_date") or work_date
            bank = self.bank_repo.create(
                {
                    "JtcsBankAccountID": bank_account.account_id or 0,
                    "BankName": bank_account.bank_name,
                    "MaskedAccountNumber": bank_account.masked_account_number,
                    "TransactionDate": line_date,
                    "Description": self.SUB_WORK_TYPE,
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

    def _validate_bill_no(self, bill_no: str, ledger_kind: str, *, exclude_id: int | None = None) -> str:
        normalized = (bill_no or "").strip().upper()
        if not normalized:
            raise ValueError("Bill number is required.")
        pattern = BILL_NO_PATTERNS.get(ledger_kind)
        if pattern and not pattern.match(normalized):
            from app.repositories.others_repository import BILL_NO_PREFIX

            prefix = BILL_NO_PREFIX.get(ledger_kind, "S")
            raise ValueError(f"Bill number must match format {prefix}-ddmmyyyy/NNN.")
        existing = self.entry_repo.find_by_bill_no(normalized)
        if existing and (exclude_id is None or existing.EntryID != exclude_id):
            raise ValueError(f"Bill number {normalized} already exists.")
        return normalized

    def next_bill_no(self, work_date: date, *, ledger_kind: str = LEDGER_INCOME) -> str:
        return self.entry_repo.next_bill_no(work_date, ledger_kind=ledger_kind)

    def list_work_types(self, *, ledger_kind: str) -> list[dict]:
        if ledger_kind not in self.LEDGER_KINDS:
            raise ValueError("Ledger kind must be Income, Expense, or Misc.")
        self.entry_repo.ensure_schema()
        return [
            {
                "work_id": row.WorkID,
                "work_name": row.WorkName,
                "ledger_kind": row.LedgerKind,
            }
            for row in self.work_repo.list_active(ledger_kind=ledger_kind)
        ]

    def list_sub_works(self, work_name: str) -> list[dict]:
        """Sub works from WorkTypeMaster where WorkTypeName matches WorkMaster.WorkName."""
        self.entry_repo.ensure_schema()
        rows = self.master_repo.list_sub_works_for_parent(work_name)
        return [
            {
                "work_type_id": row.WorkTypeID,
                "work_type_name": row.WorkTypeName,
                "sub_work_type": row.SubWorkType,
            }
            for row in rows
        ]

    @staticmethod
    def _account_label(bank_name: str | None, account_number: str | None) -> str:
        """Cash stays Cash; otherwise show last 4 digits of the account number."""
        name = (bank_name or "").strip()
        number = (account_number or "").strip()
        if name.casefold() == "cash" or number.casefold() == "cash":
            return "Cash"
        digits = "".join(ch for ch in number if ch.isdigit())
        if len(digits) >= 4:
            return digits[-4:]
        if number:
            return number[-4:] if len(number) > 4 else number
        return "—"

    def _account_labels_by_bill(self, bill_nos: list[str]) -> dict[str, str]:
        normalized = sorted({(bill or "").strip().upper() for bill in bill_nos if (bill or "").strip()})
        if not normalized:
            return {}

        daily_rows = []
        chunk_size = 400
        for offset in range(0, len(normalized), chunk_size):
            chunk = normalized[offset : offset + chunk_size]
            daily_rows.extend(
                db.session.execute(
                    select(
                        JTCSDailyTransaction.TransactionID,
                        JTCSDailyTransaction.ReferenceNo,
                    )
                    .where(
                        JTCSDailyTransaction.ReferenceNo.in_(chunk),
                        JTCSDailyTransaction.WorkType == self.WORK_TYPE,
                        JTCSDailyTransaction.SubWorkType.like(f"{self.SUB_WORK_TYPE}%"),
                    )
                    .order_by(JTCSDailyTransaction.TransactionID.asc())
                ).all()
            )
        if not daily_rows:
            return {}

        latest_tid_by_bill: dict[str, int] = {}
        for transaction_id, reference_no in daily_rows:
            key = (reference_no or "").strip().upper()
            if key:
                latest_tid_by_bill[key] = int(transaction_id)

        transaction_ids = list(latest_tid_by_bill.values())
        payment_rows = []
        for offset in range(0, len(transaction_ids), chunk_size):
            chunk = transaction_ids[offset : offset + chunk_size]
            payment_rows.extend(
                db.session.scalars(
                    select(JTCSDailyTransactionPayment)
                    .where(JTCSDailyTransactionPayment.TransactionID.in_(chunk))
                    .order_by(
                        JTCSDailyTransactionPayment.TransactionID.asc(),
                        JTCSDailyTransactionPayment.PaymentSequence.asc(),
                    )
                ).all()
            )
        bank_ids_by_tid: dict[int, list[int]] = {}
        for payment in payment_rows:
            bank_ids_by_tid.setdefault(payment.TransactionID, []).append(int(payment.BankAccountID))

        bank_ids = {bank_id for ids in bank_ids_by_tid.values() for bank_id in ids}
        accounts: dict[int, JtcsBankAccountMaster] = {}
        if bank_ids:
            for account in db.session.scalars(
                select(JtcsBankAccountMaster).where(
                    JtcsBankAccountMaster.JtcsBankAccountID.in_(bank_ids)
                )
            ).all():
                accounts[account.JtcsBankAccountID] = account

        labels: dict[str, str] = {}
        for bill_no, transaction_id in latest_tid_by_bill.items():
            seen: list[str] = []
            for bank_id in bank_ids_by_tid.get(transaction_id, []):
                account = accounts.get(bank_id)
                if account is None:
                    continue
                label = self._account_label(
                    account.BankName,
                    MasterRepository._stamp_account_number(account),
                )
                if label and label not in seen:
                    seen.append(label)
            labels[bill_no] = ", ".join(seen) if seen else "—"
        return labels

    def list_entries(self, *, ledger_kind: str | None = None) -> list[dict]:
        self.entry_repo.ensure_schema()
        rows = self.entry_repo.list_recent(ledger_kind=ledger_kind)
        entries = [self._entry_dict(row) for row in rows]
        account_map = self._account_labels_by_bill([item.get("bill_no") or "" for item in entries])
        for item in entries:
            item["account_label"] = account_map.get((item.get("bill_no") or "").strip().upper(), "—")
        return entries

    def get_entry(self, entry_id: int) -> dict:
        self.entry_repo.ensure_schema()
        row = self.entry_repo.get_by_id(entry_id)
        if row is None or not row.IsActive:
            raise ValueError("Income / expense record not found.")
        data = self._entry_dict(row)
        daily = self._find_daily_for_bill(row.BillNo)
        if daily:
            data["daily_transaction_id"] = daily.TransactionID
            data["payments"] = self._load_payment_lines(daily)
        else:
            data["daily_transaction_id"] = None
            data["payments"] = []
        return data

    def _category_lines_from_row(self, row) -> list[dict]:
        details = list(getattr(row, "detail_lines", None) or [])
        if details:
            return [
                {
                    "work_id": detail.WorkID,
                    "work_name": detail.work_type.WorkName if detail.work_type else "",
                    "work_type_id": detail.WorkTypeID,
                    "sub_work_type": (
                        detail.sub_work_type.SubWorkType if detail.sub_work_type else ""
                    ),
                    "amount": str(detail.Amount),
                }
                for detail in sorted(details, key=lambda item: item.LineSequence or 0)
            ]
        work = row.work_type
        return [
            {
                "work_id": row.WorkID,
                "work_name": work.WorkName if work else "",
                "work_type_id": None,
                "sub_work_type": "",
                "amount": str(row.Amount),
            }
        ]

    def _entry_dict(self, row) -> dict:
        work = row.work_type
        ledger_kind = work.LedgerKind if work else self.LEDGER_INCOME
        categories = self._category_lines_from_row(row)
        work_names = [item["work_name"] for item in categories if item.get("work_name")]
        return {
            "entry_id": row.EntryID,
            "bill_no": row.BillNo,
            "work_date": row.WorkDate.isoformat() if row.WorkDate else "",
            "work_id": row.WorkID,
            "work_name": ", ".join(work_names) if work_names else (work.WorkName if work else ""),
            "ledger_kind": ledger_kind,
            "amount": str(row.Amount),
            "account_label": "—",
            "categories": categories,
            "customer_name": row.CustomerName or "",
            "mobile_number": row.MobileNumber or "",
            "customer_id": getattr(row, "CustomerID", None) or None,
            "work_done": bool(getattr(row, "WorkDone", False)),
            "tally_bill_generated": bool(getattr(row, "TallyBillGenerated", False)),
            "tally_bill_no": (getattr(row, "TallyBillNo", None) or "") or "",
            "tally_bill_date": (
                row.TallyBillDate.isoformat()
                if getattr(row, "TallyBillDate", None)
                else ""
            ),
            "tally_bill_amount": (
                str(row.TallyBillAmount)
                if getattr(row, "TallyBillAmount", None) is not None
                else ""
            ),
            "remarks": row.Remarks or "",
            "created_date": row.CreatedDate.isoformat() if row.CreatedDate else "",
        }

    def _parse_category_lines(self, form: dict, ledger_kind: str) -> list[dict]:
        work_ids = self._get_form_list(form, "WorkID[]")
        amounts = self._get_form_list(form, "CategoryAmount[]")
        work_type_ids = self._get_form_list(form, "WorkTypeID[]")

        # Backward compatible: single WorkID field
        if not work_ids:
            single = form.get("WorkID") or form.get("work_id")
            if single:
                work_ids = [single]
                amounts = [
                    form.get("CategoryAmount")
                    or form.get("Amount")
                    or form.get("amount")
                    or "0"
                ]
                single_wt = form.get("WorkTypeID") or form.get("work_type_id")
                work_type_ids = [single_wt] if single_wt else [""]

        if not work_ids:
            raise ValueError("At least one category is required.")

        if len(amounts) < len(work_ids):
            amounts.extend([""] * (len(work_ids) - len(amounts)))
        if len(work_type_ids) < len(work_ids):
            work_type_ids.extend([""] * (len(work_ids) - len(work_type_ids)))

        lines: list[dict] = []
        seen: set[int] = set()
        for work_id_raw, amount_raw, work_type_raw in zip(work_ids, amounts, work_type_ids):
            try:
                work_id = int(work_id_raw or 0)
            except (TypeError, ValueError):
                work_id = 0
            if work_id <= 0:
                raise ValueError("Each category must be selected.")
            if work_id in seen:
                raise ValueError("Duplicate categories are not allowed.")
            seen.add(work_id)

            work = self.work_repo.get_by_id(work_id)
            if work is None or not work.ActiveStatus:
                raise ValueError("Selected category is not valid.")
            if work.LedgerKind != ledger_kind:
                raise ValueError(f"Selected category must be a {ledger_kind} type.")

            amount = self._decimal(amount_raw)
            if amount <= 0:
                raise ValueError("Each category amount must be greater than zero.")

            work_type_id = None
            sub_work_name = ""
            if ledger_kind == self.LEDGER_MISC:
                available = self.master_repo.list_sub_works_for_parent(work.WorkName)
                if available:
                    try:
                        work_type_id = int(work_type_raw or 0)
                    except (TypeError, ValueError):
                        work_type_id = 0
                    if work_type_id <= 0:
                        raise ValueError(f"Sub Work is required for {work.WorkName}.")
                    sub = self.master_repo.get_work_type(work_type_id)
                    if (
                        sub is None
                        or not sub.ActiveStatus
                        or (sub.WorkTypeName or "").strip() != (work.WorkName or "").strip()
                    ):
                        raise ValueError(f"Selected Sub Work is not valid for {work.WorkName}.")
                    sub_work_name = sub.SubWorkType or ""

            lines.append(
                {
                    "work_id": work.WorkID,
                    "work_name": work.WorkName,
                    "work_type_id": work_type_id,
                    "sub_work_type": sub_work_name,
                    "amount": amount,
                    "work": work,
                }
            )
        return lines

    def _allocate_bill_no(
        self, work_date: date, bill_raw: str | None, ledger_kind: str
    ) -> str:
        """Assign next free bill number, skipping numbers kept by inactive/deleted rows.

        Income next_bill_no ignores inactive rows, but BillNo is globally unique. Without
        next_bill_no_after, save can loop forever when S-ddmmyyyy/001 (etc.) is soft-deleted.
        """
        bill_no = self.entry_repo.next_bill_no(work_date, ledger_kind=ledger_kind)
        if bill_raw:
            candidate = bill_raw.strip().upper()
            if not self.entry_repo.find_by_bill_no(candidate):
                bill_no = self._validate_bill_no(bill_raw, ledger_kind)
        guard = 0
        while self.entry_repo.find_by_bill_no(bill_no):
            guard += 1
            if guard > 999:
                raise ValueError(f"Unable to allocate a new {ledger_kind} bill number.")
            bill_no = self.entry_repo.next_bill_no_after(bill_no, ledger_kind=ledger_kind)
        return bill_no

    def save_entry(self, form: dict, *, created_by: str) -> OthersIncomeExpenseSaveResult:
        self.entry_repo.ensure_schema()
        entry_id = self._entry_id_from_form(form)
        is_update = entry_id is not None
        ledger_kind = self._ledger_kind_from_form(form)

        work_date = self._date(form.get("WorkDate") or form.get("work_date"))
        if not work_date:
            raise ValueError("Work date is required.")

        category_lines = self._parse_category_lines(form, ledger_kind)
        category_total = sum((line["amount"] for line in category_lines), Decimal("0"))
        if category_total <= 0:
            raise ValueError("Category total must be greater than zero.")

        primary_work = category_lines[0]["work"]
        work_names = []
        for line in category_lines:
            label = line["work_name"]
            if line.get("sub_work_type"):
                label = f"{label} / {line['sub_work_type']}"
            work_names.append(label)
        work_label = ", ".join(work_names)
        if len(work_label) > 80:
            work_label = work_label[:77].rstrip(", ") + "..."

        work_done = self._bool_from_form(form, "WorkDone", "work_done")
        tally_bill = self._bool_from_form(form, "TallyBillGenerated", "tally_bill_generated")
        if ledger_kind != self.LEDGER_MISC:
            work_done = False
            tally_bill = False
        if tally_bill and not work_done:
            raise ValueError("Work Done must be checked before Tally Bill Generated.")

        tally_bill_no = (form.get("TallyBillNo") or form.get("tally_bill_no") or "").strip() or None
        tally_bill_date = self._date(form.get("TallyBillDate") or form.get("tally_bill_date"))
        tally_bill_amount_raw = form.get("TallyBillAmount") or form.get("tally_bill_amount") or ""
        tally_bill_amount = None
        if str(tally_bill_amount_raw).strip():
            tally_bill_amount = self._decimal(tally_bill_amount_raw)

        if tally_bill:
            if not tally_bill_no:
                raise ValueError("Tally bill number is required when Tally Bill Generated is checked.")
            if not tally_bill_amount or tally_bill_amount <= 0:
                raise ValueError("Bill amount is required when Tally Bill Generated is checked.")
            if not tally_bill_date:
                tally_bill_date = work_date
        else:
            tally_bill_no = None
            tally_bill_date = None
            tally_bill_amount = None

        if ledger_kind == self.LEDGER_MISC and not tally_bill:
            payment_lines = []
        else:
            payment_lines = self._parse_payment_lines(
                form, category_total, required=ledger_kind != self.LEDGER_MISC
            )
        if ledger_kind != self.LEDGER_MISC and not payment_lines:
            raise ValueError("At least one payment mode is required.")

        received_total = sum((line["amount"] for line in payment_lines), Decimal("0"))
        if ledger_kind != self.LEDGER_MISC:
            if received_total <= 0:
                raise ValueError("Payment amount must be greater than zero.")
        amount = category_total
        customer_name = (form.get("CustomerName") or form.get("customer_name") or "").strip() or None
        mobile_number = (form.get("MobileNumber") or form.get("mobile_number") or "").strip() or None
        customer_id = self._int_from_form(form, "CustomerID", "customer_id")
        remarks = (form.get("Remarks") or form.get("remarks") or "").strip() or None
        if tally_bill and not customer_name:
            raise ValueError("Customer name is required when Tally Bill Generated is checked.")

        existing_row = None
        if is_update:
            existing_row = self.entry_repo.get_by_id(entry_id)
            if existing_row is None or not existing_row.IsActive:
                raise ValueError("Income / expense record not found.")

        bill_raw = (form.get("BillNo") or form.get("bill_no") or "").strip()
        if is_update and existing_row:
            if bill_raw:
                bill_no = self._validate_bill_no(bill_raw, ledger_kind, exclude_id=entry_id)
            else:
                bill_no = existing_row.BillNo
        else:
            bill_no = self._allocate_bill_no(work_date, bill_raw, ledger_kind)

        def _write() -> OthersIncomeExpenseSaveResult:
            payload = {
                "BillNo": bill_no,
                "WorkDate": work_date,
                "WorkID": primary_work.WorkID,
                "Amount": amount,
                "CustomerName": customer_name,
                "MobileNumber": mobile_number,
                "CustomerID": customer_id,
                "WorkDone": work_done,
                "TallyBillGenerated": tally_bill,
                "TallyBillNo": tally_bill_no,
                "TallyBillDate": tally_bill_date,
                "TallyBillAmount": tally_bill_amount,
                "Remarks": remarks,
            }
            existing_daily = None
            if is_update and existing_row:
                row = self.entry_repo.update(existing_row, payload)
                dailies = self._list_dailies_for_bill(row.BillNo)
                if dailies:
                    existing_daily = dailies[-1]
                    for extra in dailies[:-1]:
                        self._remove_daily_transaction(extra)
                action = "updated"
            else:
                payload["CreatedBy"] = created_by
                payload["CreatedDate"] = datetime.utcnow()
                payload["IsActive"] = True
                row = self.entry_repo.create(payload)
                action = "saved"

            self.entry_repo.replace_detail_lines(
                row.EntryID,
                [
                    {
                        "work_id": line["work_id"],
                        "work_type_id": line.get("work_type_id"),
                        "amount": line["amount"],
                    }
                    for line in category_lines
                ],
            )

            daily = None
            bank_ids: list[int] = []
            if payment_lines:
                daily, bank_ids = self._repost_transactions(
                    bill_no=row.BillNo,
                    work_date=work_date,
                    work_name=work_label,
                    entry_amount=amount,
                    payment_lines=payment_lines,
                    customer_name=customer_name,
                    remarks=remarks,
                    created_by=created_by,
                    existing_daily=existing_daily,
                    ledger_kind=ledger_kind,
                )
            elif existing_daily is not None:
                self._remove_daily_transaction(existing_daily)

            if daily is not None:
                message = (
                    f"{action.capitalize()} bill {row.BillNo} ({ledger_kind}, {amount}). "
                    f"Payment received {received_total}. Daily Transaction #{daily.TransactionID}."
                )
            elif tally_bill:
                message = (
                    f"{action.capitalize()} bill {row.BillNo} ({ledger_kind}, {amount}). "
                    "Tally bill generated — payment pending."
                )
            elif work_done:
                message = (
                    f"{action.capitalize()} bill {row.BillNo} ({ledger_kind}, {amount}). Work done."
                )
            else:
                message = f"{action.capitalize()} bill {row.BillNo} ({ledger_kind}, {amount})."

            return OthersIncomeExpenseSaveResult(
                entry_id=row.EntryID,
                bill_no=row.BillNo,
                daily_transaction_id=daily.TransactionID if daily is not None else None,
                bank_transaction_ids=bank_ids,
                message=message,
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

    def delete_entry(self, entry_id: int) -> str:
        self.entry_repo.ensure_schema()
        row = self.entry_repo.get_by_id(entry_id)
        if row is None or not row.IsActive:
            raise ValueError("Income / expense record not found.")

        bill_no = row.BillNo
        try:
            with db.session.begin_nested():
                self._remove_linked_transactions(bill_no)
                self.entry_repo.deactivate(row)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return f"Deleted bill {bill_no}."

    def search_customers(self, query: str, *, limit: int = 20) -> list[dict]:
        return self.customer_service.search(query, limit=limit)

    def list_customer_groups(self) -> list[dict]:
        self.group_service.repository.ensure_schema()
        return self.group_service.list_active_groups()

    def create_customer(self, payload: dict) -> dict:
        """Quick customer create for Income / Expense popup (module-specific fields)."""
        group = (payload.get("customer_group") or payload.get("CustomerGroup") or "").strip().upper()
        customer_type = (payload.get("customer_type") or payload.get("CustomerType") or "").strip()
        name = (payload.get("customer_name") or payload.get("CustomerName") or "").strip()
        pan = self.customer_repo._normalize_pan(payload.get("pan_number") or payload.get("PANNumber"))
        aadhaar = re.sub(r"\D", "", str(payload.get("aadhaar_number") or payload.get("AadhaarNumber") or ""))
        dob_raw = (payload.get("date_of_birth") or payload.get("DateOfBirth") or "").strip()
        email = (payload.get("email_id") or payload.get("EmailID") or "").strip()
        mobile = self.customer_repo._normalize_mobile(
            payload.get("mobile_number") or payload.get("MobileNumber")
        )
        remarks = (payload.get("remarks") or payload.get("Remarks") or "").strip() or None
        is_other = customer_type.casefold() == OTHER_CUSTOMER_TYPE.casefold()

        active_codes = {item["code"] for item in self.list_customer_groups()}
        if not group or group not in active_codes:
            raise ValueError("Customer group is required.")
        if not customer_type:
            raise ValueError("Customer type is required.")
        if not name:
            raise ValueError("Customer name is required.")

        if is_other:
            # Other: only name mandatory; blank PAN becomes reusable placeholder.
            if not pan:
                pan = CustomerRepository.PLACEHOLDER_PAN
            elif len(pan) != 10:
                raise ValueError("Valid 10-character PAN is required.")
            if aadhaar and len(aadhaar) != 12:
                raise ValueError("Valid 12-digit Aadhaar is required.")
            if mobile and len(mobile) != 10:
                raise ValueError("Valid 10-digit mobile number is required.")
            if email and ("@" not in email or "." not in email.split("@")[-1]):
                raise ValueError("Valid email ID is required.")
            if dob_raw:
                try:
                    date.fromisoformat(dob_raw[:10])
                except ValueError as exc:
                    raise ValueError("Valid date of birth is required.") from exc
        else:
            if not pan or len(pan) != 10:
                raise ValueError("Valid 10-character PAN is required.")
            if not aadhaar or len(aadhaar) != 12:
                raise ValueError("Valid 12-digit Aadhaar is required.")
            if not dob_raw:
                raise ValueError("Date of birth is required.")
            try:
                date.fromisoformat(dob_raw[:10])
            except ValueError as exc:
                raise ValueError("Valid date of birth is required.") from exc
            if not email or "@" not in email or "." not in email.split("@")[-1]:
                raise ValueError("Valid email ID is required.")
            if not mobile or len(mobile) != 10:
                raise ValueError("Valid 10-digit mobile number is required.")

        pan_dup = self.customer_repo.find_by_pan(pan)
        if pan_dup:
            raise ValueError(
                f"PAN already exists for customer {pan_dup['customer_name']} "
                f"(ID {pan_dup['customer_id']})."
            )
        if aadhaar:
            aadhaar_dup = self.customer_repo.find_by_aadhaar(aadhaar)
            if aadhaar_dup:
                raise ValueError(
                    f"Aadhaar already exists for customer {aadhaar_dup['customer_name']} "
                    f"(ID {aadhaar_dup['customer_id']})."
                )

        save_payload = {
            "customer_group": group,
            "customer_type": customer_type,
            "customer_name": name,
            "pan_number": pan,
            "aadhaar_number": aadhaar or None,
            "date_of_birth": (dob_raw[:10] if dob_raw else None),
            "email_id": email or None,
            "mobile_number": mobile or None,
            "customer_status": "Active",
        }
        if remarks:
            save_payload["remarks"] = remarks

        def _write() -> dict:
            return self.customer_repo.save_full(save_payload)

        return persist(_write)
