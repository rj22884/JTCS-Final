from __future__ import annotations

from datetime import datetime

from app.customer_master.constants import GROUP_TABS, TAB_LABELS
from app.repositories.customer_group_repository import CustomerGroupRepository
from app.utils.db_session import persist
from app.utils.master_delete_guard import assert_master_unused

AVAILABLE_TAB_CODES = list(TAB_LABELS.keys())


def is_universal_customer_group(code: str | None, name: str | None = None) -> bool:
    """Catch-all groups such as 'None above' apply to every Chart of Account Group."""
    label = (name or "").strip().casefold()
    if "none above" in label:
        return True
    key = (code or "").strip().upper().replace(" ", "").replace("_", "").replace("-", "")
    return key in {"NONE", "NONEABOVE", "NA"}


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

    def chart_group_usage_map(self) -> dict[str, list[int]]:
        """Existing Customer Group → Chart of Account Group IDs (read-only)."""
        from sqlalchemy import text

        from app.extensions import db

        usage: dict[str, list[int]] = {}
        try:
            rows = db.session.execute(
                text(
                    """
                    SELECT DISTINCT
                        UPPER(LTRIM(RTRIM(c.CustomerGroup))) AS CustomerGroup,
                        a.GroupID
                    FROM dbo.CustomerMaster c
                    INNER JOIN dbo.ChartOfAccountMaster a ON a.CustomerID = c.CustomerID
                    WHERE c.CustomerGroup IS NOT NULL
                      AND LTRIM(RTRIM(c.CustomerGroup)) <> N''
                      AND a.GroupID IS NOT NULL
                      AND ISNULL(a.IsActive, 1) = 1
                    """
                )
            ).mappings().all()
        except Exception:
            db.session.rollback()
            return usage
        for row in rows:
            code = (row.get("CustomerGroup") or "").strip().upper()
            try:
                gid = int(row.get("GroupID"))
            except (TypeError, ValueError):
                continue
            if not code or gid <= 0:
                continue
            bucket = usage.setdefault(code, [])
            if gid not in bucket:
                bucket.append(gid)
        return usage

    @staticmethod
    def filter_codes_for_chart(
        *,
        active_codes: list[str],
        chart_group_id: int | None,
        chart_nature: str | None,
        usage: dict[str, list[int]] | dict[str, set[int]],
        nature_by_chart_id: dict[int, str],
        include_code: str | None = None,
        labels: dict[str, str] | None = None,
    ) -> list[str]:
        """All active Customer Groups are listed for any Chart of Account Group."""
        _ = (chart_nature, usage, nature_by_chart_id, labels)
        if not chart_group_id:
            return []
        allowed: list[str] = []
        seen = set()
        for raw in active_codes:
            code = (raw or "").strip()
            if not code:
                continue
            key = code.upper()
            if key in seen:
                continue
            seen.add(key)
            allowed.append(code)
        include = (include_code or "").strip()
        if include and include.upper() not in seen:
            allowed.append(include)
        return allowed

    def allowed_group_codes(
        self,
        chart_group_id: int | None,
        *,
        include_code: str | None = None,
    ) -> list[str]:
        active = [g["code"] for g in self.list_active_groups()]
        labels = {
            (g["code"] or "").strip().upper(): g.get("label") or ""
            for g in self.list_active_groups()
        }
        if not chart_group_id:
            return []
        natures: dict[int, str] = {}
        selected_nature = ""
        try:
            from app.services.chart_group_service import ChartGroupService

            for item in ChartGroupService().list_active_for_dropdown():
                gid = int(item.get("group_id") or 0)
                if gid <= 0:
                    continue
                natures[gid] = (item.get("group_nature") or "").strip()
            selected_nature = natures.get(int(chart_group_id), "")
        except Exception:
            natures = {}
        return self.filter_codes_for_chart(
            active_codes=active,
            chart_group_id=int(chart_group_id),
            chart_nature=selected_nature,
            usage=self.chart_group_usage_map(),
            nature_by_chart_id=natures,
            include_code=include_code,
            labels=labels,
        )

    def is_group_valid_for_chart(
        self,
        customer_group: str | None,
        chart_group_id: int | None,
    ) -> bool:
        code = (customer_group or "").strip().upper()
        if not code or not chart_group_id:
            return False
        allowed = {c.upper() for c in self.allowed_group_codes(int(chart_group_id))}
        return code in allowed

    def customer_form_filter_payload(self) -> dict:
        natures: dict[str, str] = {}
        try:
            from app.services.chart_group_service import ChartGroupService

            for item in ChartGroupService().list_active_for_dropdown():
                gid = item.get("group_id")
                if gid is None:
                    continue
                natures[str(int(gid))] = (item.get("group_nature") or "").strip()
        except Exception:
            natures = {}
        return {
            "groups": self.list_active_groups(),
            "usage": self.chart_group_usage_map(),
            "chart_natures": natures,
        }

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
        tabs = list(AVAILABLE_TAB_CODES)
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
            assert_master_unused(
                table="CustomerGroupMaster",
                pk_column="GroupID",
                pk_value=group_id,
                display_name=row.GroupName or row.GroupCode or "Customer group",
                column_aliases=[],
                extra_checks=[
                    {
                        "table": "CustomerMaster",
                        "where": "UPPER(LTRIM(RTRIM(CustomerGroup))) = :code",
                        "params": {"code": (row.GroupCode or "").strip().upper()},
                        "label": "Customer Master",
                    },
                ],
            )
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
        return {}
