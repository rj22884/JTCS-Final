from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.repositories.chart_group_repository import ChartGroupRepository
from app.utils.db_session import persist

VALID_UNDER = {"Assets", "Liabilities"}

class ChartGroupService:
    def __init__(self, repository: ChartGroupRepository | None = None):
        self.repo = repository or ChartGroupRepository()

    def _parent_lookup(self) -> dict[int, object]:
        return {int(r.GroupID): r for r in self.repo.list_all()}

    def _serialize(self, row, by_id: dict | None = None) -> dict:
        by_id = by_id if by_id is not None else self._parent_lookup()
        parent_id = getattr(row, "ParentGroupID", None)
        parent_name = ""
        if parent_id:
            parent = by_id.get(int(parent_id))
            if parent is not None:
                parent_name = parent.GroupName or ""
        under_label = parent_name or (row.UnderType or "")
        nature = (getattr(row, "GroupNature", None) or "").strip()
        return {
            "group_id": row.GroupID,
            "group_name": row.GroupName or "",
            "under_type": row.UnderType or "",
            "parent_group_id": int(parent_id) if parent_id else None,
            "parent_group_name": parent_name,
            "group_nature": nature,
            "under_label": under_label,
            "is_active": bool(row.IsActive),
            "created_date": row.CreatedDate.isoformat() if row.CreatedDate else "",
            "updated_date": row.UpdatedDate.isoformat() if row.UpdatedDate else "",
        }

    def list_records(self, *, search: str | None = None, active_only: bool = False) -> list[dict]:
        by_id = self._parent_lookup()
        return [
            self._serialize(row, by_id)
            for row in self.repo.list_all(search=search, active_only=active_only)
        ]

    def list_active_for_dropdown(self) -> list[dict]:
        from app.services.financial_statements.engine import NATURE_BY_NAME

        by_id = self._parent_lookup()
        rows = []
        for row in self.repo.list_all(active_only=True):
            parent_name = ""
            if getattr(row, "ParentGroupID", None):
                parent = by_id.get(int(row.ParentGroupID))
                if parent is not None:
                    parent_name = parent.GroupName or ""
            under = parent_name or row.UnderType or ""
            nature = ""
            cur = row
            hops = 0
            seen: set[int] = set()
            while cur is not None and hops < 40:
                gid = int(cur.GroupID)
                if gid in seen:
                    break
                seen.add(gid)
                mapped = NATURE_BY_NAME.get((cur.GroupName or "").strip())
                if mapped:
                    nature = mapped
                    break
                stored = (getattr(cur, "GroupNature", None) or "").strip()
                if stored in {"Asset", "Liability", "Income", "Expense"}:
                    nature = stored
                    break
                cur = by_id.get(int(cur.ParentGroupID)) if cur.ParentGroupID else None
                hops += 1
            if nature not in {"Asset", "Liability", "Income", "Expense"}:
                nature = "Asset" if (row.UnderType or "") == "Assets" else "Liability"
            rows.append(
                {
                    "group_id": row.GroupID,
                    "group_name": row.GroupName,
                    "under_type": row.UnderType,
                    "parent_group_id": int(row.ParentGroupID) if row.ParentGroupID else None,
                    "parent_group_name": parent_name,
                    "group_nature": nature,
                    "label": f"{row.GroupName} ({under})",
                }
            )
        return rows

    def get_record(self, group_id: int) -> dict:
        row = self.repo.get_by_id(group_id)
        if row is None:
            raise ValueError("Group not found.")
        return self._serialize(row)

    def _nature_from_under(self, under: str) -> str:
        return "Asset" if under == "Assets" else "Liability"

    def _inherit_from_parent(self, parent) -> tuple[str, str]:
        nature = (getattr(parent, "GroupNature", None) or "").strip()
        if nature not in {"Asset", "Liability", "Income", "Expense"}:
            nature = self._nature_from_under(parent.UnderType or "Assets")
        under = parent.UnderType if (parent.UnderType or "") in VALID_UNDER else (
            "Assets" if nature in {"Asset", "Expense"} else "Liabilities"
        )
        return under, nature

    def _would_cycle(self, group_id: int | None, parent_id: int) -> bool:
        if group_id and int(group_id) == int(parent_id):
            return True
        seen = {int(group_id)} if group_id else set()
        cur = self.repo.get_by_id(int(parent_id))
        hops = 0
        while cur is not None and hops < 40:
            gid = int(cur.GroupID)
            if gid in seen:
                return True
            seen.add(gid)
            if not cur.ParentGroupID:
                return False
            cur = self.repo.get_by_id(int(cur.ParentGroupID))
            hops += 1
        return False

    def _parse(self, payload: dict, *, existing=None) -> dict:
        name = (payload.get("group_name") or payload.get("GroupName") or "").strip()
        under = (payload.get("under_type") or payload.get("UnderType") or "").strip()
        raw_parent = payload.get("parent_group_id")
        if raw_parent is None:
            raw_parent = payload.get("ParentGroupID")

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

        parent_id = None
        nature = None
        try:
            if raw_parent not in (None, "", 0, "0"):
                parent_id = int(raw_parent)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid parent group.") from exc

        if parent_id:
            parent = self.repo.get_by_id(parent_id)
            if parent is None or not parent.IsActive:
                raise ValueError("Under group is invalid or inactive.")
            existing_id = existing.GroupID if existing is not None else None
            if self._would_cycle(existing_id, parent_id):
                raise ValueError("A group cannot be placed under itself.")
            under, nature = self._inherit_from_parent(parent)
        else:
            if under not in VALID_UNDER:
                raise ValueError("Under must be a parent group, or Assets / Liabilities.")
            nature = self._nature_from_under(under)

        return {
            "GroupName": name,
            "UnderType": under,
            "ParentGroupID": parent_id,
            "GroupNature": nature,
            "IsActive": is_active,
        }

    def _adopt_matching_ledgers(self, group_id: int, group_name: str, parent_id: int | None) -> None:
        """If this group sits under Investments (etc.), move same-name Individual Client ledgers here."""
        if not parent_id:
            return
        ancestor_names = []
        cur = self.repo.get_by_id(int(parent_id))
        hops = 0
        while cur is not None and hops < 40:
            ancestor_names.append((cur.GroupName or "").strip().casefold())
            if not cur.ParentGroupID:
                break
            cur = self.repo.get_by_id(int(cur.ParentGroupID))
            hops += 1
        if "investments" not in ancestor_names and "fixed assets" not in ancestor_names:
            return
        default_row = self.repo.find_by_name("Individual Client")
        if default_row is None:
            return
        db.session.execute(
            text(
                """
                UPDATE a
                SET a.GroupID = :new_gid,
                    a.UpdatedDate = SYSUTCDATETIME()
                FROM dbo.ChartOfAccountMaster a
                LEFT JOIN dbo.CustomerMaster c ON c.CustomerID = a.CustomerID
                WHERE a.IsActive = 1
                  AND a.GroupID = :old_gid
                  AND (
                        LOWER(LTRIM(RTRIM(a.AccountName))) = LOWER(LTRIM(RTRIM(:gname)))
                     OR LOWER(LTRIM(RTRIM(ISNULL(c.CustomerName, N''))))
                            = LOWER(LTRIM(RTRIM(:gname)))
                  )
                """
            ),
            {
                "new_gid": int(group_id),
                "old_gid": int(default_row.GroupID),
                "gname": group_name,
            },
        )

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
            self._adopt_matching_ledgers(row.GroupID, row.GroupName, row.ParentGroupID)
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
            self._adopt_matching_ledgers(
                updated.GroupID, updated.GroupName, updated.ParentGroupID
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
        children = db.session.execute(
            text(
                "SELECT COUNT(1) FROM dbo.ChartOfGroupMaster WHERE ParentGroupID = :gid"
            ),
            {"gid": group_id},
        ).scalar()
        if int(children or 0) > 0:
            raise ValueError(
                f"Cannot delete group '{row.GroupName}' — child groups still exist under it."
            )

        def _write() -> str:
            name = row.GroupName
            self.repo.delete(row)
            return f"Group '{name}' deleted."

        return persist(_write)
