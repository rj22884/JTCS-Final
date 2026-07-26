from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.repositories.bank_cash_repository import RdAccountRepository
from app.repositories.bank_master_repository import BankMasterRepository
from app.utils.db_session import persist


class RdAccountService:
    def __init__(
        self,
        repository: RdAccountRepository | None = None,
        bank_repo: BankMasterRepository | None = None,
    ):
        self.repo = repository or RdAccountRepository()
        self.bank_repo = bank_repo or BankMasterRepository()

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

    @staticmethod
    def _decimal_or_none(value) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _date_or_none(value) -> date | None:
        if value in (None, ""):
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    def _parse_form(self, form: dict) -> dict:
        rd_name = self._clean(form.get("RdName"), 150)
        if not rd_name:
            raise ValueError("RD Name is required.")

        rd_number = self._clean(form.get("RdNumber"), 50)
        if not rd_number:
            raise ValueError("RD Number is required.")

        if "ActiveStatus" in form or "active_status" in form:
            active_raw = (form.get("ActiveStatus") or form.get("active_status") or "").strip().lower()
            active = active_raw in {"1", "true", "on", "yes"}
        else:
            active = False

        return {
            "RdName": rd_name,
            "BankName": self._clean(form.get("BankName"), 150),
            "RdNumber": rd_number,
            "OpeningDate": self._date_or_none(form.get("OpeningDate")),
            "MaturityDate": self._date_or_none(form.get("MaturityDate")),
            "InterestRate": self._decimal_or_none(form.get("InterestRate")),
            "InstallmentAmount": self._decimal_or_none(form.get("InstallmentAmount")),
            "OpeningBalance": self._decimal_or_none(form.get("OpeningBalance")),
            "ActiveStatus": active,
            "Remarks": self._clean(form.get("Remarks"), 500),
        }

    @staticmethod
    def _mask_account(account_number: str) -> str:
        digits = "".join(ch for ch in account_number if ch.isalnum())
        if len(digits) <= 4:
            return digits or account_number
        return ("X" * (len(digits) - 4)) + digits[-4:]

    def _serialize(self, row) -> dict:
        return {
            "rd_account_id": row.RdAccountID,
            "rd_name": row.RdName or "",
            "bank_name": row.BankName or "",
            "rd_number": row.RdNumber or "",
            "bank_account_id": row.BankAccountID,
            "opening_date": row.OpeningDate.isoformat() if row.OpeningDate else "",
            "maturity_date": row.MaturityDate.isoformat() if row.MaturityDate else "",
            "interest_rate": str(row.InterestRate) if row.InterestRate is not None else "",
            "installment_amount": str(row.InstallmentAmount) if row.InstallmentAmount is not None else "",
            "opening_balance": str(row.OpeningBalance) if row.OpeningBalance is not None else "",
            "active_status": bool(row.ActiveStatus),
            "remarks": row.Remarks or "",
            "created_date": row.CreatedDate.isoformat() if isinstance(row.CreatedDate, datetime) else "",
            "modified_date": row.ModifiedDate.isoformat() if isinstance(row.ModifiedDate, datetime) else "",
        }

    def list_records(self, *, search: str | None = None) -> list[dict]:
        return [self._serialize(row) for row in self.repo.list_all(search=search)]

    def get_record(self, rd_account_id: int) -> dict:
        row = self.repo.get_by_id(rd_account_id)
        if row is None:
            raise ValueError("RD account not found.")
        return self._serialize(row)

    def create_record(self, form: dict, *, created_by: str = "System") -> dict:
        data = self._parse_form(form)

        def _write() -> dict:
            bank_name = data["BankName"] or data["RdName"]
            bank_row = self.bank_repo.create(
                {
                    "BankName": bank_name,
                    "AccountNumber": data["RdNumber"],
                    "MaskedAccountNumber": self._mask_account(data["RdNumber"]),
                    "AccountHolderName": data["RdName"],
                    "AccountType": "RD",
                    "Description": f"RD Account: {data['RdName']}",
                    "ActiveStatus": data["ActiveStatus"],
                    "OpeningBalance": data["OpeningBalance"],
                    "OpeningBalanceDate": data["OpeningDate"],
                }
            )
            row = self.repo.create(
                {
                    **data,
                    "BankAccountID": bank_row.JtcsBankAccountID,
                    "CreatedBy": created_by,
                }
            )
            return self._serialize(row)

        return persist(_write)

    def update_record(self, rd_account_id: int, form: dict) -> dict:
        data = self._parse_form(form)

        def _write() -> dict:
            row = self.repo.get_by_id(rd_account_id)
            if row is None:
                raise ValueError("RD account not found.")
            row = self.repo.update(row, data)
            if row.BankAccountID:
                bank = self.bank_repo.get_by_id(row.BankAccountID)
                if bank is not None:
                    self.bank_repo.update(
                        bank,
                        {
                            "BankName": data["BankName"] or data["RdName"],
                            "AccountNumber": data["RdNumber"],
                            "MaskedAccountNumber": self._mask_account(data["RdNumber"]),
                            "AccountHolderName": data["RdName"],
                            "AccountType": "RD",
                            "Description": f"RD Account: {data['RdName']}",
                            "ActiveStatus": data["ActiveStatus"],
                            "OpeningBalance": data["OpeningBalance"],
                            "OpeningBalanceDate": data["OpeningDate"],
                        },
                    )
            return self._serialize(row)

        return persist(_write)

    def delete_record(self, rd_account_id: int) -> str:
        def _write() -> str:
            row = self.repo.get_by_id(rd_account_id)
            if row is None:
                raise ValueError("RD account not found.")
            usage = self.repo.usage_count(row.BankAccountID)
            if usage > 0:
                self.repo.update(row, {"ActiveStatus": False})
                if row.BankAccountID:
                    bank = self.bank_repo.get_by_id(row.BankAccountID)
                    if bank is not None:
                        self.bank_repo.update(bank, {"ActiveStatus": False})
                return (
                    "RD account is used in transactions and was marked inactive "
                    "instead of deleted."
                )
            bank_id = row.BankAccountID
            self.repo.delete(row)
            if bank_id:
                bank = self.bank_repo.get_by_id(bank_id)
                if bank is not None:
                    self.bank_repo.delete(bank)
            return "RD account deleted successfully."

        return persist(_write)
