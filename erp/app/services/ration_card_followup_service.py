from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.ration_card import PdsAroMaster, PdsDistrictMaster, PdsDsoMaster, PdsFpsMaster, PdsStateMaster
from app.models.transactions import JTCSDailyTransaction
from app.repositories.customer_repository import CustomerRepository
from app.repositories.ration_card_followup_repository import (
    BILL_NO_PATTERN,
    RationCardFollowupRepository,
)
from app.repositories.transaction_repository import (
    BankTransactionRepository,
    DailyTransactionPaymentRepository,
    DailyTransactionRepository,
    MasterRepository,
)
from app.utils.db_session import persist
from app.utils.tally_bill import normalize_tally_bill_key


@dataclass
class RationCardFollowupSaveResult:
    entry_id: int
    bill_no: str
    daily_transaction_id: int | None
    bank_transaction_ids: list[int]
    message: str


class RationCardFollowupService:
    WORK_TYPE = "Others"
    SUB_WORK_TYPE = "Ration Card Followup"
    MODULE_CODE = "RCF"

    def __init__(
        self,
        entry_repo: RationCardFollowupRepository | None = None,
        daily_repo: DailyTransactionRepository | None = None,
        bank_repo: BankTransactionRepository | None = None,
        payment_repo: DailyTransactionPaymentRepository | None = None,
        master_repo: MasterRepository | None = None,
    ):
        self.entry_repo = entry_repo or RationCardFollowupRepository()
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
        raw = form.get("EntryID") or form.get("entry_id")
        if raw in (None, ""):
            return None
        try:
            entry_id = int(raw)
            return entry_id if entry_id > 0 else None
        except (TypeError, ValueError):
            return None

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

    def _form_has_positive_payment_amount(self, form: dict) -> bool:
        for raw in self._get_form_list(form, "PaymentAmount[]"):
            try:
                if self._decimal(raw) > 0:
                    return True
            except ValueError:
                continue
        return False

    def _form_payment_line_count(self, form: dict) -> int:
        return sum(1 for raw in self._get_form_list(form, "PaymentBankAccountID[]") if str(raw or "").strip())

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
        fallback_date = self._date(form.get("WorkDate") or form.get("work_date")) or date.today()
        lines: list[dict] = []
        for bank_id_raw, amount_raw, payment_date_raw in zip(bank_ids, amounts, payment_dates):
            try:
                bank_account_id = int(bank_id_raw or 0)
            except (TypeError, ValueError):
                bank_account_id = 0
            try:
                amount = self._decimal(amount_raw)
            except ValueError:
                amount = Decimal("0")
            payment_date = self._date(payment_date_raw) or (fallback_date if not required else None)
            if payment_date is None and required:
                raise ValueError("Each payment line must have a date.")
            if bank_account_id <= 0 or amount <= 0:
                if required:
                    if bank_account_id <= 0:
                        raise ValueError("Each payment mode must be selected.")
                    raise ValueError("Each payment amount must be greater than zero.")
                continue
            payment_mode_id = self.master_repo.resolve_payment_mode_for_bank_account(bank_account_id)
            lines.append(
                {
                    "bank_account_id": bank_account_id,
                    "payment_mode_id": payment_mode_id,
                    "amount": amount,
                    "payment_date": payment_date or fallback_date,
                }
            )
        return lines

    def _collect_bank_rows_for_daily(self, daily: JTCSDailyTransaction, payment_rows: list | None = None) -> list:
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

    def _load_payment_lines(self, daily: JTCSDailyTransaction) -> list[dict]:
        lines: list[dict] = []
        for row in self.payment_repo.list_by_transaction(daily.TransactionID):
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

    def _find_daily_for_bill(self, bill_no: str) -> JTCSDailyTransaction | None:
        rows = self._list_dailies_for_bill(bill_no)
        return rows[-1] if rows else None

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
        fps_label: str,
        entry_amount: Decimal,
        payment_lines: list[dict],
        customer_name: str | None,
        remarks: str | None,
        created_by: str,
        existing_daily: JTCSDailyTransaction | None = None,
    ) -> tuple[JTCSDailyTransaction, list[int]]:
        description = f"{self.SUB_WORK_TYPE} — {fps_label} — {bill_no}"
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
            existing_daily.ExpenseAmount = Decimal("0")
            existing_daily.SaleAmount = entry_amount
            existing_daily.TotalAmount = entry_amount
            existing_daily.PaymentModeID = payment_lines[0]["payment_mode_id"]
            existing_daily.PaymentSplitCount = len(payment_lines)
            existing_daily.Remarks = remarks
            existing_daily.SubWorkType = f"{self.SUB_WORK_TYPE} - {fps_label}"[:100]
            existing_daily.ModifiedDate = datetime.utcnow()
            db.session.flush()
            daily = existing_daily
        else:
            daily = self.daily_repo.create(
                {
                    "TransactionDate": work_date,
                    "WorkType": self.WORK_TYPE,
                    "SubWorkType": f"{self.SUB_WORK_TYPE} - {fps_label}"[:100],
                    "CustomerName": customer_name,
                    "ReferenceNo": bill_no,
                    "Description": description,
                    "IncomeAmount": Decimal("0"),
                    "ExpenseAmount": Decimal("0"),
                    "SaleAmount": entry_amount,
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
                    "Debit": payment_line["amount"],
                    "Credit": None,
                    "ClosingBalance": Decimal("0"),
                    "ImportedBy": created_by,
                    "ImportedDate": datetime.utcnow(),
                    "Remarks": bill_no,
                    "IsLocked": False,
                    "SourceTable": self.bank_repo.SOURCE_TABLE,
                    "SourceRecordID": daily.TransactionID,
                    "SourceType": self.WORK_TYPE,
                    "SourceID": daily.TransactionID,
                    "LedgerKind": "RECEIPT",
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

    def _validate_bill_no(self, bill_no: str, *, exclude_id: int | None = None) -> str:
        normalized = (bill_no or "").strip().upper()
        if not normalized:
            raise ValueError("Bill number is required.")
        if not BILL_NO_PATTERN.match(normalized):
            raise ValueError("Bill number must match format R-ddmmyyyy/NNN.")
        existing = self.entry_repo.find_by_bill_no(normalized)
        if existing and (exclude_id is None or existing.EntryID != exclude_id):
            raise ValueError(f"Bill number {normalized} already exists.")
        return normalized

    def _allocate_bill_no(self, work_date: date, bill_raw: str | None) -> str:
        bill_no = self.entry_repo.next_bill_no(work_date)
        if bill_raw:
            candidate = bill_raw.strip().upper()
            if not self.entry_repo.find_by_bill_no(candidate):
                bill_no = self._validate_bill_no(bill_raw)
        guard = 0
        while self.entry_repo.find_by_bill_no(bill_no):
            guard += 1
            if guard > 999:
                raise ValueError("Unable to allocate a new Ration Card Followup bill number.")
            bill_no = self.entry_repo.next_bill_no_after(bill_no)
        return bill_no

    def _resolve_fps(self, form: dict) -> dict:
        fps_row_id = self._int_from_form(form, "FpsRowID", "fps_row_id")
        if not fps_row_id:
            raise ValueError("Select a PDS FPS shop.")
        fps = db.session.get(PdsFpsMaster, fps_row_id)
        if fps is None or not fps.ActiveStatus:
            raise ValueError("Selected FPS is not valid.")

        district = db.session.get(PdsDistrictMaster, fps.DistrictID) if fps.DistrictID else None
        state = db.session.get(PdsStateMaster, district.StateID) if district else None
        dso = db.session.get(PdsDsoMaster, fps.DsoID) if fps.DsoID else None
        aro = db.session.get(PdsAroMaster, fps.AroID) if fps.AroID else None

        dealer_name = (fps.DealerName or fps.FpsName or "").strip()
        fps_name = (fps.FpsName or "").strip()
        fps_code = (fps.FpsCode or "").strip()
        return {
            "fps_row_id": fps.FpsRowID,
            "fps_code": fps_code,
            "fps_name": fps_name,
            "dealer_name": dealer_name,
            "state_name": (state.StateName if state else "") or "",
            "district_name": (district.DistrictName if district else "") or "",
            "dso_name": (dso.DsoName if dso else "") or "",
            "aro_name": (aro.AroName if aro else "") or "",
            "display_name": dealer_name or fps_name or fps_code or f"FPS #{fps.FpsRowID}",
        }

    def next_bill_no(self, work_date: date) -> str:
        return self.entry_repo.next_bill_no(work_date)

    @staticmethod
    def build_fps_customer_name(fps_name: str, fps_code: str) -> str:
        name = (fps_name or "").strip()
        code = (fps_code or "").strip()
        if not name or not code:
            raise ValueError("FPS name and FPS code are required to create customer.")
        return f"{name} - {code}"[:255]

    def find_fps_customer(self, fps_name: str, fps_code: str) -> dict | None:
        """Find existing Customer Master row for this FPS (name+code), no duplicates."""
        customer_name = self.build_fps_customer_name(fps_name, fps_code)
        code = (fps_code or "").strip()
        marker = f"RCF|FPS:{code}"
        row = db.session.execute(
            text(
                """
                SELECT TOP 1 CustomerID, CustomerName, MobileNumber
                FROM dbo.CustomerMaster
                WHERE ISNULL(CustomerStatus, N'Active') <> N'Inactive'
                  AND (
                        UPPER(LTRIM(RTRIM(CustomerName))) = UPPER(LTRIM(RTRIM(:full_name)))
                     OR UPPER(LTRIM(RTRIM(ISNULL(Remarks, N'')))) LIKE UPPER(N'%' + :marker + N'%')
                     OR RIGHT(
                            UPPER(LTRIM(RTRIM(CustomerName))),
                            LEN(N' - ' + UPPER(LTRIM(RTRIM(:fps_code))))
                        ) = UPPER(N' - ' + LTRIM(RTRIM(:fps_code)))
                  )
                ORDER BY
                    CASE
                        WHEN UPPER(LTRIM(RTRIM(CustomerName))) = UPPER(LTRIM(RTRIM(:full_name))) THEN 0
                        WHEN UPPER(LTRIM(RTRIM(ISNULL(Remarks, N'')))) LIKE UPPER(N'%' + :marker + N'%') THEN 1
                        ELSE 2
                    END,
                    CustomerID ASC
                """
            ),
            {
                "full_name": customer_name,
                "marker": marker,
                "fps_code": code,
            },
        ).mappings().first()
        if not row:
            return None
        return {
            "customer_id": int(row["CustomerID"]),
            "customer_name": (row["CustomerName"] or "").strip(),
            "mobile_number": (row["MobileNumber"] or "").strip(),
            "created": False,
        }

    def ensure_fps_customer(self, fps_name: str, fps_code: str) -> dict:
        """
        On Work Done: create Customer Master as ``{FPS Name} - {FPS Code}``.
        Same name+code never creates a second row (Ration Card Followup only).
        """
        customer_name = self.build_fps_customer_name(fps_name, fps_code)
        existing = self.find_fps_customer(fps_name, fps_code)
        if existing:
            return existing

        customer_repo = CustomerRepository()
        customer_repo.ensure_schema()
        code = (fps_code or "").strip()
        remarks = f"RCF|FPS:{code}"

        def _write() -> dict:
            saved = customer_repo.save_full(
                {
                    "customer_group": "ITR",
                    "customer_type": "Other",
                    "customer_name": customer_name,
                    "pan_number": CustomerRepository.PLACEHOLDER_PAN,
                    "customer_status": "Active",
                    "remarks": remarks,
                }
            )
            return {
                "customer_id": int(saved.get("customer_id") or 0),
                "customer_name": (saved.get("customer_name") or customer_name).strip(),
                "mobile_number": (saved.get("mobile_number") or "").strip(),
                "created": True,
            }

        try:
            created = persist(_write)
        except IntegrityError:
            again = self.find_fps_customer(fps_name, fps_code)
            if again:
                return again
            raise ValueError("Customer already exists for this FPS (duplicate).") from None
        if not created.get("customer_id"):
            raise ValueError("Customer could not be created in Customer Master.")
        return created

    def _entry_dict(self, row) -> dict:
        return {
            "entry_id": row.EntryID,
            "bill_no": row.BillNo,
            "work_date": row.WorkDate.isoformat() if row.WorkDate else "",
            "amount": str(row.Amount),
            "fps_row_id": row.FpsRowID,
            "fps_code": row.FpsCode or "",
            "fps_name": row.FpsName or "",
            "dealer_name": row.DealerName or "",
            "display_name": (row.DealerName or row.FpsName or row.FpsCode or "").strip(),
            "state_name": row.StateName or "",
            "district_name": row.DistrictName or "",
            "dso_name": row.DsoName or "",
            "aro_name": row.AroName or "",
            "work_done": bool(row.WorkDone),
            "tally_bill_generated": bool(row.TallyBillGenerated),
            "payment_received": bool(row.PaymentReceived),
            "tally_bill_no": row.TallyBillNo or "",
            "tally_bill_date": row.TallyBillDate.isoformat() if row.TallyBillDate else "",
            "tally_bill_amount": str(row.TallyBillAmount) if row.TallyBillAmount is not None else "",
            "remarks": row.Remarks or "",
            "created_date": row.CreatedDate.isoformat() if row.CreatedDate else "",
        }

    def list_entries(self) -> list[dict]:
        self.entry_repo.ensure_schema()
        return [self._entry_dict(row) for row in self.entry_repo.list_recent()]

    def get_entry(self, entry_id: int) -> dict:
        self.entry_repo.ensure_schema()
        row = self.entry_repo.get_by_id(entry_id)
        if row is None or not row.IsActive:
            raise ValueError("Ration Card Followup record not found.")
        data = self._entry_dict(row)
        daily = self._find_daily_for_bill(row.BillNo)
        if daily:
            data["daily_transaction_id"] = daily.TransactionID
            data["payments"] = self._load_payment_lines(daily)
        else:
            data["daily_transaction_id"] = None
            data["payments"] = []
        if not data.get("payment_received") and data.get("payments"):
            data["payment_received"] = True
        return data

    def save_entry(self, form: dict, *, created_by: str) -> RationCardFollowupSaveResult:
        self.entry_repo.ensure_schema()
        entry_id = self._entry_id_from_form(form)
        is_update = entry_id is not None

        work_date = self._date(form.get("WorkDate") or form.get("work_date"))
        if not work_date:
            raise ValueError("Work date is required.")

        amount = self._decimal(form.get("Amount") or form.get("amount") or "0")
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")

        fps = self._resolve_fps(form)
        fps_label = fps["display_name"]

        work_done = self._bool_from_form(form, "WorkDone", "work_done")
        tally_bill = self._bool_from_form(form, "TallyBillGenerated", "tally_bill_generated")
        payment_received = self._bool_from_form(form, "PaymentReceived", "payment_received")
        if tally_bill and not work_done:
            raise ValueError("Work Done must be checked before Tally Bill Generated.")
        if payment_received and not tally_bill:
            raise ValueError("Tally Bill Generated must be checked before Payment Received.")

        fps_customer = None
        if work_done:
            fps_customer = self.ensure_fps_customer(
                fps.get("dealer_name") or fps.get("fps_name") or fps_label,
                fps.get("fps_code") or "",
            )
        tally_bill_no = normalize_tally_bill_key(
            form.get("TallyBillNo") or form.get("tally_bill_no") or ""
        ) or None
        tally_bill_date = self._date(form.get("TallyBillDate") or form.get("tally_bill_date"))
        tally_bill_amount_raw = form.get("TallyBillAmount") or form.get("tally_bill_amount") or ""
        tally_bill_amount = None
        if str(tally_bill_amount_raw).strip():
            tally_bill_amount = self._decimal(tally_bill_amount_raw)

        if tally_bill:
            if not tally_bill_no:
                raise ValueError("Tally bill number is required when Tally Bill Generated is checked.")
            # Date / Amount removed from UI — Sales module will own billing later.
            tally_bill_date = None
            tally_bill_amount = None
        else:
            tally_bill_no = None
            tally_bill_date = None
            tally_bill_amount = None

        payments_active = payment_received
        extra_payment_lines = self._form_payment_line_count(form) > 1
        has_positive_payment = self._form_has_positive_payment_amount(form)
        require_payments = payment_received or has_positive_payment or extra_payment_lines
        if not payments_active:
            payment_lines = []
        else:
            payment_lines = self._parse_payment_lines(form, amount, required=require_payments)
            if require_payments and not payment_lines:
                raise ValueError("At least one payment mode is required when Payment Received is checked.")
        if payment_lines and not payment_received:
            payment_received = True
        if payment_received and not tally_bill:
            raise ValueError("Tally Bill Generated must be checked before Payment Received.")

        received_total = sum((line["amount"] for line in payment_lines), Decimal("0"))
        if require_payments and received_total <= 0:
            raise ValueError("Payment amount must be greater than zero.")

        remarks = (form.get("Remarks") or form.get("remarks") or "").strip() or None

        existing_row = None
        if is_update:
            existing_row = self.entry_repo.get_by_id(entry_id)
            if existing_row is None or not existing_row.IsActive:
                raise ValueError("Ration Card Followup record not found.")

        bill_raw = (form.get("BillNo") or form.get("bill_no") or "").strip()
        if is_update and existing_row:
            bill_no = self._validate_bill_no(bill_raw, exclude_id=entry_id) if bill_raw else existing_row.BillNo
        else:
            bill_no = self._allocate_bill_no(work_date, bill_raw)

        def _write() -> RationCardFollowupSaveResult:
            payload = {
                "BillNo": bill_no,
                "WorkDate": work_date,
                "Amount": amount,
                "FpsRowID": fps["fps_row_id"],
                "FpsCode": fps["fps_code"] or None,
                "FpsName": fps["fps_name"] or None,
                "DealerName": fps["dealer_name"] or None,
                "StateName": fps["state_name"] or None,
                "DistrictName": fps["district_name"] or None,
                "DsoName": fps["dso_name"] or None,
                "AroName": fps["aro_name"] or None,
                "WorkDone": work_done,
                "TallyBillGenerated": tally_bill,
                "PaymentReceived": payment_received,
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

            daily = None
            bank_ids: list[int] = []
            if payment_lines:
                daily, bank_ids = self._repost_transactions(
                    bill_no=row.BillNo,
                    work_date=work_date,
                    fps_label=fps_label,
                    entry_amount=amount,
                    payment_lines=payment_lines,
                    customer_name=fps_label,
                    remarks=remarks,
                    created_by=created_by,
                    existing_daily=existing_daily,
                )
            elif existing_daily is not None:
                self._remove_daily_transaction(existing_daily)

            if daily is not None:
                message = (
                    f"{action.capitalize()} bill {row.BillNo} ({amount}). "
                    f"Payment received {received_total}. Daily Transaction #{daily.TransactionID}."
                )
            elif tally_bill:
                message = (
                    f"{action.capitalize()} bill {row.BillNo} ({amount}). "
                    "Tally bill generated — payment pending."
                )
            elif work_done:
                message = f"{action.capitalize()} bill {row.BillNo} ({amount}). Work done."
            else:
                message = f"{action.capitalize()} bill {row.BillNo} ({amount})."

            return RationCardFollowupSaveResult(
                entry_id=row.EntryID,
                bill_no=row.BillNo,
                daily_transaction_id=daily.TransactionID if daily is not None else None,
                bank_transaction_ids=bank_ids,
                message=message,
            )

        try:
            return persist(_write)
        except IntegrityError as exc:
            if "BillNo" in str(getattr(exc, "orig", None) or exc):
                raise ValueError(f"Bill number {bill_no} already exists.") from exc
            raise

    def delete_entry(self, entry_id: int) -> str:
        self.entry_repo.ensure_schema()
        row = self.entry_repo.get_by_id(entry_id)
        if row is None or not row.IsActive:
            raise ValueError("Ration Card Followup record not found.")
        bill_no = row.BillNo

        def _write() -> None:
            self._remove_linked_transactions(bill_no)
            self.entry_repo.deactivate(row)

        persist(_write)
        return f"Deleted bill {bill_no}."
