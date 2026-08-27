"""Sub Work Master: WorkMaster (by LedgerKind) → WorkTypeMaster.SubWorkType."""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.others import WorkMaster
from app.models.transactions import WorkTypeMaster
from app.repositories.others_repository import OthersIncomeExpenseRepository, WorkMasterRepository
from app.utils.db_session import persist
from app.utils.master_delete_guard import (
    assert_master_unused,
    raise_if_integrity_in_use,
)


class SubWorkMasterService:
    LEDGER_KINDS = ("Income", "Expense", "Misc.")

    def __init__(self):
        self._entry_repo = OthersIncomeExpenseRepository()
        self._work_repo = WorkMasterRepository()
        self._group_name_cache: dict[int, str] | None = None

    def _ensure(self) -> None:
        self._entry_repo.ensure_schema()
        self._seed_misc_defaults()
        self._ensure_unique_name_sub()

    def _group_name_map(self) -> dict[int, str]:
        if self._group_name_cache is not None:
            return self._group_name_cache
        mapping: dict[int, str] = {}
        try:
            from app.services.chart_group_service import ChartGroupService

            for item in ChartGroupService().list_active_for_dropdown():
                try:
                    gid = int(item.get("group_id") or 0)
                except (TypeError, ValueError):
                    continue
                if gid:
                    mapping[gid] = item.get("group_name") or item.get("label") or ""
        except Exception:
            mapping = {}
        self._group_name_cache = mapping
        return mapping

    def _seed_misc_defaults(self) -> None:
        seeds = (
            ("NSDL", "New-Pan"),
            ("New Pan application", "New-Pan"),
        )
        for work_type_name, sub_work_type in seeds:
            db.session.execute(
                text(
                    """
                    IF COL_LENGTH(N'dbo.WorkTypeMaster', N'SubWorkType') IS NOT NULL
                       AND NOT EXISTS (
                            SELECT 1 FROM dbo.WorkTypeMaster
                            WHERE WorkTypeName = :wtn AND SubWorkType = :swt
                       )
                        INSERT INTO dbo.WorkTypeMaster (WorkTypeName, SubWorkType, ActiveStatus)
                        VALUES (:wtn, :swt, 1);
                    """
                ),
                {"wtn": work_type_name, "swt": sub_work_type},
            )
        db.session.commit()

    def _ensure_unique_name_sub(self) -> None:
        try:
            db.session.execute(
                text(
                    """
                    IF COL_LENGTH(N'dbo.WorkTypeMaster', N'SubWorkType') IS NOT NULL
                       AND NOT EXISTS (
                            SELECT 1 FROM sys.indexes
                            WHERE name = N'UX_WorkTypeMaster_Name_Sub'
                              AND object_id = OBJECT_ID(N'dbo.WorkTypeMaster')
                       )
                       AND NOT EXISTS (
                            SELECT WorkTypeName, SubWorkType
                            FROM dbo.WorkTypeMaster
                            GROUP BY WorkTypeName, SubWorkType
                            HAVING COUNT(*) > 1
                       )
                        CREATE UNIQUE INDEX UX_WorkTypeMaster_Name_Sub
                            ON dbo.WorkTypeMaster (WorkTypeName, SubWorkType);
                    """
                )
            )
            db.session.commit()
        except Exception:
            db.session.rollback()

    def _normalize_ledger_kind(self, raw: str | None) -> str | None:
        kind = (raw or "").strip()
        if not kind:
            return None
        if kind in self.LEDGER_KINDS:
            return kind
        compact = "".join(kind.split()).lower().rstrip(".")
        if compact == "income":
            return "Income"
        if compact == "expense":
            return "Expense"
        if compact == "misc":
            return "Misc."
        return None

    def _kind_of(self, raw: str | None) -> str | None:
        """Canonical Income / Expense / Misc. from DB or query values (Misc vs Misc., padding)."""
        return self._normalize_ledger_kind(raw)

    def _works_for_kind(self, kind: str) -> list:
        """Match WorkMaster.LedgerKind loosely so Misc / Misc. / padded values all appear."""
        want = self._kind_of(kind)
        if not want:
            return []
        return [
            row
            for row in self._work_repo.list_active()
            if self._kind_of(row.LedgerKind) == want
        ]

    def _work_lookup(self) -> dict[str, WorkMaster]:
        """Map WorkName → WorkMaster (prefer Misc. when duplicate names)."""
        rows = self._work_repo.list_active()
        by_name: dict[str, WorkMaster] = {}
        priority = {"Misc.": 0, "Income": 1, "Expense": 2}
        for row in rows:
            name = (row.WorkName or "").strip()
            if not name:
                continue
            existing = by_name.get(name)
            if existing is None:
                by_name[name] = row
                continue
            if priority.get(self._kind_of(row.LedgerKind) or "", 9) < priority.get(
                self._kind_of(existing.LedgerKind) or "", 9
            ):
                by_name[name] = row
        return by_name

    def _under_group_for_work(self, work: WorkMaster | None) -> tuple[int | None, str | None]:
        if work is None:
            return None, None
        gid = getattr(work, "ChartGroupID", None)
        try:
            gid = int(gid) if gid is not None else None
        except (TypeError, ValueError):
            gid = None
        if not gid:
            return None, None
        name = self._group_name_map().get(gid)
        return gid, name or None

    def _row_dict(self, row: WorkTypeMaster, work_lookup: dict[str, WorkMaster] | None = None) -> dict:
        lookup = work_lookup if work_lookup is not None else self._work_lookup()
        parent = lookup.get((row.WorkTypeName or "").strip())
        chart_group_id, under_group = self._under_group_for_work(parent)
        return {
            "work_type_id": row.WorkTypeID,
            "work_id": parent.WorkID if parent else None,
            "work_type_name": row.WorkTypeName or "",
            "work_name": row.WorkTypeName or "",
            "sub_work_type": row.SubWorkType or "",
            "ledger_kind": self._kind_of(parent.LedgerKind) if parent else "",
            "chart_group_id": chart_group_id,
            "under_group": under_group,
            "active_status": bool(row.ActiveStatus),
        }

    def list_ledger_kinds(self) -> list[str]:
        return list(self.LEDGER_KINDS)

    def _serialize_work(self, row) -> dict:
        chart_group_id, under_group = self._under_group_for_work(row)
        return {
            "work_id": row.WorkID,
            "work_name": row.WorkName,
            "ledger_kind": self._kind_of(row.LedgerKind) or (row.LedgerKind or ""),
            "chart_group_id": chart_group_id,
            "under_group": under_group,
        }

    def list_works_for_ledger(self, ledger_kind: str | None) -> list[dict]:
        """Active WorkMaster rows for a LedgerKind (for cascading dropdown)."""
        self._ensure()
        kind = self._kind_of(ledger_kind)
        if not kind:
            return []
        return [self._serialize_work(row) for row in self._works_for_kind(kind)]

    def list_work_groups(self) -> dict[str, list[dict]]:
        """WorkMaster grouped by LedgerKind for the form/filter."""
        self._ensure()
        groups = {kind: [] for kind in self.LEDGER_KINDS}
        for row in self._work_repo.list_active():
            kind = self._kind_of(row.LedgerKind)
            if not kind:
                continue
            groups[kind].append(self._serialize_work(row))
        return groups

    def list_records(
        self,
        *,
        search: str | None = None,
        ledger_kind: str | None = None,
    ) -> list[dict]:
        self._ensure()
        kind = self._normalize_ledger_kind(ledger_kind)
        lookup = self._work_lookup()
        stmt = (
            select(WorkTypeMaster)
            .where(WorkTypeMaster.ActiveStatus == True)  # noqa: E712
            .order_by(WorkTypeMaster.WorkTypeName, WorkTypeMaster.SubWorkType)
        )
        rows = list(db.session.scalars(stmt).all())
        result = []
        needle = (search or "").strip().lower()
        for row in rows:
            item = self._row_dict(row, lookup)
            if kind and self._kind_of(item["ledger_kind"]) != kind:
                # Keep orphans only when no ledger filter
                continue
            if kind is None and not item["ledger_kind"]:
                # Hide legacy rows not linked to any WorkMaster
                continue
            if needle:
                hay = " ".join(
                    [
                        item["ledger_kind"],
                        item["work_name"],
                        item["sub_work_type"],
                    ]
                ).lower()
                if needle not in hay:
                    continue
            result.append(item)

        kind_order = {k: i for i, k in enumerate(self.LEDGER_KINDS)}
        result.sort(
            key=lambda r: (
                kind_order.get(r["ledger_kind"], 99),
                (r["work_name"] or "").lower(),
                (r["sub_work_type"] or "").lower(),
            )
        )
        return result

    def get_record(self, work_type_id: int) -> dict:
        self._ensure()
        row = db.session.get(WorkTypeMaster, work_type_id)
        if row is None or not row.ActiveStatus:
            raise ValueError("Sub work not found.")
        return self._row_dict(row)

    def _resolve_parent_work(self, payload: dict) -> WorkMaster:
        work_id_raw = payload.get("work_id") or payload.get("WorkID")
        ledger_kind = self._normalize_ledger_kind(
            payload.get("ledger_kind") or payload.get("LedgerKind")
        )
        work_name = (
            payload.get("work_name")
            or payload.get("work_type_name")
            or payload.get("WorkTypeName")
            or payload.get("WorkName")
            or ""
        ).strip()

        parent = None
        if work_id_raw not in (None, ""):
            try:
                parent = self._work_repo.get_by_id(int(work_id_raw))
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid Work selected.") from exc
            if parent is None or not parent.ActiveStatus:
                raise ValueError("Selected Work not found in Work Master.")
        elif work_name and ledger_kind:
            parent = self._work_repo.find_by_name_kind(work_name, ledger_kind)
            if parent is None or not parent.ActiveStatus:
                raise ValueError(
                    f"Work '{work_name}' not found under Ledger Kind '{ledger_kind}'. "
                    "Add it first in Masters → Income/Expense."
                )
        elif work_name:
            matches = [
                w
                for w in self._work_repo.list_active()
                if (w.WorkName or "").strip() == work_name
            ]
            if not matches:
                raise ValueError(
                    f"Work '{work_name}' not found in Work Master. "
                    "Add it first in Masters → Income/Expense."
                )
            if len(matches) > 1 and not ledger_kind:
                raise ValueError("Select Ledger Kind (Income / Expense / Misc.).")
            parent = matches[0]
            if ledger_kind:
                parent = next(
                    (w for w in matches if self._kind_of(w.LedgerKind) == ledger_kind),
                    None,
                )
                if parent is None:
                    raise ValueError(
                        f"Work '{work_name}' not found under Ledger Kind '{ledger_kind}'."
                    )
        else:
            raise ValueError("Select Ledger Kind and Work from Work Master.")

        parent_kind = self._kind_of(parent.LedgerKind)
        if ledger_kind and parent_kind != ledger_kind:
            raise ValueError(
                f"Work '{parent.WorkName}' belongs to '{parent_kind}', not '{ledger_kind}'."
            )
        return parent

    def _find_by_name_sub(
        self,
        work_type_name: str,
        sub_work_type: str,
        *,
        exclude_id: int | None = None,
    ) -> WorkTypeMaster | None:
        name = (work_type_name or "").strip()
        sub = (sub_work_type or "").strip()
        if not name or not sub:
            return None
        stmt = select(WorkTypeMaster).where(
            func.lower(WorkTypeMaster.WorkTypeName) == name.lower(),
            func.lower(WorkTypeMaster.SubWorkType) == sub.lower(),
        )
        if exclude_id is not None:
            stmt = stmt.where(WorkTypeMaster.WorkTypeID != exclude_id)
        return db.session.scalars(stmt).first()

    def create_record(self, payload: dict) -> dict:
        self._ensure()
        parent = self._resolve_parent_work(payload)
        sub_work_type = (payload.get("sub_work_type") or payload.get("SubWorkType") or "").strip()
        if not sub_work_type:
            raise ValueError("Sub Work Type is required (e.g. New-Pan).")

        work_type_name = (parent.WorkName or "").strip()
        existing = self._find_by_name_sub(work_type_name, sub_work_type)
        if existing and existing.ActiveStatus:
            raise ValueError(
                f"'{sub_work_type}' already exists under '{work_type_name}' ({parent.LedgerKind})."
            )

        def _write() -> dict:
            if existing:
                existing.ActiveStatus = True
                db.session.flush()
                return self._row_dict(existing)
            row = WorkTypeMaster(
                WorkTypeName=work_type_name,
                SubWorkType=sub_work_type,
                ActiveStatus=True,
            )
            db.session.add(row)
            db.session.flush()
            return self._row_dict(row)

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise ValueError(
                f"'{sub_work_type}' already exists under '{work_type_name}'."
            ) from exc

    def update_record(self, work_type_id: int, payload: dict) -> dict:
        self._ensure()
        row = db.session.get(WorkTypeMaster, work_type_id)
        if row is None or not row.ActiveStatus:
            raise ValueError("Sub work not found.")

        parent = self._resolve_parent_work(
            {
                **payload,
                "work_name": payload.get("work_name")
                or payload.get("work_type_name")
                or row.WorkTypeName,
                "ledger_kind": payload.get("ledger_kind") or payload.get("LedgerKind"),
            }
        )
        sub_work_type = (
            payload.get("sub_work_type") or payload.get("SubWorkType") or row.SubWorkType
        ).strip()
        if not sub_work_type:
            raise ValueError("Sub Work Type is required.")

        work_type_name = (parent.WorkName or "").strip()
        other = self._find_by_name_sub(work_type_name, sub_work_type, exclude_id=work_type_id)
        if other and other.ActiveStatus:
            raise ValueError(
                f"'{sub_work_type}' already exists under '{work_type_name}' ({parent.LedgerKind})."
            )

        def _write() -> dict:
            row.WorkTypeName = work_type_name
            row.SubWorkType = sub_work_type
            db.session.flush()
            return self._row_dict(row)

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise ValueError(
                f"'{sub_work_type}' already exists under '{work_type_name}'."
            ) from exc

    def delete_record(self, work_type_id: int) -> str:
        self._ensure()
        row = db.session.get(WorkTypeMaster, work_type_id)
        if row is None or not row.ActiveStatus:
            raise ValueError("Sub work not found.")
        parent_name = (row.WorkTypeName or "").strip()
        sub_name = (row.SubWorkType or "").strip()
        label = f"{parent_name} / {sub_name}".strip(" /") or "Sub work"
        assert_master_unused(
            table="WorkTypeMaster",
            pk_column="WorkTypeID",
            pk_value=work_type_id,
            display_name=label,
            extra_checks=[
                {
                    "table": "JTCSDailyTransaction",
                    "where": (
                        "LTRIM(RTRIM(SubWorkType)) = :sub "
                        "AND LTRIM(RTRIM(WorkType)) = :parent"
                    ),
                    "params": {"sub": sub_name, "parent": parent_name},
                    "label": "Daily Transaction",
                },
            ],
        )

        def _write() -> str:
            row.ActiveStatus = False
            db.session.flush()
            return "Sub work deleted successfully."

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise_if_integrity_in_use(exc, label)
            raise
