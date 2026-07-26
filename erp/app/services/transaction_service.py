from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text

from app.extensions import db
from app.repositories.transaction_repository import (
    BankTransactionRepository,
    DailyTransactionRepository,
    MasterRepository,
)


@dataclass
class TransactionResult:
    daily_transaction_id: int
    bank_transaction_id: int | None
    message: str


@dataclass
class ContraResult:
    contra_reference: str
    bank_transaction_ids: list[int]
    message: str


class TransactionService:
    """Synchronizes JTCSDailyTransaction with JtcsBankTransaction atomically."""

    WORK_TYPES = [
        "ITR",
        "GST",
        "TDS",
        "DSC",
        "SHCIL",
        "Accounting",
        "Payroll",
        "Employee",
        "Stock",
        "Other Income",
        "Expenses",
        "Court Fee",
        "Ticket",
        "Stamp",
        "Customer Service",
    ]

    def __init__(
        self,
        daily_repo: DailyTransactionRepository | None = None,
        bank_repo: BankTransactionRepository | None = None,
        master_repo: MasterRepository | None = None,
    ):
        self.daily_repo = daily_repo or DailyTransactionRepository()
        self.bank_repo = bank_repo or BankTransactionRepository()
        self.master_repo = master_repo or MasterRepository()

    def save_daily_transaction(self, payload: dict, created_by: str) -> TransactionResult:
        normalized = self._normalize_daily_payload(payload, created_by)
        money_in, money_out = self._resolve_money_movement(normalized)

        if money_in <= 0 and money_out <= 0:
            raise ValueError("Daily transaction must contain a money movement amount.")

        if not normalized.get("PaymentModeID"):
            raise ValueError("Payment mode is required for synchronized bank posting.")

        try:
            with db.session.begin_nested():
                daily = self.daily_repo.create(normalized)
                bank_account = self.master_repo.resolve_bank_account(int(normalized["PaymentModeID"]))
                bank_row = self._create_bank_row(
                    daily=daily,
                    bank_account=bank_account,
                    money_in=money_in,
                    money_out=money_out,
                    created_by=created_by,
                    ledger_kind="RECEIPT" if money_in > 0 else "PAYMENT",
                )
                self.daily_repo.update_bank_link(daily, bank_row.JtcsBankTransactionID)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return TransactionResult(
            daily_transaction_id=daily.TransactionID,
            bank_transaction_id=bank_row.JtcsBankTransactionID,
            message="Daily and bank transactions saved successfully.",
        )

    def save_contra(self, payload: dict, created_by: str) -> ContraResult:
        txn_date = self._as_date(payload.get("TransactionDate")) or date.today()
        amount = self._decimal(payload.get("Amount"))
        if amount <= 0:
            raise ValueError("Contra amount must be greater than zero.")

        from_mode_id = int(payload["FromPaymentModeID"])
        to_mode_id = int(payload["ToPaymentModeID"])
        if from_mode_id == to_mode_id:
            raise ValueError("Source and destination accounts must be different.")

        from_account = self.master_repo.resolve_bank_account(from_mode_id)
        to_account = self.master_repo.resolve_bank_account(to_mode_id)
        contra_ref = payload.get("ContraReference") or f"CONTRA-{uuid4().hex[:10].upper()}"
        description = (payload.get("Description") or "Cash/Bank contra transfer").strip()
        remarks = f"[JTCS-CONTRA] Ref={contra_ref}"

        try:
            with db.session.begin_nested():
                out_row = self._create_standalone_bank_row(
                    bank_account=from_account,
                    txn_date=txn_date,
                    description=f"{description} (Out)",
                    money_in=Decimal("0"),
                    money_out=amount,
                    created_by=created_by,
                    source_type="CONTRA",
                    source_id=None,
                    ledger_kind="CONTRA_OUT",
                    remarks=f"{remarks}|Leg=OUT",
                )
                in_row = self._create_standalone_bank_row(
                    bank_account=to_account,
                    txn_date=txn_date,
                    description=f"{description} (In)",
                    money_in=amount,
                    money_out=Decimal("0"),
                    created_by=created_by,
                    source_type="CONTRA",
                    source_id=out_row.JtcsBankTransactionID,
                    ledger_kind="CONTRA_IN",
                    remarks=f"{remarks}|Leg=IN",
                )
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return ContraResult(
            contra_reference=contra_ref,
            bank_transaction_ids=[out_row.JtcsBankTransactionID, in_row.JtcsBankTransactionID],
            message="Contra bank entries created successfully.",
        )

    def delete_daily_transaction(self, transaction_id: int) -> None:
        daily = self.daily_repo.get_by_id(transaction_id)
        if daily is None:
            raise ValueError("Daily transaction not found.")

        try:
            with db.session.begin_nested():
                bank_row = None
                if daily.BankTransactionID:
                    bank_row = self.bank_repo.get_by_id(daily.BankTransactionID)
                if bank_row is None:
                    bank_row = self.bank_repo.find_by_daily_id(transaction_id)
                if bank_row is not None:
                    self.bank_repo.delete(bank_row)
                self.daily_repo.delete(daily)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    def _create_bank_row(
        self,
        daily,
        bank_account,
        money_in: Decimal,
        money_out: Decimal,
        created_by: str,
        ledger_kind: str,
    ):
        return self._create_standalone_bank_row(
            bank_account=bank_account,
            txn_date=daily.TransactionDate,
            description=daily.Description or f"{daily.WorkType} / {daily.SubWorkType or ''}".strip(),
            money_in=money_in,
            money_out=money_out,
            created_by=created_by,
            source_type=daily.WorkType,
            source_id=daily.TransactionID,
            ledger_kind=ledger_kind,
            remarks=daily.Remarks,
            daily_id=daily.TransactionID,
        )

    def _create_standalone_bank_row(
        self,
        bank_account,
        txn_date: date,
        description: str,
        money_in: Decimal,
        money_out: Decimal,
        created_by: str,
        source_type: str,
        source_id: int | None,
        ledger_kind: str,
        remarks: str | None,
        daily_id: int | None = None,
    ):
        now = datetime.utcnow()
        debit = money_in if money_in > 0 else None
        credit = money_out if money_out > 0 else None

        return self.bank_repo.create(
            {
                "JtcsBankAccountID": bank_account.account_id or 0,
                "BankName": bank_account.bank_name,
                "MaskedAccountNumber": bank_account.masked_account_number,
                "TransactionDate": txn_date,
                "Description": description[:1000],
                "Debit": debit,
                "Credit": credit,
                "ClosingBalance": Decimal("0"),
                "ImportedBy": created_by,
                "ImportedDate": now,
                "Remarks": remarks,
                "IsLocked": False,
                "SourceTable": self.bank_repo.SOURCE_TABLE if daily_id else "CONTRA",
                "SourceRecordID": daily_id,
                "SourceType": source_type,
                "SourceID": source_id,
                "LedgerKind": ledger_kind,
            }
        )

    def _normalize_daily_payload(self, payload: dict, created_by: str) -> dict:
        customer_id = payload.get("CustomerID")
        customer_name = (payload.get("CustomerName") or "").strip() or None
        if customer_id:
            customer = self.master_repo.get_customer(int(customer_id))
            if customer:
                customer_name = customer.CustomerName

        income = self._decimal(payload.get("IncomeAmount"))
        expense = self._decimal(payload.get("ExpenseAmount"))
        sale = self._decimal(payload.get("SaleAmount"))
        purchase = self._decimal(payload.get("PurchaseAmount"))
        total = self._decimal(payload.get("TotalAmount"))
        if total <= 0:
            total = income + sale + expense + purchase

        return {
            "TransactionDate": self._as_date(payload.get("TransactionDate")) or date.today(),
            "WorkType": (payload.get("WorkType") or "").strip(),
            "SubWorkType": (payload.get("SubWorkType") or "").strip() or None,
            "CustomerID": int(customer_id) if customer_id else None,
            "CustomerName": customer_name,
            "ReferenceNo": (payload.get("ReferenceNo") or "").strip() or None,
            "Description": (payload.get("Description") or "").strip() or None,
            "IncomeAmount": income,
            "ExpenseAmount": expense,
            "SaleAmount": sale,
            "PurchaseAmount": purchase,
            "GSTAmount": self._decimal(payload.get("GSTAmount")),
            "TDSAmount": self._decimal(payload.get("TDSAmount")),
            "Quantity": self._decimal_or_none(payload.get("Quantity")),
            "Rate": self._decimal_or_none(payload.get("Rate")),
            "TotalAmount": total,
            "PaymentModeID": int(payload["PaymentModeID"]) if payload.get("PaymentModeID") else None,
            "Status": (payload.get("Status") or "Posted").strip(),
            "CreatedBy": created_by,
            "CreatedDate": datetime.utcnow(),
            "Remarks": (payload.get("Remarks") or "").strip() or None,
        }

    def _resolve_money_movement(self, data: dict) -> tuple[Decimal, Decimal]:
        money_in = data["IncomeAmount"] + data["SaleAmount"]
        money_out = data["ExpenseAmount"] + data["PurchaseAmount"]

        if money_in > 0 and money_out > 0:
            raise ValueError("A daily transaction cannot contain both receipt and payment amounts.")

        if money_in <= 0 and money_out <= 0 and data["TotalAmount"] > 0:
            txn_kind = (data.get("WorkType") or "").lower()
            if txn_kind in {"expenses", "expense", "purchase", "salary"}:
                money_out = data["TotalAmount"]
            else:
                money_in = data["TotalAmount"]

        return money_in, money_out

    @staticmethod
    def _decimal(value) -> Decimal:
        if value in (None, ""):
            return Decimal("0")
        return Decimal(str(value)).quantize(Decimal("0.01"))

    @staticmethod
    def _decimal_or_none(value):
        if value in (None, ""):
            return None
        return Decimal(str(value))

    @staticmethod
    def _as_date(value) -> date | None:
        if not value:
            return None
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value)[:10])

    def list_tds_deductors(self, *, recent_days: int = 30, limit: int = 500) -> dict:
        """TDS customer/deductor rows for Return Filing Deductor Master UI."""
        has_tan = db.session.execute(
            text(
                """
                SELECT CASE
                    WHEN COL_LENGTH(N'dbo.CustomerMaster', N'TANNumber') IS NULL THEN 0
                    ELSE 1
                END
                """
            )
        ).scalar()
        tan_expr = "ISNULL(TANNumber, N'')" if int(has_tan or 0) == 1 else "CAST(N'' AS NVARCHAR(20))"

        rows = db.session.execute(
            text(
                f"""
                SELECT TOP (:lim)
                    CustomerID,
                    CustomerName,
                    {tan_expr} AS TANNumber,
                    ISNULL(City, N'') AS City,
                    ISNULL(CustomerType, N'') AS CustomerType,
                    ISNULL(MobileNumber, N'') AS MobileNumber,
                    ISNULL(EmailID, N'') AS EmailID,
                    ISNULL(CustomerStatus, N'Active') AS CustomerStatus,
                    CreatedDate
                FROM CustomerMaster
                WHERE CustomerGroup = N'TDS'
                ORDER BY CustomerName, CustomerID DESC
                """
            ),
            {"lim": limit},
        ).mappings().all()

        all_rows: list[dict] = []
        recent_rows: list[dict] = []
        cutoff = datetime.utcnow().timestamp() - (recent_days * 86400)

        for row in rows:
            created = row.get("CreatedDate")
            created_iso = ""
            is_recent = False
            if created is not None:
                try:
                    created_iso = created.isoformat() if hasattr(created, "isoformat") else str(created)
                    ts = created.timestamp() if hasattr(created, "timestamp") else None
                    if ts is not None and ts >= cutoff:
                        is_recent = True
                except Exception:
                    created_iso = str(created)

            item = {
                "customer_id": int(row["CustomerID"]),
                "deductor_name": row.get("CustomerName") or "",
                "tan": row.get("TANNumber") or "",
                "location": row.get("City") or "",
                "deductor_type": row.get("CustomerType") or "",
                "mobile_number": row.get("MobileNumber") or "",
                "email_id": row.get("EmailID") or "",
                "customer_status": row.get("CustomerStatus") or "Active",
                "created_date": created_iso,
            }
            all_rows.append(item)
            if is_recent:
                recent_rows.append(item)

        return {
            "all": all_rows,
            "recent": recent_rows,
            "all_count": len(all_rows),
            "recent_count": len(recent_rows),
        }