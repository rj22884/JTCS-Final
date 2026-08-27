from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.repositories.account_type_repository import AccountTypeRepository, SEED_TYPES
from app.utils.db_session import persist
from app.utils.master_delete_guard import (
    MasterInUseError,
    assert_master_unused,
    raise_if_integrity_in_use,
)

# Backward-compatible tuple of seed codes (tests / legacy imports).
ACCOUNT_TYPE_CODES = tuple(code for code, *_ in SEED_TYPES)


class AccountTypeMasterService:
    def __init__(self, repository: AccountTypeRepository | None = None):
        self.repo = repository or AccountTypeRepository()

    @staticmethod
    def _serialize(row) -> dict:
        return {
            "account_type_id": row.AccountTypeID,
            "account_type_code": row.AccountTypeCode or "",
            "account_type_name": row.AccountTypeName or "",
            "description": row.Description or "",
            "order_no": int(row.OrderNo or 100),
            "is_active": bool(row.IsActive),
            "created_at": row.CreatedAt.isoformat() if row.CreatedAt else "",
            "updated_at": row.UpdatedAt.isoformat() if row.UpdatedAt else "",
        }

    def list_records(self, *, search: str | None = None, active_only: bool = False) -> list[dict]:
        return [
            self._serialize(row)
            for row in self.repo.list_all(search=search, active_only=active_only)
        ]

    def list_active_for_dropdown(self) -> list[dict]:
        """Active types for Bank Master select (code + display label)."""
        rows = self.repo.list_all(active_only=True)
        return [
            {
                "code": row.AccountTypeCode,
                "name": row.AccountTypeName,
                "label": f"{row.AccountTypeCode} - {row.AccountTypeName}",
            }
            for row in rows
        ]

    def get_record(self, account_type_id: int) -> dict:
        row = self.repo.get_by_id(account_type_id)
        if row is None:
            raise ValueError("Account type not found.")
        return self._serialize(row)

    def _parse(self, payload: dict, *, existing=None) -> dict:
        raw_code = (payload.get("account_type_code") or payload.get("AccountTypeCode") or "").strip()
        # Preserve case (e.g. CA-Current Asset). Only normalize slash codes like cc/od → CC/OD.
        if raw_code and "/" in raw_code and " " not in raw_code and "-" not in raw_code:
            code = "/".join(part.strip().upper() for part in raw_code.split("/") if part.strip())
        else:
            code = " ".join(raw_code.split()) if raw_code else ""

        name = (payload.get("account_type_name") or payload.get("AccountTypeName") or "").strip()
        description = (payload.get("description") or payload.get("Description") or "").strip() or None
        order_raw = payload.get("order_no") if "order_no" in payload else payload.get("OrderNo")
        try:
            order_no = int(order_raw) if order_raw not in (None, "") else 100
        except (TypeError, ValueError):
            order_no = 100

        if "is_active" in payload or "IsActive" in payload:
            active_raw = payload.get("is_active")
            if active_raw is None:
                active_raw = payload.get("IsActive")
            is_active = str(active_raw).lower() in {"1", "true", "yes", "on"}
        elif existing is not None:
            is_active = bool(existing.IsActive)
        else:
            is_active = True

        if not code:
            raise ValueError("Account Type Code is required.")
        if len(code) > 20:
            raise ValueError("Account Type Code must be at most 20 characters.")
        if not name:
            raise ValueError("Account Type Name is required.")

        return {
            "AccountTypeCode": code,
            "AccountTypeName": name[:100],
            "Description": (description[:255] if description else None),
            "OrderNo": order_no,
            "IsActive": is_active,
        }

    def create_record(self, payload: dict) -> dict:
        data = self._parse(payload)
        if self.repo.find_by_code(data["AccountTypeCode"]):
            raise ValueError(f"Account Type Code '{data['AccountTypeCode']}' already exists.")

        def _write() -> dict:
            row = self.repo.create(
                {
                    **data,
                    "CreatedAt": datetime.utcnow(),
                    "UpdatedAt": None,
                }
            )
            return self._serialize(row)

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise ValueError(f"Account Type Code '{data['AccountTypeCode']}' already exists.") from exc

    def update_record(self, account_type_id: int, payload: dict) -> dict:
        row = self.repo.get_by_id(account_type_id)
        if row is None:
            raise ValueError("Account type not found.")
        data = self._parse(payload, existing=row)
        other = self.repo.find_by_code(data["AccountTypeCode"])
        if other and other.AccountTypeID != row.AccountTypeID:
            raise ValueError(f"Account Type Code '{data['AccountTypeCode']}' already exists.")

        # If code changes while in use under old code, block rename.
        if data["AccountTypeCode"] != row.AccountTypeCode and self.repo.usage_count(row.AccountTypeCode) > 0:
            raise ValueError(
                "This Account Type is already in use and cannot be renamed. "
                "You can set it Inactive instead."
            )

        def _write() -> dict:
            updated = self.repo.update(
                row,
                {**data, "UpdatedAt": datetime.utcnow()},
            )
            return self._serialize(updated)

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise ValueError(f"Account Type Code '{data['AccountTypeCode']}' already exists.") from exc

    def delete_record(self, account_type_id: int) -> str:
        row = self.repo.get_by_id(account_type_id)
        if row is None:
            raise ValueError("Account type not found.")
        label = row.AccountTypeCode or row.AccountTypeName or "Account type"
        assert_master_unused(
            table="AccountTypeMaster",
            pk_column="AccountTypeID",
            pk_value=account_type_id,
            display_name=label,
            extra_checks=[
                {
                    "table": "JtcsBankAccountMaster",
                    "where": "LTRIM(RTRIM(AccountType)) = :code",
                    "params": {"code": (row.AccountTypeCode or "").strip()},
                    "label": "Bank Master",
                },
            ],
        )
        if self.repo.usage_count(row.AccountTypeCode) > 0:
            raise MasterInUseError(
                f"Stop: '{label}' is already in use and cannot be deleted."
            )

        def _write() -> str:
            self.repo.delete(row)
            return "Account type deleted successfully."

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise_if_integrity_in_use(exc, label)
            raise

    def is_valid_code(self, code: str, *, allow_inactive: bool = False) -> bool:
        row = self.repo.find_by_code((code or "").strip())
        if row is None:
            return False
        if allow_inactive:
            return True
        return bool(row.IsActive)
