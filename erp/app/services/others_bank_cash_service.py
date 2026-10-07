from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, select, text, update

from app.extensions import db
from app.models.auth import User
from app.models.transactions import JTCSDailyTransaction, JTCSDailyTransactionPayment
from app.repositories.bank_cash_repository import OthersBankCashRepository
from app.repositories.transaction_repository import (
    BankAccountSnapshot,
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


@dataclass
class LedgerRef:
    ledger_key: str
    source: str
    bank_account_id: int | None
    coa_account_id: int | None
    label: str
    group_name: str
    under_type: str
    snapshot: BankAccountSnapshot
    customer_id: int | None = None


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

    @staticmethod
    def _ledger_label(row: dict) -> str:
        name = (row.get("ledger_name") or "Account").strip()
        ref = (row.get("account_ref") or "").strip()
        account_type = (row.get("account_type") or "OTH").strip() or "OTH"
        parts = [name]
        if ref and ref.lower() not in {name.lower(), "na"}:
            parts.append(ref)
        parts.append(f"[{account_type}]")
        return " · ".join(parts)

    def list_accounts(self) -> dict:
        """Flat list + grouped by Chart of Group for Credit/Debit dropdowns."""
        flat: list[dict] = []
        groups_map: dict[tuple, dict] = {}
        for row in self.entry_repo.list_transfer_ledgers():
            label = self._ledger_label(row)
            item = {
                "ledger_key": row["ledger_key"],
                "account_id": row.get("bank_account_id"),
                "coa_account_id": row.get("coa_account_id"),
                "source": row["source"],
                "label": label,
                "bank_name": row.get("ledger_name") or "",
                "account_type": row.get("account_type") or "OTH",
                "group_id": row.get("group_id"),
                "group_name": row.get("group_name") or "Ungrouped",
                "under_type": row.get("under_type") or "Assets",
                "is_rd": bool(row.get("is_rd")),
                "is_cash": bool(row.get("is_cash")),
                "customer_id": int(row["customer_id"]) if row.get("customer_id") else None,
                "customer_name": (row.get("customer_name") or "").strip(),
            }
            flat.append(item)
            gkey = (
                int(row["group_id"]) if row.get("group_id") is not None else 0,
                item["under_type"],
                item["group_name"],
            )
            if gkey not in groups_map:
                groups_map[gkey] = {
                    "group_id": row.get("group_id"),
                    "group_name": item["group_name"],
                    "under_type": item["under_type"],
                    "label": f"{item['group_name']} ({item['under_type']})",
                    "accounts": [],
                }
            groups_map[gkey]["accounts"].append(item)

        groups = sorted(
            groups_map.values(),
            key=lambda g: (
                0 if g["under_type"] == "Assets" else 1,
                (g["group_name"] or "").lower(),
            ),
        )
        return {"rows": flat, "groups": groups}

    def search_accounts(
        self,
        term: str,
        *,
        limit: int = 30,
        include_customers: bool = False,
    ) -> list[dict]:
        """Credit/Debit autocomplete. Customer Master is included only for Credit."""
        items = []
        for row in self.entry_repo.search_transfer_ledgers(
            term,
            limit=limit,
            include_customers=include_customers,
        ):
            customer_id = int(row["customer_id"]) if row.get("customer_id") else None
            items.append(
                {
                    "ledger_key": row["ledger_key"],
                    "account_id": row.get("bank_account_id"),
                    "coa_account_id": row.get("coa_account_id"),
                    "source": row.get("source") or "",
                    "label": self._ledger_label(row),
                    "title": (row.get("ledger_name") or "Account").strip(),
                    "lines": self._account_search_lines(row),
                    "group_name": row.get("group_name") or "",
                    "customer_id": customer_id,
                    "customer_name": (row.get("customer_name") or "").strip(),
                }
            )
        return items

    @staticmethod
    def _account_search_lines(row: dict) -> list[str]:
        lines: list[str] = []
        source = (row.get("source") or "").strip()
        ledger_name = (row.get("ledger_name") or "").strip()
        account_ref = (row.get("account_ref") or "").strip()
        account_number = (row.get("account_number") or "").strip()
        if source == "bank":
            shown = account_ref or account_number
            if shown:
                lines.append(f"A/c: {shown}")
        elif account_ref:
            lines.append(account_ref)
        customer_name = (row.get("customer_name") or "").strip()
        if customer_name and customer_name.lower() != ledger_name.lower():
            lines.append(customer_name)
        mobile = (row.get("mobile") or "").strip()
        if mobile:
            lines.append(f"Mobile: {mobile}")
        pan = (row.get("pan") or "").strip()
        if pan:
            lines.append(f"PAN: {pan}")
        gstin = (row.get("gstin") or "").strip()
        if gstin:
            lines.append(f"GSTIN: {gstin}")
        ifsc = (row.get("ifsc") or "").strip()
        if ifsc:
            lines.append(f"IFSC: {ifsc}")
        return lines

    def list_account_rows(self) -> list[dict]:
        return self.list_accounts()["rows"]

    def _account_label(self, account_id: int | None) -> str:
        if not account_id:
            return ""
        account = self.master_repo.get_bank_account(account_id)
        if account is None:
            return f"#{account_id}"
        mask = account.MaskedAccountNumber or account.AccountNumber or ""
        account_type = account.AccountType or "OTH"
        return f"{account.BankName} · {mask} [{account_type}]".strip()

    def _ledger_key_for_row(self, row, *, side: str) -> str:
        if side == "credit":
            key = getattr(row, "CreditLedgerKey", None)
            bank_id = row.CreditBankAccountID
        else:
            key = getattr(row, "DebitLedgerKey", None)
            bank_id = row.DebitBankAccountID
        if key:
            return str(key).strip()
        if bank_id:
            return f"bank-{int(bank_id)}"
        return ""

    def _label_for_ledger_key(self, ledger_key: str) -> str:
        key = (ledger_key or "").strip()
        if not key:
            return ""
        for item in self.list_account_rows():
            if item["ledger_key"] == key:
                group = item.get("group_name") or ""
                if group and group != "Ungrouped":
                    return f"{item['label']} · {group}"
                return item["label"]
        if key.startswith("bank-"):
            try:
                return self._account_label(int(key.split("-", 1)[1]))
            except (TypeError, ValueError):
                return key
        if key.startswith("customer-"):
            try:
                cid = int(key.split("-", 1)[1])
            except (TypeError, ValueError):
                return key
            return self._customer_display_name(cid) or key
        if key.startswith("coa-"):
            try:
                aid = int(key.split("-", 1)[1])
            except (TypeError, ValueError):
                return key
            name = db.session.execute(
                text(
                    """
                    SELECT a.AccountName, g.GroupName
                    FROM dbo.ChartOfAccountMaster a
                    LEFT JOIN dbo.ChartOfGroupMaster g ON g.GroupID = a.GroupID
                    WHERE a.AccountID = :aid
                    """
                ),
                {"aid": aid},
            ).mappings().first()
            if not name:
                return key
            label = (name.get("AccountName") or key).strip()
            group = (name.get("GroupName") or "").strip()
            return f"{label} · {group}" if group else label
        return key

    def _parse_ledger_ref(self, raw) -> LedgerRef:
        text_raw = str(raw or "").strip()
        if not text_raw:
            raise ValueError("Credit and Debit accounts are required.")

        ledger_key = text_raw
        if text_raw.isdigit():
            ledger_key = f"bank-{int(text_raw)}"

        if ledger_key.startswith("bank-"):
            try:
                bank_id = int(ledger_key.split("-", 1)[1])
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid bank account.") from exc
            snapshot = self.master_repo.resolve_bank_account_by_id(bank_id)
            account = self.master_repo.get_bank_account(bank_id)
            group_name = "Ungrouped"
            under_type = "Assets"
            if account is not None and getattr(account, "ChartGroupID", None):
                g = db.session.execute(
                    text(
                        """
                        SELECT GroupName, UnderType
                        FROM dbo.ChartOfGroupMaster
                        WHERE GroupID = :gid
                        """
                    ),
                    {"gid": int(account.ChartGroupID)},
                ).mappings().first()
                if g:
                    group_name = (g.get("GroupName") or group_name).strip()
                    under_type = (g.get("UnderType") or under_type).strip()
            label = self._account_label(bank_id)
            return LedgerRef(
                ledger_key=f"bank-{bank_id}",
                source="bank",
                bank_account_id=bank_id,
                coa_account_id=None,
                label=label,
                group_name=group_name,
                under_type=under_type,
                snapshot=snapshot,
            )

        if ledger_key.startswith("coa-"):
            try:
                coa_id = int(ledger_key.split("-", 1)[1])
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid chart account.") from exc
            row = db.session.execute(
                text(
                    """
                    SELECT a.AccountID, a.AccountName, a.IsActive,
                           g.GroupName, g.UnderType
                    FROM dbo.ChartOfAccountMaster a
                    INNER JOIN dbo.ChartOfGroupMaster g ON g.GroupID = a.GroupID
                    WHERE a.AccountID = :aid
                    """
                ),
                {"aid": coa_id},
            ).mappings().first()
            if row is None or not row.get("IsActive"):
                raise ValueError("Chart account not found or inactive.")
            under = (row.get("UnderType") or "").strip()
            if under not in {"Assets", "Liabilities"}:
                raise ValueError("Account group must be under Assets or Liabilities.")
            name = (row.get("AccountName") or f"Account #{coa_id}").strip()
            group_name = (row.get("GroupName") or "").strip()
            snapshot = BankAccountSnapshot(
                account_id=0,
                bank_name=name[:150],
                masked_account_number=(group_name or "COA")[:50],
            )
            return LedgerRef(
                ledger_key=f"coa-{coa_id}",
                source="coa",
                bank_account_id=None,
                coa_account_id=coa_id,
                label=f"{name} [{group_name}]" if group_name else name,
                group_name=group_name,
                under_type=under,
                snapshot=snapshot,
                customer_id=self._coa_customer_id(coa_id),
            )

        if ledger_key.startswith("customer-"):
            return self._customer_ledger_ref(ledger_key)

        raise ValueError("Credit and Debit accounts are required.")

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

    def _ledger_label_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for item in self.list_account_rows():
            group = item.get("group_name") or ""
            label = item["label"]
            if group and group != "Ungrouped":
                label = f"{label} · {group}"
            mapping[item["ledger_key"]] = label
        return mapping

    def list_entries(self) -> list[dict]:
        lookup = self._entered_by_lookup()
        labels = self._ledger_label_map()
        rows = []
        for row in self.entry_repo.list_active():
            credit_key = self._ledger_key_for_row(row, side="credit")
            debit_key = self._ledger_key_for_row(row, side="debit")
            rows.append(
                {
                    "entry_id": row.EntryID,
                    "voucher_no": row.VoucherNo,
                    "work_date": row.WorkDate.isoformat() if row.WorkDate else "",
                    "purpose": row.Purpose or "",
                    "credit_account_id": row.CreditBankAccountID,
                    "credit_ledger_key": credit_key,
                    "credit_account": labels.get(credit_key)
                    or self._label_for_ledger_key(credit_key)
                    or self._account_label(row.CreditBankAccountID),
                    "debit_account_id": row.DebitBankAccountID,
                    "debit_ledger_key": debit_key,
                    "debit_account": labels.get(debit_key)
                    or self._label_for_ledger_key(debit_key)
                    or self._account_label(row.DebitBankAccountID),
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
        self.entry_repo.ensure_schema()
        row = self.entry_repo.get_by_id(entry_id)
        if row is None or not row.IsActive:
            raise ValueError("Transaction not found.")
        credit_key = self._ledger_key_for_row(row, side="credit")
        debit_key = self._ledger_key_for_row(row, side="debit")
        allocations = self._entry_allocations(row)
        link_mode = (getattr(row, "InvoiceLinkMode", None) or "").strip().lower()
        if link_mode not in {"none", "all", "selected"}:
            link_mode = "selected" if allocations else "none"
        credit_customer_id = self._credit_ledger_customer_id(credit_key)
        return {
            "entry_id": row.EntryID,
            "voucher_no": row.VoucherNo,
            "work_date": row.WorkDate.isoformat() if row.WorkDate else "",
            "purpose": row.Purpose or "",
            "credit_account_id": row.CreditBankAccountID,
            "credit_ledger_key": credit_key,
            "credit_account": self._label_for_ledger_key(credit_key)
            or self._account_label(row.CreditBankAccountID),
            "credit_customer_id": credit_customer_id,
            "credit_customer_name": self._customer_display_name(credit_customer_id) or "",
            "debit_account_id": row.DebitBankAccountID,
            "debit_ledger_key": debit_key,
            "debit_account": self._label_for_ledger_key(debit_key)
            or self._account_label(row.DebitBankAccountID),
            "amount": float(row.Amount or 0),
            "remarks": row.Remarks or "",
            "invoice_id": getattr(row, "InvoiceID", None),
            "invoice_mode": link_mode,
            "customer_id": self._entry_customer_id(row),
            "customer_name": self._customer_display_name(self._entry_customer_id(row))
            or self._invoice_customer_name(
                allocations[0]["invoice_id"] if allocations else getattr(row, "InvoiceID", None)
            ),
            "allocations": allocations,
            "advance_allocated": float(self._advance_allocated_total(row)),
            "advance_allocations": self._advance_allocation_rows(row),
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

    @staticmethod
    def _optional_int(value) -> int | None:
        if value in (None, "", "0", 0):
            return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ValueError("Invalid invoice.") from None
        return number if number > 0 else None

    def _invoice_customer_id(self, invoice_id: int | None) -> int | None:
        if not invoice_id:
            return None
        from app.models.gst_billing import GstInvoice

        inv = db.session.get(GstInvoice, int(invoice_id))
        if inv is None or not getattr(inv, "CustomerID", None):
            return None
        return int(inv.CustomerID)

    def _invoice_customer_name(self, invoice_id: int | None) -> str | None:
        if not invoice_id:
            return None
        from app.models.gst_billing import GstInvoice

        inv = db.session.get(GstInvoice, int(invoice_id))
        if inv is None:
            return None
        return (getattr(inv, "CustomerName", None) or "").strip() or None

    def _customer_ledger_key(self, customer_id: int) -> str | None:
        row = db.session.execute(
            text(
                """
                SELECT TOP 1 AccountID
                FROM dbo.ChartOfAccountMaster
                WHERE CustomerID = :cid AND ISNULL(IsActive, 1) = 1
                ORDER BY AccountID
                """
            ),
            {"cid": int(customer_id)},
        ).first()
        if not row or row[0] is None:
            return None
        return f"coa-{int(row[0])}"

    def _customer_ledger_ref(self, ledger_key: str) -> LedgerRef:
        """Credit selection for a Customer Master row that has no chart ledger yet."""
        try:
            customer_id = int(str(ledger_key).split("-", 1)[1])
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid customer.") from exc
        if customer_id <= 0:
            raise ValueError("Invalid customer.")
        row = db.session.execute(
            text(
                """
                SELECT CustomerID, LTRIM(RTRIM(CustomerName)) AS CustomerName, CustomerStatus
                FROM dbo.CustomerMaster
                WHERE CustomerID = :cid
                """
            ),
            {"cid": customer_id},
        ).mappings().first()
        if row is None:
            raise ValueError("Customer not found.")
        status = (row.get("CustomerStatus") or "Active").strip()
        if status in {"Inactive", "Rejected"}:
            raise ValueError("Customer is not active.")
        existing_key = self._customer_ledger_key(customer_id)
        if existing_key:
            ref = self._parse_ledger_ref(existing_key)
            ref.customer_id = customer_id
            return ref
        name = (row.get("CustomerName") or f"Customer #{customer_id}").strip()
        return LedgerRef(
            ledger_key=f"customer-{customer_id}",
            source="customer",
            bank_account_id=None,
            coa_account_id=None,
            label=name,
            group_name="Customer",
            under_type="",
            snapshot=BankAccountSnapshot(
                account_id=0,
                bank_name=name[:150],
                masked_account_number="Customer",
            ),
            customer_id=customer_id,
        )

    def _credit_ledger_customer_id(self, ledger_key: str) -> int | None:
        key = (ledger_key or "").strip()
        if key.startswith("customer-"):
            try:
                customer_id = int(key.split("-", 1)[1])
            except (TypeError, ValueError):
                return None
            return customer_id if customer_id > 0 else None
        if not key.startswith("coa-"):
            return None
        try:
            account_id = int(key.split("-", 1)[1])
        except (TypeError, ValueError):
            return None
        return self._coa_customer_id(account_id)

    def _coa_customer_id(self, coa_account_id: int | None) -> int | None:
        """Customer Master id on a chart account. Bank and other ledgers have none."""
        if not coa_account_id:
            return None
        row = db.session.execute(
            text(
                """
                SELECT CustomerID
                FROM dbo.ChartOfAccountMaster
                WHERE AccountID = :aid
                  AND ISNULL(IsActive, 1) = 1
                """
            ),
            {"aid": int(coa_account_id)},
        ).first()
        if not row or not row[0]:
            return None
        return int(row[0])

    def _allocation_rows(self, entry_id: int):
        from app.models.bank_cash import OthersBankCashInvoiceAllocation

        return list(
            db.session.scalars(
                select(OthersBankCashInvoiceAllocation)
                .where(OthersBankCashInvoiceAllocation.EntryID == int(entry_id))
                .order_by(OthersBankCashInvoiceAllocation.AllocationID.asc())
            ).all()
        )

    @staticmethod
    def _money(amount) -> Decimal:
        return Decimal(str(amount or 0)).quantize(Decimal("0.01"))

    def _clear_allocations(self, entry_id: int) -> None:
        from app.models.bank_cash import OthersBankCashInvoiceAllocation

        db.session.execute(
            delete(OthersBankCashInvoiceAllocation).where(
                OthersBankCashInvoiceAllocation.EntryID == int(entry_id)
            )
        )
        db.session.flush()

    def _insert_allocation(self, entry_id: int, invoice_id: int, amount: Decimal, source: str) -> None:
        from app.models.bank_cash import OthersBankCashInvoiceAllocation

        value = self._money(amount)
        if value <= 0:
            return
        existing = db.session.scalars(
            select(OthersBankCashInvoiceAllocation).where(
                OthersBankCashInvoiceAllocation.EntryID == int(entry_id),
                OthersBankCashInvoiceAllocation.InvoiceID == int(invoice_id),
            )
        ).first()
        if existing is not None:
            existing.AllocatedAmount = self._money(existing.AllocatedAmount) + value
            return
        db.session.add(
            OthersBankCashInvoiceAllocation(
                EntryID=int(entry_id),
                InvoiceID=int(invoice_id),
                AllocatedAmount=value,
                AllocationSource=source,
            )
        )

    def _replace_allocations(self, entry_id: int, pairs: list[tuple[int, Decimal]], payment_amount: Decimal) -> None:
        """Rewrite this voucher's invoice links without posting any ledger rows.

        The payment is applied to the selected invoices first. Any advance already
        applied to a later invoice is kept only while the voucher still has room.
        """
        from app.models.gst_billing import GstInvoice

        advances = []
        for item in self._allocation_rows(entry_id):
            source = (getattr(item, "AllocationSource", None) or "receipt").strip().lower()
            if source == "advance" and self._money(item.AllocatedAmount) > 0:
                advances.append((int(item.InvoiceID), self._money(item.AllocatedAmount)))
        self._clear_allocations(entry_id)
        used = Decimal("0.00")
        receipt_ids: set[int] = set()
        for invoice_id, allocated in pairs:
            amount = self._money(allocated)
            if amount <= 0:
                continue
            self._insert_allocation(entry_id, invoice_id, amount, "receipt")
            used += amount
            receipt_ids.add(int(invoice_id))
        capacity = self._money(payment_amount) - used
        pending = [(invoice_id, amount) for invoice_id, amount in advances if invoice_id not in receipt_ids]
        if pending and capacity > 0:
            invoices = {
                int(inv.InvoiceID): inv
                for inv in db.session.scalars(
                    select(GstInvoice).where(GstInvoice.InvoiceID.in_([invoice_id for invoice_id, _amount in pending]))
                ).all()
            }
            pending.sort(
                key=lambda item: (
                    invoices[item[0]].InvoiceDate if item[0] in invoices and invoices[item[0]].InvoiceDate else date.min,
                    item[0],
                )
            )
            for invoice_id, amount in pending:
                if capacity <= 0 or invoice_id not in invoices:
                    continue
                take = amount if amount <= capacity else capacity
                take = self._money(take)
                if take <= 0:
                    continue
                self._insert_allocation(entry_id, invoice_id, take, "advance")
                capacity -= take
        db.session.flush()

    def _customer_display_name(self, customer_id: int | None) -> str | None:
        if not customer_id:
            return None
        from app.models.transactions import CustomerMaster

        row = db.session.get(CustomerMaster, int(customer_id))
        if row is None:
            return None
        return (row.CustomerName or "").strip() or None

    def _customer_receipt_entries(self, customer_id: int):
        from app.models.bank_cash import OthersBankCashInvoiceAllocation, OthersBankCashTransaction
        from app.models.gst_billing import GstInvoice

        entries = {
            int(row.EntryID): row
            for row in db.session.scalars(
                select(OthersBankCashTransaction).where(
                    OthersBankCashTransaction.IsActive == True,  # noqa: E712
                    OthersBankCashTransaction.CustomerID == int(customer_id),
                )
            ).all()
        }
        linked_ids = {
            int(entry_id)
            for entry_id in db.session.scalars(
                select(OthersBankCashInvoiceAllocation.EntryID)
                .join(GstInvoice, GstInvoice.InvoiceID == OthersBankCashInvoiceAllocation.InvoiceID)
                .where(GstInvoice.CustomerID == int(customer_id))
            ).all()
            if entry_id
        }
        missing = [entry_id for entry_id in linked_ids if entry_id not in entries]
        if missing:
            for row in db.session.scalars(
                select(OthersBankCashTransaction).where(
                    OthersBankCashTransaction.EntryID.in_(missing),
                    OthersBankCashTransaction.IsActive == True,  # noqa: E712
                )
            ).all():
                entries[int(row.EntryID)] = row
        return sorted(entries.values(), key=lambda row: (row.WorkDate, row.EntryID))

    def _entry_allocated_total(self, entry_id: int) -> Decimal:
        total = Decimal("0.00")
        for item in self._allocation_rows(entry_id):
            total += self._money(item.AllocatedAmount)
        return self._money(total)

    def _customer_opening_receivable(self, customer_id: int) -> Decimal:
        """Customer Master opening balance, using the ledger Dr/Cr sign.

        A debit opening is amount the customer already owed and is added to
        sales. A credit opening reduces that amount. Invoice rows do not
        contain this balance, so it is applied once.
        """
        if customer_id <= 0:
            return Decimal("0.00")
        try:
            has_ob = bool(
                db.session.execute(
                    text(
                        "SELECT CASE WHEN COL_LENGTH(N'dbo.CustomerMaster', N'OpeningBalance') "
                        "IS NULL THEN 0 ELSE 1 END"
                    )
                ).scalar()
            )
        except Exception:
            db.session.rollback()
            return Decimal("0.00")
        if not has_ob:
            return Decimal("0.00")
        row = db.session.execute(
            text(
                """
                SELECT
                    ISNULL(OpeningBalance, 0) AS OpeningBalance,
                    OpeningBalanceDate,
                    OpeningBalanceDrCr
                FROM dbo.CustomerMaster
                WHERE CustomerID = :cid
                """
            ),
            {"cid": int(customer_id)},
        ).mappings().first()
        if not row:
            return Decimal("0.00")
        amount = self._money(row["OpeningBalance"])
        if amount == 0:
            return Decimal("0.00")
        ob_date = row["OpeningBalanceDate"]
        if hasattr(ob_date, "date"):
            ob_date = ob_date.date()
        if ob_date is not None and ob_date > date.today():
            return Decimal("0.00")
        side = (row["OpeningBalanceDrCr"] or "Dr").strip().upper()
        if side.startswith("C"):
            return self._money(-amount)
        return amount

    def invoice_payment_adjustment(self, invoice_id: int) -> dict:
        """Read-only allocation summary for one sale invoice.

        Money In/Out amounts come from the voucher. Allocated amounts come
        from OthersBankCashInvoiceAllocation. This method does not post,
        edit, or delete any transaction.
        """
        from app.models.bank_cash import (
            OthersBankCashInvoiceAllocation,
            OthersBankCashTransaction,
        )
        from app.models.gst_billing import GstInvoice

        self.entry_repo.ensure_schema()
        try:
            invoice_key = int(invoice_id)
        except (TypeError, ValueError):
            invoice_key = 0
        inv = db.session.get(GstInvoice, invoice_key) if invoice_key > 0 else None
        if inv is None:
            raise ValueError("Invoice not found.")

        grouped: dict[int, dict] = {}
        alloc_rows = db.session.execute(
            select(OthersBankCashTransaction, OthersBankCashInvoiceAllocation.AllocatedAmount)
            .join(
                OthersBankCashInvoiceAllocation,
                OthersBankCashInvoiceAllocation.EntryID == OthersBankCashTransaction.EntryID,
            )
            .where(
                OthersBankCashInvoiceAllocation.InvoiceID == invoice_key,
                OthersBankCashTransaction.IsActive == True,  # noqa: E712
            )
            .order_by(
                OthersBankCashTransaction.WorkDate.asc(),
                OthersBankCashTransaction.EntryID.asc(),
            )
        ).all()
        for txn, allocated in alloc_rows:
            entry_id = int(txn.EntryID)
            bucket = grouped.get(entry_id)
            if bucket is None:
                bucket = {"txn": txn, "allocated": Decimal("0.00")}
                grouped[entry_id] = bucket
            bucket["allocated"] += self._money(allocated)

        legacy_rows = db.session.scalars(
            select(OthersBankCashTransaction).where(
                OthersBankCashTransaction.InvoiceID == invoice_key,
                OthersBankCashTransaction.IsActive == True,  # noqa: E712
            )
        ).all()
        legacy_ids = [int(row.EntryID) for row in legacy_rows if int(row.EntryID) not in grouped]
        allocated_elsewhere: set[int] = set()
        if legacy_ids:
            allocated_elsewhere = {
                int(entry_id)
                for entry_id in db.session.scalars(
                    select(OthersBankCashInvoiceAllocation.EntryID).where(
                        OthersBankCashInvoiceAllocation.EntryID.in_(legacy_ids)
                    )
                ).all()
                if entry_id
            }
        for txn in legacy_rows:
            entry_id = int(txn.EntryID)
            if entry_id in grouped or entry_id in allocated_elsewhere:
                continue
            grouped[entry_id] = {"txn": txn, "allocated": self._money(txn.Amount)}

        entries = []
        money_inout_amount = Decimal("0.00")
        allocated_amount = Decimal("0.00")
        ordered = sorted(
            grouped.values(),
            key=lambda item: (item["txn"].WorkDate, int(item["txn"].EntryID)),
        )
        for item in ordered:
            txn = item["txn"]
            txn_amount = self._money(txn.Amount)
            taken = self._money(item["allocated"])
            remaining = self._money(txn_amount - taken)
            money_inout_amount += txn_amount
            allocated_amount += taken
            entries.append(
                {
                    "money_inout_entry_id": int(txn.EntryID),
                    "voucher_no": txn.VoucherNo or "",
                    "work_date": txn.WorkDate.isoformat() if txn.WorkDate else "",
                    "money_inout_transaction_amount": float(txn_amount),
                    "allocated_amount": float(taken),
                    "remaining_money_inout_amount": float(remaining),
                }
            )
        money_inout_amount = self._money(money_inout_amount)
        allocated_amount = self._money(allocated_amount)
        remaining_amount = self._money(money_inout_amount - allocated_amount)

        customer_id = int(getattr(inv, "CustomerID", None) or 0)
        customer_total_sale = Decimal("0.00")
        customer_total_received = Decimal("0.00")
        if customer_id > 0:
            from sqlalchemy import func

            sale_total = db.session.scalar(
                select(func.coalesce(func.sum(GstInvoice.InvoiceValue), 0)).where(
                    GstInvoice.CustomerID == customer_id,
                    GstInvoice.VoucherType == "SALE",
                )
            )
            customer_total_sale = self._money(
                self._money(sale_total) + self._customer_opening_receivable(customer_id)
            )
            for receipt in self._customer_receipt_entries(customer_id):
                customer_total_received += self._money(receipt.Amount)
            customer_total_received = self._money(customer_total_received)
        customer_outstanding = self._money(customer_total_sale - customer_total_received)

        return {
            "invoice_id": invoice_key,
            "invoice_amount": float(self._money(inv.InvoiceValue)),
            "has_allocation": allocated_amount > 0,
            "allocated_amount": float(allocated_amount),
            "money_inout_entry_id": entries[0]["money_inout_entry_id"] if len(entries) == 1 else None,
            "money_inout_transaction_amount": float(money_inout_amount),
            "remaining_money_inout_amount": float(remaining_amount),
            "customer_id": customer_id or None,
            "customer_total_sale": float(customer_total_sale),
            "customer_total_received": float(customer_total_received),
            "customer_outstanding": float(customer_outstanding),
            "entries": entries,
        }

    def apply_unallocated_to_invoice(self, invoice) -> None:
        """Apply this customer's existing unallocated Money In balance to one new invoice.

        This only writes invoice allocation rows. It does not post a bank, cash,
        or customer ledger entry.
        """
        from app.services.gst_invoice_service import GstInvoiceService

        svc = GstInvoiceService()
        if svc.normalize_voucher_type(getattr(invoice, "VoucherType", None)) != svc.VOUCHER_SALE:
            return
        customer_id = int(getattr(invoice, "CustomerID", None) or 0)
        if customer_id <= 0 or not getattr(invoice, "InvoiceID", None):
            return
        room = self._money(svc.payment_position(invoice)["outstanding_amount"])
        if room <= 0:
            return
        for entry in self._customer_receipt_entries(customer_id):
            if room <= 0:
                break
            spare = self._money(entry.Amount) - self._entry_allocated_total(entry.EntryID)
            take = spare if spare <= room else room
            take = self._money(take)
            if take <= 0:
                continue
            self._insert_allocation(entry.EntryID, int(invoice.InvoiceID), take, "advance")
            room -= take
        db.session.flush()

    def release_invoice_allocations(self, invoice_id: int) -> None:
        """Drop virtual invoice links so the amount returns to the customer advance."""
        from app.models.bank_cash import OthersBankCashInvoiceAllocation

        try:
            invoice_key = int(invoice_id)
        except (TypeError, ValueError):
            return
        if invoice_key <= 0:
            return
        db.session.execute(
            delete(OthersBankCashInvoiceAllocation).where(
                OthersBankCashInvoiceAllocation.InvoiceID == invoice_key
            )
        )
        db.session.flush()

    def _entry_customer_id(self, row) -> int | None:
        stored = getattr(row, "CustomerID", None)
        if stored:
            return int(stored)
        allocations = self._allocation_rows(row.EntryID)
        if allocations:
            return self._invoice_customer_id(allocations[0].InvoiceID)
        return self._invoice_customer_id(getattr(row, "InvoiceID", None))

    def _advance_allocation_rows(self, row) -> list[dict]:
        rows = []
        for item in self._allocation_rows(row.EntryID):
            source = (getattr(item, "AllocationSource", None) or "receipt").strip().lower()
            amount = self._money(item.AllocatedAmount)
            if source == "advance" and amount > 0:
                rows.append(
                    {
                        "invoice_id": int(item.InvoiceID),
                        "allocated_amount": float(amount),
                    }
                )
        return rows

    def _advance_allocated_total(self, row) -> Decimal:
        return self._money(
            sum((Decimal(str(item["allocated_amount"])) for item in self._advance_allocation_rows(row)), Decimal("0.00"))
        )

    def _entry_allocations(self, row) -> list[dict]:
        stored = self._allocation_rows(row.EntryID)
        if stored:
            return [
                {
                    "invoice_id": int(item.InvoiceID),
                    "allocated_amount": float(item.AllocatedAmount or 0),
                }
                for item in stored
                if self._money(item.AllocatedAmount) > 0
                and (getattr(item, "AllocationSource", None) or "receipt").strip().lower() != "advance"
            ]
        invoice_id = getattr(row, "InvoiceID", None)
        if invoice_id:
            return [
                {
                    "invoice_id": int(invoice_id),
                    "allocated_amount": float(row.Amount or 0),
                }
            ]
        return []

    def _customer_sale_invoices(self, customer_id: int, *, entry_id: int | None = None) -> list[dict]:
        """Outstanding sale invoices for one customer, newest invoice date first.

        Editing a voucher puts its own allocation back into outstanding so the
        same invoices can be allocated again. Fully paid and non-sale invoices
        stay out of the list. Deleted invoices are already removed from GstInvoice.
        Display order is InvoiceDate DESC, InvoiceID DESC. Allocation still
        walks the same rows oldest-first.
        """
        from app.models.gst_billing import GstInvoice
        from app.services.gst_invoice_service import GstInvoiceService

        svc = GstInvoiceService()
        rows = list(
            db.session.scalars(
                select(GstInvoice)
                .where(
                    GstInvoice.CustomerID == int(customer_id),
                    GstInvoice.VoucherType == svc.VOUCHER_SALE,
                )
                .order_by(GstInvoice.InvoiceDate.desc(), GstInvoice.InvoiceID.desc())
            ).all()
        )
        invoices = []
        for inv in rows:
            position = svc.payment_position(inv, exclude_entry_id=entry_id)
            outstanding = Decimal(str(position["outstanding_amount"])).quantize(Decimal("0.01"))
            if outstanding <= 0:
                continue
            invoices.append(
                {
                    "invoice_id": int(inv.InvoiceID),
                    "invoice_no": inv.InvoiceNo or "",
                    "invoice_date": inv.InvoiceDate.isoformat() if inv.InvoiceDate else "",
                    "customer_name": (getattr(inv, "CustomerName", None) or "").strip() or None,
                    "contact_person": (getattr(inv, "ContactPerson", None) or "").strip(),
                    "outstanding": outstanding,
                    **position,
                }
            )
        return invoices

    def _form_invoice_ids(self, form) -> list[int]:
        raw_values = form.getlist("InvoiceIDs") if hasattr(form, "getlist") else []
        if not raw_values:
            single = form.get("InvoiceIDs") or form.get("InvoiceID")
            raw_values = [single] if single not in (None, "") else []
        ids: list[int] = []
        seen: set[int] = set()
        for raw in raw_values:
            number = self._optional_int(raw)
            if number and number not in seen:
                seen.add(number)
                ids.append(number)
        return ids

    def _plan_invoice_allocations(
        self,
        form,
        amount: Decimal,
        entry_id: int | None,
        *,
        credit_customer_id: int | None = None,
    ):
        """FIFO allocation across selected outstanding invoices. Does not post ledgers.

        A customer credit ledger is the party. The debit/receiving account is not.
        """
        mode = (form.get("InvoiceMode") or form.get("invoice_mode") or "none").strip().lower()
        if mode not in {"none", "all", "selected"}:
            mode = "none"
        if mode == "none":
            return "none", None, None, []

        customer_id = credit_customer_id or self._optional_int(
            form.get("CustomerID") or form.get("customer_id")
        )
        if not customer_id:
            raise ValueError("Select a customer before linking invoices.")
        eligible = self._customer_sale_invoices(customer_id, entry_id=entry_id)
        if mode == "all":
            targets = eligible
        else:
            wanted = set(self._form_invoice_ids(form))
            if not wanted:
                raise ValueError("Select at least one invoice.")
            known = {row["invoice_id"] for row in eligible}
            missing = wanted - known
            if missing:
                raise ValueError(
                    "One or more selected invoices are not outstanding for this customer."
                )
            targets = [row for row in eligible if row["invoice_id"] in wanted]
        if not targets:
            if mode == "all":
                return mode, customer_id, self._customer_display_name(customer_id), []
            raise ValueError("Select at least one outstanding invoice.")
        targets.sort(key=lambda row: ((row.get("invoice_date") or ""), int(row.get("invoice_id") or 0)))

        remaining = self._money(amount)
        pairs: list[tuple[int, Decimal]] = []
        for target in targets:
            if remaining <= Decimal("0.00"):
                break
            room = self._money(target["outstanding"])
            take = room if remaining >= room else remaining
            take = self._money(take)
            if take <= 0:
                continue
            pairs.append((target["invoice_id"], take))
            remaining = self._money(remaining - take)
        customer_name = next(
            (row["customer_name"] for row in targets if row.get("customer_name")),
            None,
        ) or self._customer_display_name(customer_id)
        return mode, customer_id, customer_name, pairs

    def customer_open_invoices(self, customer_id: int, entry_id: int | None = None) -> dict:
        """Outstanding sale invoices for a Money In customer, newest first."""
        try:
            cid = int(customer_id)
        except (TypeError, ValueError):
            cid = 0
        if cid <= 0:
            raise ValueError("Customer is required.")
        self.entry_repo.ensure_schema()
        invoices = []
        for row in self._customer_sale_invoices(cid, entry_id=entry_id):
            invoices.append(
                {
                    "invoice_id": row["invoice_id"],
                    "invoice_no": row["invoice_no"],
                    "invoice_date": row["invoice_date"],
                    "contact_person": row.get("contact_person") or "",
                    "invoice_amount": row["invoice_amount"],
                    "received_amount": row["received_amount"],
                    "outstanding_amount": row["outstanding_amount"],
                    "payment_status": row["payment_status"],
                }
            )
        return {
            "customer_id": cid,
            "customer_ledger_key": self._customer_ledger_key(cid),
            "invoices": invoices,
        }

    def save_entry(self, form: dict, *, created_by: str) -> BankCashSaveResult:
        self.entry_repo.ensure_schema()
        work_date = self._date(form.get("WorkDate"))
        purpose = self._clean(form.get("Purpose"), 200)
        if not purpose:
            raise ValueError("Purpose is required.")

        credit_raw = (
            form.get("CreditLedgerKey")
            or form.get("CreditBankAccountID")
            or form.get("credit_ledger_key")
        )
        debit_raw = (
            form.get("DebitLedgerKey")
            or form.get("DebitBankAccountID")
            or form.get("debit_ledger_key")
        )
        credit_ref = self._parse_ledger_ref(credit_raw)
        debit_ref = self._parse_ledger_ref(debit_raw)
        if debit_ref.source == "customer":
            raise ValueError("Select a bank or chart ledger for the Debit account.")
        if credit_ref.ledger_key == debit_ref.ledger_key:
            raise ValueError("Credit and Debit accounts must be different.")

        amount = self._decimal(form.get("Amount"))
        remarks = self._clean(form.get("Remarks"), 500)
        if purpose.casefold() == "other" and len(remarks or "") < 10:
            raise ValueError("If you select Other, the Remarks field is required.")
        entry_id_raw = form.get("EntryID") or form.get("entry_id")
        entry_id = None
        if entry_id_raw not in (None, ""):
            try:
                entry_id = int(entry_id_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid entry id.") from exc

        link_mode, linked_customer_id, linked_customer_name, allocation_pairs = (
            self._plan_invoice_allocations(
                form,
                amount,
                entry_id,
                credit_customer_id=(
                    credit_ref.customer_id
                    or self._coa_customer_id(credit_ref.coa_account_id)
                ),
            )
        )

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
                        "CustomerID": linked_customer_id,
                        "CustomerName": linked_customer_name,
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
                daily.CustomerID = linked_customer_id
                daily.CustomerName = linked_customer_name
                daily.TotalAmount = amount
                daily.Remarks = remarks
                daily.ModifiedDate = datetime.utcnow()

            out_row = self._create_bank_leg(
                bank_account=credit_ref.snapshot,
                txn_date=work_date,
                description=f"{purpose} (Credit / Out) · {voucher_no} · {debit_ref.label}"[:1000],
                money_in=Decimal("0"),
                money_out=amount,
                created_by=created_by,
                source_id=None,
                ledger_kind="CONTRA_OUT",
                remarks=(
                    f"[OBC] Voucher={voucher_no}|Leg=CREDIT|Ledger={credit_ref.ledger_key}"
                    f"|Purpose={purpose}|Counterparty={debit_ref.label}"
                )[:500],
                daily_id=daily.TransactionID,
            )
            in_row = self._create_bank_leg(
                bank_account=debit_ref.snapshot,
                txn_date=work_date,
                description=f"{purpose} (Debit / In) · {voucher_no} · {credit_ref.label}"[:1000],
                money_in=amount,
                money_out=Decimal("0"),
                created_by=created_by,
                source_id=out_row.JtcsBankTransactionID,
                ledger_kind="CONTRA_IN",
                remarks=(
                    f"[OBC] Voucher={voucher_no}|Leg=DEBIT|Ledger={debit_ref.ledger_key}"
                    f"|Purpose={purpose}|Counterparty={credit_ref.label}"
                )[:500],
                daily_id=daily.TransactionID,
            )

            daily.BankTransactionID = out_row.JtcsBankTransactionID
            payload = {
                "WorkDate": work_date,
                "Purpose": purpose,
                "CreditBankAccountID": credit_ref.bank_account_id,
                "DebitBankAccountID": debit_ref.bank_account_id,
                "CreditLedgerKey": credit_ref.ledger_key,
                "DebitLedgerKey": debit_ref.ledger_key,
                "Amount": amount,
                "Remarks": remarks,
                "OutBankTransactionID": out_row.JtcsBankTransactionID,
                "InBankTransactionID": in_row.JtcsBankTransactionID,
                "InvoiceID": None,
                "InvoiceLinkMode": link_mode,
                "CustomerID": linked_customer_id if link_mode != "none" else None,
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
            self._replace_allocations(entry.EntryID, allocation_pairs, amount)

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
        self.entry_repo.ensure_schema()

        def _write() -> str:
            entry = self.entry_repo.get_by_id(entry_id)
            if entry is None or not entry.IsActive:
                raise ValueError("Transaction not found.")

            daily = self._find_daily(entry.VoucherNo)
            self._remove_bank_legs(entry, daily)
            if daily is not None:
                self.daily_repo.delete(daily)

            self._clear_allocations(entry.EntryID)
            self.entry_repo.soft_delete(entry)
            return "Transaction deleted successfully."

        return persist(_write)
