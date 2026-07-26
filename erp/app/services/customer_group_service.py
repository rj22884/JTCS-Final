from __future__ import annotations

from datetime import datetime

from app.customer_master.constants import GROUP_TABS, TAB_LABELS
from app.repositories.customer_group_repository import CustomerGroupRepository
from app.utils.db_session import persist

AVAILABLE_TAB_CODES = list(TAB_LABELS.keys())


class CustomerGroupService:
    def __init__(self, repository: CustomerGroupRepository | None = None):
        self.repository = repository or CustomerGroupRepository()

    @staticmethod
    def _parse_tab_codes(raw) -> list[str]:
        if isinstance(raw, list):
            items = raw
        else:
            items = str(raw or "").split(",")
        tabs = []
        for item in items:
            code = str(item).strip().lower()
            if code and code in TAB_LABELS and code not in tabs:
                tabs.append(code)
        if not tabs:
            raise ValueError("Select at least one tab for the group.")
        return tabs

    def list_records(self, *, search: str | None = None, active_only: bool = False) -> list[dict]:
        rows = self.repository.list_dicts(active_only=active_only)
        if search:
            needle = search.strip().lower()
            rows = [
                row
                for row in rows
                if needle in (row["group_name"] or "").lower()
                or needle in (row["group_code"] or "").lower()
            ]
        return rows

    def list_active_groups(self) -> list[dict]:
        return [
            {"code": row["group_code"], "label": row["group_name"]}
            for row in self.repository.list_dicts(active_only=True)
        ]

    def build_group_tabs_map(self) -> dict[str, list[str]]:
        result = {}
        for row in self.repository.list_dicts(active_only=True):
            result[row["group_code"]] = row["tab_codes"]
        return result or dict(GROUP_TABS)

    def get_record(self, group_id: int) -> dict:
        row = self.repository.get_by_id(group_id)
        if row is None:
            raise ValueError("Group not found.")
        return self.repository._row_dict(row)

    def create_record(self, payload: dict) -> dict:
        group_code = (payload.get("group_code") or payload.get("GroupCode") or "").strip().upper()
        group_name = (payload.get("group_name") or payload.get("GroupName") or "").strip()
        if not group_code:
            raise ValueError("Group code is required.")
        if not group_name:
            raise ValueError("Group name is required.")
        if self.repository.get_by_code(group_code):
            raise ValueError(f"Group code '{group_code}' already exists.")
        tabs = self._parse_tab_codes(payload.get("tab_codes") or payload.get("TabCodes"))
        try:
            display_order = int(payload.get("display_order") or payload.get("DisplayOrder") or 1)
        except (TypeError, ValueError):
            display_order = 1

        def _write() -> dict:
            row = self.repository.create(
                {
                    "GroupCode": group_code,
                    "GroupName": group_name,
                    "TabCodes": ",".join(tabs),
                    "DisplayOrder": display_order,
                    "ActiveStatus": True,
                    "CreatedDate": datetime.utcnow(),
                }
            )
            return self.repository._row_dict(row)

        return persist(_write)

    def update_record(self, group_id: int, payload: dict) -> dict:
        row = self.repository.get_by_id(group_id)
        if row is None:
            raise ValueError("Group not found.")
        group_name = (payload.get("group_name") or payload.get("GroupName") or row.GroupName).strip()
        if not group_name:
            raise ValueError("Group name is required.")
        tabs = self._parse_tab_codes(payload.get("tab_codes") or payload.get("TabCodes") or row.TabCodes)
        try:
            display_order = int(payload.get("display_order") or payload.get("DisplayOrder") or row.DisplayOrder)
        except (TypeError, ValueError):
            display_order = row.DisplayOrder
        active_status = row.ActiveStatus
        if "active_status" in payload or "ActiveStatus" in payload:
            raw = payload.get("active_status", payload.get("ActiveStatus"))
            active_status = str(raw).lower() in {"1", "true", "yes", "on", "active"}

        def _write() -> dict:
            updated = self.repository.update(
                row,
                {
                    "GroupName": group_name,
                    "TabCodes": ",".join(tabs),
                    "DisplayOrder": display_order,
                    "ActiveStatus": active_status,
                },
            )
            return self.repository._row_dict(updated)

        return persist(_write)

    def delete_record(self, group_id: int) -> str:
        def _write() -> str:
            row = self.repository.get_by_id(group_id)
            if row is None:
                raise ValueError("Group not found.")
            if not row.ActiveStatus:
                raise ValueError("Group is already inactive.")
            self.repository.deactivate(row)
            return "Group marked inactive successfully."

        return persist(_write)

    def activate_record(self, group_id: int) -> dict:
        def _write() -> dict:
            row = self.repository.get_by_id(group_id)
            if row is None:
                raise ValueError("Group not found.")
            if row.ActiveStatus:
                raise ValueError("Group is already active.")
            updated = self.repository.activate(row)
            return self.repository._row_dict(updated)

        return persist(_write)

    @staticmethod
    def ui_config() -> dict:
        return {
            "available_tabs": [
                {"code": code, "label": TAB_LABELS[code]} for code in AVAILABLE_TAB_CODES
            ],
        }
