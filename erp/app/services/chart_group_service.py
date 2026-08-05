from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.repositories.chart_group_repository import ChartGroupRepository
from app.utils.db_session import persist

VALID_UNDER = {"Assets", "Liabilities"}


class ChartGroupService:
    def __init__(self, repository: ChartGroupRepository | None = None):
        self.repo = repository or ChartGroupRepository()

    @staticmethod
    def _serialize(row) -> dict:
        return {
            "group_id": row.GroupID,
            "group_name": row.GroupName or "",
            "under_type": row.UnderType or "",
            "is_active": bool(row.IsActive),
            "created_date": row.CreatedDate.isoformat() if row.CreatedDate else "",
            "updated_date": row.UpdatedDate.isoformat() if row.UpdatedDate else "",
        }

    def list_records(self, *, search: str | None = None, active_only: bool = False) -> list[dict]:
        return [
            self._serialize(row)
            for row in self.repo.list_all(search=search, active_only=active_only)
        ]

    def list_active_for_dropdown(self) -> list[dict]:
        rows = self.repo.list_all(active_only=True)
        return [
            {
                "group_id": row.GroupID,
                "group_name": row.GroupName,
                "under_type": row.UnderType,
                "label": f"{row.GroupName} ({row.UnderType})",
            }
            for row in rows
        ]

    def get_record(self, group_id: int) -> dict:
        row = self.repo.get_by_id(group_id)
        if row is None:
            raise ValueError("Group not found.")
        return self._serialize(row)

    def _parse(self, payload: dict, *, existing=None) -> dict:
        name = (payload.get("group_name") or payload.get("GroupName") or "").strip()
        under = (payload.get("under_type") or payload.get("UnderType") or "").strip()

        if "is_active" in payload or "IsActive" in payload:
            active_raw = payload.get("is_active")
            if active_raw is None:
                active_raw = payload.get("IsActive")
            is_active = str(active_raw).lower() in {"1", "true", "yes", "on"}
        elif existing is not None:
            is_active = bool(existing.IsActive)
        else:
            is_active = True

        if not name:
            raise ValueError("Group Name is required.")
        if len(name) > 150:
            raise ValueError("Group Name must be at most 150 characters.")
        if under not in VALID_UNDER:
            raise ValueError("Under must be Assets or Liabilities.")

        return {
            "GroupName": name,
            "UnderType": under,
            "IsActive": is_active,
        }

    def create_record(self, payload: dict) -> dict:
        data = self._parse(payload)
        if self.repo.find_by_name(data["GroupName"]):
            raise ValueError(f"Group Name '{data['GroupName']}' already exists.")

        def _write() -> dict:
            row = self.repo.create(
                {
                    **data,
                    "CreatedDate": datetime.utcnow(),
                    "UpdatedDate": None,
                }
            )
            return self._serialize(row)

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise ValueError(f"Group Name '{data['GroupName']}' already exists.") from exc

    def update_record(self, group_id: int, payload: dict) -> dict:
        row = self.repo.get_by_id(group_id)
        if row is None:
            raise ValueError("Group not found.")
        data = self._parse(payload, existing=row)
        if self.repo.find_by_name(data["GroupName"], exclude_id=group_id):
            raise ValueError(f"Group Name '{data['GroupName']}' already exists.")

        def _write() -> dict:
            updated = self.repo.update(
                row,
                {
                    **data,
                    "UpdatedDate": datetime.utcnow(),
                },
            )
            return self._serialize(updated)

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise ValueError(f"Group Name '{data['GroupName']}' already exists.") from exc

    def delete_record(self, group_id: int) -> str:
        row = self.repo.get_by_id(group_id)
        if row is None:
            raise ValueError("Group not found.")
        linked = self.repo.count_accounts(group_id)
        if linked > 0:
            raise ValueError(
                f"Cannot delete group '{row.GroupName}' — {linked} account(s) still reference it."
            )

        def _write() -> str:
            name = row.GroupName
            self.repo.delete(row)
            return f"Group '{name}' deleted."

        return persist(_write)
