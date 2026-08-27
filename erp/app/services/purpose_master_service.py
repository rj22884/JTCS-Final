from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.repositories.purpose_master_repository import PurposeMasterRepository
from app.utils.db_session import persist
from app.utils.master_delete_guard import assert_master_unused, raise_if_integrity_in_use


class PurposeMasterService:
    def __init__(self, repository: PurposeMasterRepository | None = None):
        self.repo = repository or PurposeMasterRepository()

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

    def _parse_form(self, form: dict) -> dict:
        purpose_name = self._clean(form.get("PurposeName"), 200)
        if not purpose_name:
            raise ValueError("Purpose Name is required.")

        if "ActiveStatus" in form or "active_status" in form:
            active_raw = (form.get("ActiveStatus") or form.get("active_status") or "").strip().lower()
            active = active_raw in {"1", "true", "on", "yes"}
        else:
            active = False

        return {
            "PurposeName": purpose_name,
            "Description": self._clean(form.get("Description"), 500),
            "ActiveStatus": active,
        }

    @staticmethod
    def _serialize(row) -> dict:
        return {
            "purpose_id": row.PurposeID,
            "purpose_name": row.PurposeName or "",
            "description": row.Description or "",
            "active_status": bool(row.ActiveStatus),
            "created_date": row.CreatedDate.isoformat() if isinstance(row.CreatedDate, datetime) else "",
            "modified_date": row.ModifiedDate.isoformat() if isinstance(row.ModifiedDate, datetime) else "",
        }

    def list_records(self, *, search: str | None = None, active_only: bool = False) -> list[dict]:
        return [
            self._serialize(row)
            for row in self.repo.list_all(search=search, active_only=active_only)
        ]

    def get_record(self, purpose_id: int) -> dict:
        row = self.repo.get_by_id(purpose_id)
        if row is None:
            raise ValueError("Purpose not found.")
        return self._serialize(row)

    def create_record(self, form: dict, *, created_by: str = "System") -> dict:
        data = self._parse_form(form)

        def _write() -> dict:
            row = self.repo.create({**data, "CreatedBy": created_by})
            return self._serialize(row)

        return persist(_write)

    def update_record(self, purpose_id: int, form: dict) -> dict:
        data = self._parse_form(form)

        def _write() -> dict:
            row = self.repo.get_by_id(purpose_id)
            if row is None:
                raise ValueError("Purpose not found.")
            row = self.repo.update(row, data)
            return self._serialize(row)

        return persist(_write)

    def delete_record(self, purpose_id: int) -> str:
        def _write() -> str:
            row = self.repo.get_by_id(purpose_id)
            if row is None:
                raise ValueError("Purpose not found.")
            label = row.PurposeName or "Purpose"
            assert_master_unused(
                table="PurposeMaster",
                pk_column="PurposeID",
                pk_value=purpose_id,
                display_name=label,
                extra_checks=[
                    {
                        "table": "OthersBankCashTransaction",
                        "where": "LTRIM(RTRIM(Purpose)) = :name",
                        "params": {"name": (row.PurposeName or "").strip()},
                        "label": "Bank / Cash Transaction",
                    },
                ],
            )
            if row.ActiveStatus:
                self.repo.update(row, {"ActiveStatus": False})
                return "Purpose marked inactive."
            self.repo.delete(row)
            return "Purpose deleted successfully."

        try:
            return persist(_write)
        except IntegrityError as exc:
            row = self.repo.get_by_id(purpose_id)
            raise_if_integrity_in_use(exc, (row.PurposeName if row else None) or "Purpose")
            raise
