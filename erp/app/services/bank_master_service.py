from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db

from app.repositories.bank_master_repository import BankMasterRepository
from app.services.account_type_master_service import AccountTypeMasterService
from app.utils.db_session import persist
from app.utils.opening_balance import default_dr_cr_for_under_type, parse_opening_balance_fields
from app.utils.master_delete_guard import (
    assert_master_unused,
    raise_if_integrity_in_use,
)
from app.utils.master_ledger_delete import ledger_payload, raise_if_ledger_in_use
from app.utils.bank_account_flags import form_flag

# Fallback labels only if AccountTypeMaster is empty (should be rare).
BANK_ACCOUNT_TYPES = (
    "CA-Current Asset",
    "CA-Current Account",
    "LN-Loan Account",
    "DA-Demat Account",
)
ACCOUNT_TYPES = BANK_ACCOUNT_TYPES


def account_type_needs_upi(account_type: str | None) -> bool:
    """UPI ID is optional on every Bank Master account type."""
    return True


class BankMasterService:
    DEFAULT_BANK_GROUP_NAME = "Bank Accounts"
    DEFAULT_CASH_GROUP_NAME = "Cash-in-Hand"

    def __init__(self, repository: BankMasterRepository | None = None):
        self.repo = repository or BankMasterRepository()
        # Kept only so Account Type Master schema/seed is not broken for its own page.
        self.account_types = AccountTypeMasterService()

    def list_chart_groups_for_form(self) -> list[dict]:
        """Active Chart of Group Master rows for Under Group dropdown (read-only)."""
        try:
            from app.services.chart_group_service import ChartGroupService

            return ChartGroupService().list_active_for_dropdown()
        except Exception:
            return []

    def _group_id_by_name(self, group_name: str) -> int | None:
        needle = (group_name or "").strip().casefold()
        if not needle:
            return None
        for item in self.list_chart_groups_for_form():
            name = (item.get("group_name") or "").strip().casefold()
            if name == needle:
                try:
                    return int(item["group_id"])
                except (TypeError, ValueError, KeyError):
                    return None
        return None

    def _default_chart_group_id(self, *, is_cash: bool) -> int | None:
        name = self.DEFAULT_CASH_GROUP_NAME if is_cash else self.DEFAULT_BANK_GROUP_NAME
        return self._group_id_by_name(name)

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

    @staticmethod
    def _int_or_default(value, default: int = 100) -> int:
        if value in (None, ""):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _is_cash_account(bank_name: str | None, account_number: str | None) -> bool:
        return (bank_name or "").strip().lower() == "cash" or (account_number or "").strip().lower() == "cash"

    @staticmethod
    def _flag_from_form(form: dict, *keys: str) -> bool:
        return form_flag(form, *keys)

    def _parse_form(self, form: dict, *, existing=None) -> dict:
        self.account_types.repo.ensure_schema()
        allowed = self.list_account_types_for_form()
        allowed_by_key = {
            (item.get("code") or "").strip().casefold(): (item.get("code") or "").strip()
            for item in allowed
            if (item.get("code") or "").strip()
        }
        default_type = (
            (allowed[0].get("code") if allowed else None)
            or BANK_ACCOUNT_TYPES[0]
        )
        raw_type = self._clean(form.get("AccountType"), 20) or default_type
        account_type = allowed_by_key.get(raw_type.casefold(), raw_type)
        existing_type = (existing.AccountType or "").strip() if existing is not None else ""
        # Must exist in AccountTypeMaster (active); legacy value OK if unchanged on edit.
        if (
            account_type.casefold() not in allowed_by_key
            and account_type != existing_type
        ):
            raise ValueError(
                "Account Type is invalid. Add it in Masters → Account Type Master first."
            )
        # Prefer canonical code from master when matched.
        if account_type.casefold() in allowed_by_key:
            account_type = allowed_by_key[account_type.casefold()]

        bank_name = self._clean(form.get("BankName"), 150)
        if not bank_name:
            raise ValueError("Bank Name is required.")

        account_number = self._clean(form.get("AccountNumber"), 50)
        if not account_number:
            raise ValueError("Account Number is required.")

        if "ActiveStatus" in form or "active_status" in form:
            active = BankMasterService._flag_from_form(form, "ActiveStatus", "active_status")
        else:
            active = False

        qr_bill_received = BankMasterService._flag_from_form(
            form, "QrBillReceived", "qr_bill_received"
        )
        account_payment_received = BankMasterService._flag_from_form(
            form, "AccountPaymentReceived", "account_payment_received"
        )

        is_cash = self._is_cash_account(bank_name, account_number)
        if existing is not None and self._is_cash_account(existing.BankName, existing.AccountNumber):
            is_cash = True

        if is_cash:
            display_order = 1
        else:
            display_order = self._int_or_default(form.get("DisplayOrder"), 100)
            if display_order < 2:
                display_order = 2

        upi_id = self._clean(form.get("UpiId") or form.get("upi_id"), 100)

        chart_group_id = self._int_or_default(
            form.get("ChartGroupID") or form.get("chart_group_id") or form.get("under_group_id"),
            0,
        )
        if not chart_group_id:
            chart_group_id = self._default_chart_group_id(is_cash=is_cash) or 0
        if not chart_group_id:
            raise ValueError("Under Group is required.")
        allowed_groups = {
            int(g["group_id"]): g for g in self.list_chart_groups_for_form() if g.get("group_id") is not None
        }
        if chart_group_id not in allowed_groups:
            raise ValueError("Under Group is invalid. Select a group from Chart of Group Master.")

        ob_fields = parse_opening_balance_fields(form)
        if not ob_fields.get("OpeningBalanceDrCr"):
            under = (allowed_groups.get(chart_group_id) or {}).get("under_type") or ""
            ob_fields["OpeningBalanceDrCr"] = default_dr_cr_for_under_type(under)

        return {
            "BankName": bank_name,
            "AccountNumber": account_number,
            "MaskedAccountNumber": self._clean(form.get("MaskedAccountNumber"), 50),
            "IFSCCode": self._clean(form.get("IFSCCode"), 20),
            "BranchName": self._clean(form.get("BranchName"), 150),
            "AccountHolderName": self._clean(form.get("AccountHolderName"), 150),
            "AccountType": account_type,
            "Description": self._clean(form.get("Description"), 500),
            "ActiveStatus": active,
            "QrBillReceived": qr_bill_received,
            "AccountPaymentReceived": account_payment_received,
            "OpeningBalance": ob_fields["OpeningBalance"],
            "OpeningBalanceDate": ob_fields["OpeningBalanceDate"],
            "OpeningBalanceDrCr": ob_fields["OpeningBalanceDrCr"],
            "DisplayOrder": display_order,
            "UpiId": upi_id,
            "ChartGroupID": chart_group_id,
        }

    def _serialize(self, row) -> dict:
        is_cash = BankMasterService._is_cash_account(row.BankName, row.AccountNumber)
        account_type = row.AccountType or BANK_ACCOUNT_TYPES[0]
        chart_group_id = getattr(row, "ChartGroupID", None)
        if chart_group_id is None:
            chart_group_id = self._default_chart_group_id(is_cash=is_cash)
        group_name = ""
        under_type = ""
        if chart_group_id:
            for item in self.list_chart_groups_for_form():
                if int(item.get("group_id") or 0) == int(chart_group_id):
                    group_name = item.get("group_name") or ""
                    under_type = item.get("under_type") or ""
                    break
        return {
            "account_id": row.JtcsBankAccountID,
            "bank_name": row.BankName or "",
            "account_number": row.AccountNumber or "",
            "masked_account_number": row.MaskedAccountNumber or "",
            "ifsc_code": row.IFSCCode or "",
            "branch_name": row.BranchName or "",
            "account_holder_name": row.AccountHolderName or "",
            "account_type": account_type,
            "upi_id": getattr(row, "UpiId", None) or "",
            "needs_upi": account_type_needs_upi(account_type),
            "description": row.Description or "",
            "active_status": bool(row.ActiveStatus),
            "qr_bill_received": bool(getattr(row, "QrBillReceived", False)),
            "account_payment_received": bool(getattr(row, "AccountPaymentReceived", False)),
            "opening_balance": str(row.OpeningBalance) if row.OpeningBalance is not None else "",
            "opening_balance_date": row.OpeningBalanceDate.isoformat()
            if row.OpeningBalanceDate
            else "",
            "opening_balance_dr_cr": getattr(row, "OpeningBalanceDrCr", None)
            or default_dr_cr_for_under_type(under_type),
            "display_order": int(
                getattr(row, "DisplayOrder", 1 if is_cash else 100) or (1 if is_cash else 100)
            ),
            "chart_group_id": int(chart_group_id) if chart_group_id else None,
            "under_group": group_name,
            "under_type": under_type,
            "is_cash": is_cash,
            "created_date": row.CreatedDate.isoformat() if isinstance(row.CreatedDate, datetime) else "",
            "modified_date": row.ModifiedDate.isoformat() if isinstance(row.ModifiedDate, datetime) else "",
        }

    def list_payment_accounts(self) -> list[dict]:
        """Active bank accounts for sale invoice Payment Bank (QR/Bill Received only).

        Cash is excluded (invoice QR). Accounts without QR/Bill Received stay off this list.
        UPI ID is optional — invoice PDF shows a fallback when it is blank.
        """
        self.repo.ensure_schema()
        rows = []
        for row in self.repo.list_all():
            if not row.ActiveStatus:
                continue
            if self._is_cash_account(row.BankName, row.AccountNumber):
                continue
            data = self._serialize(row)
            if not data.get("qr_bill_received"):
                continue
            data["label"] = (
                f"{data['bank_name']} · {data['account_number']}"
                + (f" [{data['account_type']}]" if data["account_type"] else "")
            )
            rows.append(data)
        rows.sort(
            key=lambda r: (
                int(r.get("display_order") or 100),
                (r.get("label") or "").lower(),
            )
        )
        return rows

    def list_accounts_for_purchase_payment(self) -> list[dict]:
        """Active bank + cash accounts for purchase payment (UPI optional)."""
        self.repo.ensure_schema()
        rows = []
        for row in self.repo.list_all():
            if not row.ActiveStatus:
                continue
            data = self._serialize(row)
            data["label"] = (
                f"{data['bank_name']} · {data['account_number']}"
                + (f" [{data['account_type']}]" if data["account_type"] else "")
            )
            rows.append(data)
        rows.sort(key=lambda r: (0 if r.get("is_cash") else 1, (r.get("label") or "").lower()))
        return rows

    def list_account_types_for_form(self) -> list[dict]:
        """Active account types from AccountTypeMaster for Bank Master dropdown."""
        self.account_types.repo.ensure_schema()
        rows = self.account_types.list_active_for_dropdown()
        if rows:
            return rows
        return [
            {"code": code, "name": code, "label": code}
            for code in BANK_ACCOUNT_TYPES
        ]

    def list_records(self, *, search: str | None = None) -> list[dict]:
        self.repo.ensure_schema()
        self.account_types.repo.ensure_schema()
        return [self._serialize(row) for row in self.repo.list_all(search=search)]

    def get_record(self, account_id: int) -> dict:
        self.repo.ensure_schema()
        row = self.repo.get_by_id(account_id)
        if row is None:
            raise ValueError("Bank account not found.")
        return self._serialize(row)

    def create_record(self, form: dict) -> dict:
        data = self._parse_form(form)

        def _write() -> dict:
            self.repo.ensure_schema()
            row = self.repo.create(data)
            return self._serialize(row)

        return persist(_write)

    def update_record(self, account_id: int, form: dict) -> dict:
        def _write() -> dict:
            self.repo.ensure_schema()
            row = self.repo.get_by_id(account_id)
            if row is None:
                raise ValueError("Bank account not found.")
            data = self._parse_form(form, existing=row)
            row = self.repo.update(row, data)
            return self._serialize(row)

        return persist(_write)

    def _unlink_unused_payment_modes(self, account_id: int) -> None:
        """Payment Mode is not a ledger posting. Clear the bank link before delete."""
        try:
            with db.session.begin_nested():
                db.session.execute(
                    text(
                        """
                        UPDATE dbo.PaymentModeMaster
                        SET BankAccountID = NULL
                        WHERE BankAccountID = :id
                        """
                    ),
                    {"id": int(account_id)},
                )
        except SQLAlchemyError:
            return

    def _detach_inactive_bank_cash(self, account_id: int) -> None:
        """Soft-deleted Bank/Cash rows still hold FKs and would block delete."""
        try:
            with db.session.begin_nested():
                db.session.execute(
                    text(
                        """
                        UPDATE dbo.OthersBankCashTransaction
                        SET DebitBankAccountID = CASE
                                WHEN DebitBankAccountID = :id THEN NULL
                                ELSE DebitBankAccountID
                            END,
                            CreditBankAccountID = CASE
                                WHEN CreditBankAccountID = :id THEN NULL
                                ELSE CreditBankAccountID
                            END
                        WHERE ISNULL(IsActive, 1) = 0
                          AND (DebitBankAccountID = :id OR CreditBankAccountID = :id)
                        """
                    ),
                    {"id": int(account_id)},
                )
        except SQLAlchemyError:
            try:
                with db.session.begin_nested():
                    db.session.execute(
                        text(
                            """
                            DELETE FROM dbo.OthersBankCashTransaction
                            WHERE ISNULL(IsActive, 1) = 0
                              AND (DebitBankAccountID = :id OR CreditBankAccountID = :id)
                            """
                        ),
                        {"id": int(account_id)},
                    )
            except SQLAlchemyError:
                return

    def delete_record(self, account_id: int) -> str:
        def _write() -> str:
            self.repo.ensure_schema()
            row = self.repo.get_by_id(account_id)
            if row is None:
                raise ValueError("Bank account not found.")
            label = (row.BankName or "").strip() or "Bank account"
            ledger = ledger_payload("bank", account_id)
            raise_if_ledger_in_use("bank", account_id, label)
            self._unlink_unused_payment_modes(account_id)
            self._detach_inactive_bank_cash(account_id)
            assert_master_unused(
                table="JtcsBankAccountMaster",
                pk_column="JtcsBankAccountID",
                pk_value=account_id,
                display_name=label,
                column_aliases=[
                    "JtcsBankAccountID",
                    "BankAccountID",
                    "CreditBankAccountID",
                    "DebitBankAccountID",
                    "PaymentBankAccountID",
                ],
                extra_checks=[
                    {
                        "table": "OthersBankCashTransaction",
                        "where": (
                            "(CreditLedgerKey = :key OR DebitLedgerKey = :key) "
                            "AND ISNULL(IsActive, 1) = 1"
                        ),
                        "params": {"key": f"bank-{int(account_id)}"},
                        "label": "Bank / Cash Transaction",
                    },
                ],
                ledger=ledger,
            )
            try:
                self.repo.delete(row)
            except IntegrityError as exc:
                raise_if_integrity_in_use(exc, label, ledger=ledger)
                raise
            return "Bank account permanently deleted from the database."

        return persist(_write)
