from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.repositories.others_repository import WorkMasterRepository
from app.utils.db_session import persist
from app.utils.master_delete_guard import (
    assert_master_unused,
    raise_if_integrity_in_use,
)
from app.utils.master_ledger_delete import ledger_payload, raise_if_ledger_in_use
from app.utils.opening_balance import default_dr_cr_for_under_type, parse_opening_balance_fields


class WorkMasterService:
    LEDGER_INCOME = "Income"
    LEDGER_EXPENSE = "Expense"
    LEDGER_MISC = "Misc."
    LEDGER_KINDS = (LEDGER_INCOME, LEDGER_EXPENSE, LEDGER_MISC)

    def __init__(self, repository: WorkMasterRepository | None = None):
        self.repository = repository or WorkMasterRepository()
        self._chart_groups_cache: list[dict] | None = None

    def list_chart_groups_for_form(self) -> list[dict]:
        """Active Chart of Group Master rows for Under Group dropdown."""
        if self._chart_groups_cache is not None:
            return self._chart_groups_cache
        try:
            from app.services.chart_group_service import ChartGroupService

            self._chart_groups_cache = ChartGroupService().list_active_for_dropdown()
        except Exception:
            self._chart_groups_cache = []
        return self._chart_groups_cache

    def _group_meta(self, chart_group_id: int | None) -> tuple[str | None, str | None]:
        if not chart_group_id:
            return None, None
        try:
            gid = int(chart_group_id)
        except (TypeError, ValueError):
            return None, None
        for item in self.list_chart_groups_for_form():
            try:
                if int(item.get("group_id") or 0) == gid:
                    return (
                        item.get("group_name") or item.get("label"),
                        item.get("under_type") or "",
                    )
            except (TypeError, ValueError):
                continue
        return None, None

    def _parse_chart_group_id(self, payload: dict) -> int:
        raw = (
            payload.get("chart_group_id")
            if "chart_group_id" in payload
            else payload.get("ChartGroupID")
            if "ChartGroupID" in payload
            else payload.get("under_group_id")
        )
        try:
            gid = int(raw)
        except (TypeError, ValueError):
            gid = 0
        if not gid:
            raise ValueError("Under Group is required.")
        allowed = {
            int(g["group_id"])
            for g in self.list_chart_groups_for_form()
            if g.get("group_id") is not None
        }
        if gid not in allowed:
            raise ValueError("Selected Under Group is invalid or inactive.")
        return gid

    def _parse_active_status(self, payload: dict, *, default: bool = True) -> bool:
        if "active_status" not in payload and "ActiveStatus" not in payload:
            return default
        raw = payload.get("active_status")
        if raw is None:
            raw = payload.get("ActiveStatus")
        if raw is None or raw == "":
            return default
        return self._truthy(raw)

    def _sync_chart_account(self, work_id: int, chart_group_id: int, payload: dict) -> None:
        """Best-effort CoA sync — never fail WorkMaster save on CoA errors."""
        try:
            from app.services.chart_account_service import ChartAccountService

            ChartAccountService().assign_work_group(
                work_id,
                {
                    "group_id": chart_group_id,
                    "opening_balance": payload.get("opening_balance")
                    or payload.get("OpeningBalance"),
                    "opening_balance_date": payload.get("opening_balance_date")
                    or payload.get("OpeningBalanceDate"),
                    "opening_balance_dr_cr": payload.get("opening_balance_dr_cr")
                    or payload.get("OpeningBalanceDrCr"),
                },
            )
        except Exception:
            # WorkMaster row is source of truth for this page.
            pass

    def _row_dict(self, row) -> dict:
        kind = row.LedgerKind or WorkMasterService.LEDGER_INCOME
        chart_group_id = getattr(row, "ChartGroupID", None)
        try:
            chart_group_id = int(chart_group_id) if chart_group_id is not None else None
        except (TypeError, ValueError):
            chart_group_id = None
        under_group, under_type = self._group_meta(chart_group_id)
        ob = getattr(row, "OpeningBalance", None)
        ob_date = getattr(row, "OpeningBalanceDate", None)
        ob_dr_cr = getattr(row, "OpeningBalanceDrCr", None) or (
            default_dr_cr_for_under_type(under_type) if under_type else "Dr"
        )
        return {
            "work_id": row.WorkID,
            "work_name": row.WorkName,
            "ledger_kind": kind,
            "is_income": kind == WorkMasterService.LEDGER_INCOME,
            "is_expense": kind == WorkMasterService.LEDGER_EXPENSE,
            "is_misc": kind == WorkMasterService.LEDGER_MISC,
            "chart_group_id": chart_group_id,
            "under_group": under_group,
            "under_type": under_type or "",
            "opening_balance": str(ob) if ob is not None else "",
            "opening_balance_date": ob_date.isoformat() if ob_date else "",
            "opening_balance_dr_cr": ob_dr_cr or "Dr",
            "active_status": bool(row.ActiveStatus),
        }

    def list_records(
        self,
        *,
        search: str | None = None,
        ledger_kind: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        from app.repositories.others_repository import OthersIncomeExpenseRepository

        OthersIncomeExpenseRepository().ensure_schema()
        self.repository.ensure_schema()
        status_key = (status or "").strip().lower()
        active_only: bool | None
        if status_key in {"active", "1", "true"}:
            active_only = True
        elif status_key in {"inactive", "0", "false"}:
            active_only = False
        else:
            active_only = None
        rows = self.repository.list_records(
            ledger_kind=ledger_kind, active_only=active_only
        )
        if search:
            needle = search.strip().lower()
            rows = [row for row in rows if needle in (row.WorkName or "").lower()]
        return [self._row_dict(row) for row in rows]

    def get_record(self, work_id: int) -> dict:
        row = self.repository.get_by_id(work_id)
        if row is None:
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
        chart_group_id = self._parse_chart_group_id(payload)
        active_status = self._parse_active_status(payload, default=True)
        ob_fields = parse_opening_balance_fields(payload)
        if not ob_fields.get("OpeningBalanceDrCr"):
            _, under_type = self._group_meta(chart_group_id)
            ob_fields["OpeningBalanceDrCr"] = default_dr_cr_for_under_type(under_type)

        existing = self.repository.find_by_name_kind(work_name, ledger_kind)
        if existing and existing.ActiveStatus:
            raise ValueError(f"Work name '{work_name}' already exists for {ledger_kind}.")

        def _write() -> dict:
            data = {
                "WorkName": work_name,
                "LedgerKind": ledger_kind,
                "ChartGroupID": chart_group_id,
                **ob_fields,
                "ActiveStatus": active_status,
            }
            if existing and not existing.ActiveStatus:
                # Reuse inactive row instead of inserting a duplicate name/kind.
                updated = self.repository.update(
                    existing,
                    {**data, "CreatedDate": existing.CreatedDate or datetime.utcnow()},
                )
                return self._row_dict(updated)
            row = self.repository.create({**data, "CreatedDate": datetime.utcnow()})
            return self._row_dict(row)

        try:
            record = persist(_write)
        except IntegrityError as exc:
            raise ValueError(f"Work name '{work_name}' already exists for {ledger_kind}.") from exc

        self._sync_chart_account(int(record["work_id"]), chart_group_id, payload)
        return self.get_record(int(record["work_id"]))

    def update_record(self, work_id: int, payload: dict) -> dict:
        row = self.repository.get_by_id(work_id)
        if row is None:
            raise ValueError("Work type not found.")
        work_name = (payload.get("work_name") or payload.get("WorkName") or row.WorkName).strip()
        if not work_name:
            raise ValueError("Work name is required.")
        ledger_kind = self._resolve_ledger_kind(payload)
        chart_group_id = self._parse_chart_group_id(payload)
        active_status = self._parse_active_status(payload, default=bool(row.ActiveStatus))
        ob_fields = parse_opening_balance_fields(payload)
        if not ob_fields.get("OpeningBalanceDrCr"):
            _, under_type = self._group_meta(chart_group_id)
            ob_fields["OpeningBalanceDrCr"] = default_dr_cr_for_under_type(under_type)

        conflict = self.repository.find_by_name_kind(work_name, ledger_kind)
        if conflict and conflict.WorkID != row.WorkID and conflict.ActiveStatus:
            raise ValueError(f"Work name '{work_name}' already exists for {ledger_kind}.")

        def _write() -> dict:
            # Expense → Misc. (etc.): free unique key held by an inactive twin row.
            self.repository.release_inactive_name_kind(
                work_name, ledger_kind, keep_work_id=row.WorkID
            )
            updated = self.repository.update(
                row,
                {
                    "WorkName": work_name,
                    "LedgerKind": ledger_kind,
                    "ChartGroupID": chart_group_id,
                    "ActiveStatus": active_status,
                    **ob_fields,
                },
            )
            return self._row_dict(updated)

        try:
            record = persist(_write)
        except IntegrityError as exc:
            raise ValueError(f"Work name '{work_name}' already exists for {ledger_kind}.") from exc

        self._sync_chart_account(int(record["work_id"]), chart_group_id, payload)
        return self.get_record(int(record["work_id"]))

    def delete_record(self, work_id: int) -> str:
        row = self.repository.get_by_id(work_id)
        if row is None:
            raise ValueError("Work type not found.")
        work_name = (row.WorkName or "").strip()
        ledger = ledger_payload("work", work_id)
        raise_if_ledger_in_use("work", work_id, work_name or "Work")
        assert_master_unused(
            table="WorkMaster",
            pk_column="WorkID",
            pk_value=work_id,
            display_name=work_name or "Work",
            extra_checks=[
                {
                    "table": "JTCSDailyTransaction",
                    "where": "LTRIM(RTRIM(WorkType)) = :name",
                    "params": {"name": work_name},
                    "label": "Daily Transaction",
                },
                {
                    "table": "WorkTypeMaster",
                    "where": "LTRIM(RTRIM(WorkTypeName)) = :name",
                    "params": {"name": work_name},
                    "label": "Sub Work Master",
                },
            ],
            ledger=ledger,
        )
        if not row.ActiveStatus:
            return "Work type is already inactive."

        def _write() -> str:
            self.repository.deactivate(row)
            return "Work type deactivated successfully."

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise_if_integrity_in_use(exc, work_name or "Work", ledger=ledger)
            raise
