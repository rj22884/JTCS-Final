from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.repositories.others_repository import WorkMasterRepository
from app.utils.db_session import persist


class WorkMasterService:
    LEDGER_INCOME = "Income"
    LEDGER_EXPENSE = "Expense"
    LEDGER_MISC = "Misc."
    LEDGER_KINDS = (LEDGER_INCOME, LEDGER_EXPENSE, LEDGER_MISC)

    def __init__(self, repository: WorkMasterRepository | None = None):
        self.repository = repository or WorkMasterRepository()

    @staticmethod
    def _row_dict(row) -> dict:
        kind = row.LedgerKind or WorkMasterService.LEDGER_INCOME
        return {
            "work_id": row.WorkID,
            "work_name": row.WorkName,
            "ledger_kind": kind,
            "is_income": kind == WorkMasterService.LEDGER_INCOME,
            "is_expense": kind == WorkMasterService.LEDGER_EXPENSE,
            "is_misc": kind == WorkMasterService.LEDGER_MISC,
            "active_status": bool(row.ActiveStatus),
        }

    def list_records(self, *, search: str | None = None, ledger_kind: str | None = None) -> list[dict]:
        from app.repositories.others_repository import OthersIncomeExpenseRepository

        OthersIncomeExpenseRepository().ensure_schema()
        rows = self.repository.list_active(ledger_kind=ledger_kind)
        if search:
            needle = search.strip().lower()
            rows = [row for row in rows if needle in (row.WorkName or "").lower()]
        return [self._row_dict(row) for row in rows]

    def get_record(self, work_id: int) -> dict:
        row = self.repository.get_by_id(work_id)
        if row is None or not row.ActiveStatus:
            raise ValueError("Work type not found.")
        return self._row_dict(row)

    @staticmethod
    def _truthy(value) -> bool:
        return str(value).lower() in {"1", "true", "yes", "on"}

    def _normalize_ledger_kind(self, raw: str | None) -> str | None:
        kind = (raw or "").strip()
        if not kind:
            return None
        if kind in self.LEDGER_KINDS:
            return kind
        lower = kind.lower().rstrip(".")
        if lower == "income":
            return self.LEDGER_INCOME
        if lower == "expense":
            return self.LEDGER_EXPENSE
        if lower == "misc":
            return self.LEDGER_MISC
        return None

    def _resolve_ledger_kind(self, payload: dict) -> str:
        # Explicit ledger_kind / LedgerKind always wins (never fall through to flags).
        if "ledger_kind" in payload or "LedgerKind" in payload:
            raw = payload.get("ledger_kind")
            if raw is None or raw == "":
                raw = payload.get("LedgerKind")
            normalized = self._normalize_ledger_kind(None if raw is None else str(raw))
            if normalized:
                return normalized
            if raw is not None and str(raw).strip():
                raise ValueError("Select Income, Expense, or Misc.")

        if self._truthy(payload.get("is_misc")) or self._truthy(payload.get("IsMisc")):
            return self.LEDGER_MISC

        has_income = "is_income" in payload or "IsIncome" in payload
        has_expense = "is_expense" in payload or "IsExpense" in payload
        is_income = payload.get("is_income")
        if is_income is None:
            is_income = payload.get("IsIncome")
        is_expense = payload.get("is_expense")
        if is_expense is None:
            is_expense = payload.get("IsExpense")

        income_on = has_income and self._truthy(is_income)
        expense_on = has_expense and self._truthy(is_expense)
        if income_on and not expense_on:
            return self.LEDGER_INCOME
        if expense_on and not income_on:
            return self.LEDGER_EXPENSE
        if income_on and expense_on:
            raise ValueError("Select only one of Income, Expense, or Misc.")

        # Both flags present but off (legacy Misc. payload without is_misc) — do not
        # treat is_income=0 as Expense.
        if has_income and has_expense and not income_on and not expense_on:
            raise ValueError("Select Income, Expense, or Misc.")

        if has_income:
            return self.LEDGER_INCOME if self._truthy(is_income) else self.LEDGER_EXPENSE
        if has_expense:
            return self.LEDGER_EXPENSE if self._truthy(is_expense) else self.LEDGER_INCOME

        raise ValueError("Select Income, Expense, or Misc.")

    def create_record(self, payload: dict) -> dict:
        from app.repositories.others_repository import OthersIncomeExpenseRepository

        OthersIncomeExpenseRepository().ensure_schema()
        work_name = (payload.get("work_name") or payload.get("WorkName") or "").strip()
        if not work_name:
            raise ValueError("Work name is required.")
        ledger_kind = self._resolve_ledger_kind(payload)
        if self.repository.find_by_name_kind(work_name, ledger_kind):
            raise ValueError(f"Work name '{work_name}' already exists for {ledger_kind}.")

        def _write() -> dict:
            row = self.repository.create(
                {
                    "WorkName": work_name,
                    "LedgerKind": ledger_kind,
                    "ActiveStatus": True,
                    "CreatedDate": datetime.utcnow(),
                }
            )
            return self._row_dict(row)

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise ValueError(f"Work name '{work_name}' already exists for {ledger_kind}.") from exc

    def update_record(self, work_id: int, payload: dict) -> dict:
        row = self.repository.get_by_id(work_id)
        if row is None or not row.ActiveStatus:
            raise ValueError("Work type not found.")
        work_name = (payload.get("work_name") or payload.get("WorkName") or row.WorkName).strip()
        if not work_name:
            raise ValueError("Work name is required.")
        ledger_kind = self._resolve_ledger_kind(payload)
        existing = self.repository.find_by_name_kind(work_name, ledger_kind)
        if existing and existing.WorkID != row.WorkID:
            raise ValueError(f"Work name '{work_name}' already exists for {ledger_kind}.")

        def _write() -> dict:
            updated = self.repository.update(
                row,
                {"WorkName": work_name, "LedgerKind": ledger_kind},
            )
            return self._row_dict(updated)

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise ValueError(f"Work name '{work_name}' already exists for {ledger_kind}.") from exc

    def delete_record(self, work_id: int) -> str:
        row = self.repository.get_by_id(work_id)
        if row is None or not row.ActiveStatus:
            raise ValueError("Work type not found.")

        def _write() -> str:
            self.repository.deactivate(row)
            return "Work type deactivated successfully."

        return persist(_write)
