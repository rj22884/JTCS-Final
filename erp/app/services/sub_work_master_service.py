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
    # Income / Expense heads belong only in Category Master.
    # Sub Work Master is Misc. (e.g. NSDL → New-Pan) only, linked to Item Master.
    LEDGER_KINDS = ("Misc.",)
    ALLOWED_KINDS = ("Misc.",)

    def __init__(self):
        self._entry_repo = OthersIncomeExpenseRepository()
        self._work_repo = WorkMasterRepository()
        self._group_name_cache: dict[int, str] | None = None

    def _ensure(self) -> None:
        self._entry_repo.ensure_schema()
        self._ensure_item_link_column()
        self._seed_misc_defaults()
        self._ensure_unique_name_sub()
        self._backfill_linked_items()

    def ensure_item_links(self) -> None:
        """Public entry: Item Master list also syncs Sub Work → Item rows."""
        self._ensure_item_link_column()
        self._backfill_linked_items()

    def _ensure_item_link_column(self) -> None:
        try:
            db.session.execute(
                text(
                    """
                    IF COL_LENGTH(N'dbo.WorkTypeMaster', N'ItemID') IS NULL
                        ALTER TABLE dbo.WorkTypeMaster ADD ItemID INT NULL;
                    """
                )
            )
            db.session.execute(
                text(
                    """
                    IF COL_LENGTH(N'dbo.WorkTypeMaster', N'ItemID') IS NOT NULL
                       AND OBJECT_ID(N'dbo.ItemMaster', N'U') IS NOT NULL
                       AND NOT EXISTS (
                            SELECT 1 FROM sys.foreign_keys
                            WHERE name = N'FK_WorkTypeMaster_Item'
                       )
                        ALTER TABLE dbo.WorkTypeMaster
                        ADD CONSTRAINT FK_WorkTypeMaster_Item
                            FOREIGN KEY (ItemID) REFERENCES dbo.ItemMaster (ItemID);
                    """
                )
            )
            db.session.commit()
        except Exception:
            db.session.rollback()

    def _group_name_map(self) -> dict[int, str]:
        if self._group_name_cache is not None:
            return self._group_name_cache
        mapping: dict[int, str] = {}
        try:
            from app.services.chart_group_service import ChartGroupService

            svc = ChartGroupService()
            for item in svc.list_active_for_dropdown() or []:
                try:
                    gid = int(item.get("group_id") or 0)
                except (TypeError, ValueError):
                    continue
                if gid:
                    mapping[gid] = (
                        item.get("group_name") or item.get("label") or mapping.get(gid) or ""
                    )
            # Include inactive/all groups so inherited Category Master values still resolve.
            for item in svc.list_records() or []:
                try:
                    gid = int(item.get("group_id") or 0)
                except (TypeError, ValueError):
                    continue
                if gid and gid not in mapping:
                    mapping[gid] = item.get("group_name") or item.get("label") or ""
        except Exception:
            pass
        self._group_name_cache = mapping
        return mapping

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
        name = (self._group_name_map().get(gid) or "").strip()
        return gid, name or None

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
        """Map WorkName → WorkMaster (prefer active, then Misc. on duplicate names)."""
        rows = self._work_repo.list_records()
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
            if bool(row.ActiveStatus) and not bool(existing.ActiveStatus):
                by_name[name] = row
                continue
            if bool(row.ActiveStatus) == bool(existing.ActiveStatus) and priority.get(
                self._kind_of(row.LedgerKind) or "", 9
            ) < priority.get(self._kind_of(existing.LedgerKind) or "", 9):
                by_name[name] = row
        return by_name

    def _work_only_dict(self, work: WorkMaster) -> dict:
        chart_group_id, under_group = self._under_group_for_work(work)
        return {
            "work_type_id": None,
            "work_id": work.WorkID,
            "work_type_name": work.WorkName or "",
            "work_name": work.WorkName or "",
            "sub_work_type": "",
            "ledger_kind": self._kind_of(work.LedgerKind) or (work.LedgerKind or ""),
            "chart_group_id": chart_group_id,
            "under_group": under_group,
            "active_status": bool(work.ActiveStatus),
            "is_work_only": True,
        }

    def _row_dict(self, row: WorkTypeMaster, work_lookup: dict[str, WorkMaster] | None = None) -> dict:
        lookup = work_lookup if work_lookup is not None else self._work_lookup()
        parent = lookup.get((row.WorkTypeName or "").strip())
        chart_group_id, under_group = self._under_group_for_work(parent)
        item_id = getattr(row, "ItemID", None)
        try:
            item_id = int(item_id) if item_id is not None else None
        except (TypeError, ValueError):
            item_id = None
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
            "item_id": item_id,
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
        if kind not in self.ALLOWED_KINDS:
            return []
        return [self._serialize_work(row) for row in self._works_for_kind(kind)]

    def list_work_groups(self) -> dict[str, list[dict]]:
        """WorkMaster grouped by LedgerKind for the form/filter (Misc. only)."""
        self._ensure()
        groups = {kind: [] for kind in self.LEDGER_KINDS}
        for row in self._work_repo.list_active():
            kind = self._kind_of(row.LedgerKind)
            if kind not in self.ALLOWED_KINDS:
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
            item_kind = self._kind_of(item["ledger_kind"])
            if item_kind not in self.ALLOWED_KINDS:
                continue
            if kind and item_kind != kind:
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

        covered = {
            (
                self._kind_of(item.get("ledger_kind")) or "",
                (item.get("work_name") or "").strip().lower(),
            )
            for item in result
        }
        for work in self._work_repo.list_records():
            work_kind = self._kind_of(work.LedgerKind)
            if work_kind not in self.ALLOWED_KINDS:
                continue
            if kind and work_kind != kind:
                continue
            name = (work.WorkName or "").strip()
            if not name:
                continue
            if (work_kind, name.lower()) in covered:
                continue
            item = self._work_only_dict(work)
            if needle:
                hay = " ".join(
                    [item["ledger_kind"], item["work_name"], item["sub_work_type"]]
                ).lower()
                if needle not in hay:
                    continue
            result.append(item)
            covered.add((work_kind, name.lower()))

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
        if parent_kind not in self.ALLOWED_KINDS:
            raise ValueError(
                "Sub Work Master only allows Misc. works. "
                "Income / Expense heads belong in Masters → Category Master."
            )
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

    def _find_by_sub_work_type(
        self,
        sub_work_type: str,
        *,
        exclude_id: int | None = None,
        active_only: bool = True,
    ) -> WorkTypeMaster | None:
        """Sub Work Type must be unique across all works (case-insensitive)."""
        sub = (sub_work_type or "").strip()
        if not sub:
            return None
        stmt = select(WorkTypeMaster).where(
            func.lower(WorkTypeMaster.SubWorkType) == sub.lower()
        )
        if active_only:
            stmt = stmt.where(WorkTypeMaster.ActiveStatus == True)  # noqa: E712
        if exclude_id is not None:
            stmt = stmt.where(WorkTypeMaster.WorkTypeID != exclude_id)
        return db.session.scalars(stmt).first()

    def _assert_sub_work_type_unique(
        self,
        sub_work_type: str,
        *,
        exclude_id: int | None = None,
    ) -> None:
        other = self._find_by_sub_work_type(sub_work_type, exclude_id=exclude_id, active_only=True)
        if other is None:
            return
        parent = (other.WorkTypeName or "").strip() or "another work"
        raise ValueError(
            f"Sub Work Type '{sub_work_type}' already exists under '{parent}'. "
            "Duplicate Sub Work Type is not allowed."
        )

    @staticmethod
    def _suggest_item_code(work_name: str, sub_work_type: str) -> str:
        import re

        from app.repositories.item_master_repository import ItemMasterRepository

        raw = f"{work_name}-{sub_work_type}".upper()
        base = re.sub(r"[^A-Z0-9]+", "-", raw).strip("-")[:36] or "SW-ITEM"
        repo = ItemMasterRepository()
        if not repo.find_by_code(base):
            return base
        for idx in range(2, 1000):
            suffix = f"-{idx}"
            candidate = (base[: 40 - len(suffix)] + suffix)[:40]
            if not repo.find_by_code(candidate):
                return candidate
        return (base[:36] + "-X")[:40]

    def _default_item_chart_group_id(self, preferred_id: int | None = None) -> int:
        from app.services.chart_group_service import ChartGroupService
        from app.services.dynamic_master_fields import DynamicMasterFieldService

        groups = ChartGroupService().list_active_for_dropdown() or []
        dyn = DynamicMasterFieldService()
        try:
            dyn.annotate_groups(groups)
        except Exception:
            pass

        if preferred_id:
            for g in groups:
                try:
                    if int(g.get("group_id") or 0) == int(preferred_id):
                        return int(preferred_id)
                except (TypeError, ValueError):
                    pass

        # Prefer a simple income/service-style group (not fixed asset / investment).
        for g in groups:
            profile = (g.get("dyn_profile") or "").strip().lower()
            if profile in {"fixed_assets", "investments"}:
                continue
            try:
                gid = int(g.get("group_id") or 0)
            except (TypeError, ValueError):
                continue
            if gid > 0:
                return gid

        for g in groups:
            try:
                gid = int(g.get("group_id") or 0)
            except (TypeError, ValueError):
                continue
            if gid > 0:
                return gid
        raise ValueError(
            "Cannot create linked Item: add at least one active Chart of Account Group in Chart of Group Master."
        )

    def _upsert_linked_item(
        self,
        *,
        sub_work_type: str,
        work_name: str,
        preferred_chart_group_id: int | None = None,
        existing_item_id: int | None = None,
    ) -> dict:
        """Create/update Item Master silently for invoice use — no Sub Work UI fields."""
        from app.models.gst_billing import ItemMaster
        from app.services.item_master_service import ItemMasterService

        item_svc = ItemMasterService()
        item_name = (sub_work_type or "").strip()
        if not item_name:
            raise ValueError("Sub Work Type is required.")

        if existing_item_id:
            try:
                existing = item_svc.get_record(existing_item_id)
            except ValueError:
                existing = None
            if existing:
                sync = dict(existing)
                sync["item_name"] = item_name[:200]
                sync["is_active"] = "1"
                # Keep code / rates / HSN as already set in Item Master.
                return item_svc.update_record(existing_item_id, sync)

        # Reuse an existing Item with the same name (case-insensitive) when possible.
        matched = db.session.scalars(
            select(ItemMaster).where(func.lower(ItemMaster.ItemName) == item_name.lower())
        ).first()
        if matched is not None:
            sync = item_svc._serialize(matched)
            sync["item_name"] = item_name[:200]
            sync["is_active"] = "1"
            return item_svc.update_record(int(matched.ItemID), sync)

        item_code = self._suggest_item_code(work_name, item_name)
        chart_group_id = self._default_item_chart_group_id(preferred_chart_group_id)
        return item_svc.create_record(
            {
                "item_code": item_code,
                "item_name": item_name[:200],
                "hsn_sac": "9983",
                "hsn_sac_type": "SAC",
                "unit": "NOS",
                "chart_group_id": chart_group_id,
                "default_rate": "0",
                "gst_applicable": "1",
                "gst_rate_percent": "18",
                "opening_qty": "0",
                "opening_rate": "0",
                "opening_balance_date": "",
                "order_no": "100",
                "description": f"Sub Work: {work_name} / {item_name}"[:500],
                "is_active": "1",
            }
        )

    def _unlinked_sub_work_ids(self) -> list[int]:
        """Active Misc. Sub Works that still need an ItemMaster link."""
        from app.models.gst_billing import ItemMaster

        lookup = self._work_lookup()
        rows = list(
            db.session.scalars(
                select(WorkTypeMaster).where(
                    WorkTypeMaster.ActiveStatus == True,  # noqa: E712
                )
            ).all()
        )
        need: list[int] = []
        for row in rows:
            sub = (row.SubWorkType or "").strip()
            if not sub:
                continue
            parent = lookup.get((row.WorkTypeName or "").strip())
            kind = self._kind_of(parent.LedgerKind) if parent else None
            if kind not in self.ALLOWED_KINDS:
                continue
            raw_id = getattr(row, "ItemID", None)
            try:
                item_id = int(raw_id) if raw_id not in (None, "") else None
            except (TypeError, ValueError):
                item_id = None
            if item_id:
                linked = db.session.get(ItemMaster, item_id)
                if linked is not None:
                    continue
            need.append(int(row.WorkTypeID))
        return need

    def _link_one_sub_work_item(self, work_type_id: int) -> None:
        """Create/link ItemMaster for one Sub Work and store ItemID (fresh session each call)."""
        row = db.session.get(WorkTypeMaster, work_type_id)
        if row is None or not row.ActiveStatus:
            return
        sub = (row.SubWorkType or "").strip()
        if not sub:
            return
        work_name = (row.WorkTypeName or "").strip()
        lookup = self._work_lookup()
        parent = lookup.get(work_name)
        preferred_chart = None
        if parent is not None:
            try:
                preferred_chart = int(getattr(parent, "ChartGroupID", None) or 0) or None
            except (TypeError, ValueError):
                preferred_chart = None

        existing_item_id = None
        raw_id = getattr(row, "ItemID", None)
        try:
            existing_item_id = int(raw_id) if raw_id not in (None, "") else None
        except (TypeError, ValueError):
            existing_item_id = None

        item = self._upsert_linked_item(
            sub_work_type=sub,
            work_name=work_name,
            preferred_chart_group_id=preferred_chart,
            existing_item_id=existing_item_id,
        )
        item_id = int(item["item_id"])

        def _write() -> None:
            fresh = db.session.get(WorkTypeMaster, work_type_id)
            if fresh is None:
                return
            fresh.ItemID = item_id
            db.session.flush()

        persist(_write)

    def _backfill_linked_items(self) -> None:
        """One-time-style sync: every Misc. Sub Work gets a row in Item Master."""
        try:
            ids = self._unlinked_sub_work_ids()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            return
        if not ids:
            return
        for work_type_id in ids:
            try:
                self._link_one_sub_work_item(work_type_id)
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass

    def create_record(self, payload: dict) -> dict:
        self._ensure()
        parent = self._resolve_parent_work(payload)
        sub_work_type = (payload.get("sub_work_type") or payload.get("SubWorkType") or "").strip()
        if not sub_work_type:
            # Allow Item Name to drive Sub Work Type
            sub_work_type = (payload.get("item_name") or payload.get("ItemName") or "").strip()
        if not sub_work_type:
            raise ValueError("Sub Work Type is required (e.g. New-Pan).")

        work_type_name = (parent.WorkName or "").strip()
        self._assert_sub_work_type_unique(sub_work_type)
        existing = self._find_by_name_sub(work_type_name, sub_work_type)
        if existing and existing.ActiveStatus:
            raise ValueError(
                f"Sub Work Type '{sub_work_type}' already exists under '{work_type_name}'. "
                "Duplicate Sub Work Type is not allowed."
            )
        # Prefer reactivating the same Sub Work Type row if it was soft-deleted elsewhere.
        if existing is None:
            existing = self._find_by_sub_work_type(
                sub_work_type, active_only=False
            )
            if existing and existing.ActiveStatus:
                existing = None

        preferred_chart = None
        try:
            preferred_chart = int(getattr(parent, "ChartGroupID", None) or 0) or None
        except (TypeError, ValueError):
            preferred_chart = None

        existing_id = int(existing.WorkTypeID) if existing is not None else None
        existing_item_id = None
        if existing is not None and getattr(existing, "ItemID", None):
            try:
                existing_item_id = int(existing.ItemID)
            except (TypeError, ValueError):
                existing_item_id = None

        item = self._upsert_linked_item(
            sub_work_type=sub_work_type,
            work_name=work_type_name,
            preferred_chart_group_id=preferred_chart,
            existing_item_id=existing_item_id,
        )
        item_id = int(item["item_id"])

        def _write() -> dict:
            if existing_id:
                fresh = db.session.get(WorkTypeMaster, existing_id)
                if fresh is not None:
                    fresh.ActiveStatus = True
                    fresh.ItemID = item_id
                    fresh.SubWorkType = sub_work_type
                    fresh.WorkTypeName = work_type_name
                    db.session.flush()
                    return self._row_dict(fresh)
            row = WorkTypeMaster(
                WorkTypeName=work_type_name,
                SubWorkType=sub_work_type,
                ItemID=item_id,
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
            payload.get("sub_work_type")
            or payload.get("SubWorkType")
            or payload.get("item_name")
            or payload.get("ItemName")
            or row.SubWorkType
        ).strip()
        if not sub_work_type:
            raise ValueError("Sub Work Type is required.")

        work_type_name = (parent.WorkName or "").strip()
        self._assert_sub_work_type_unique(sub_work_type, exclude_id=work_type_id)
        other = self._find_by_name_sub(work_type_name, sub_work_type, exclude_id=work_type_id)
        if other and other.ActiveStatus:
            raise ValueError(
                f"Sub Work Type '{sub_work_type}' already exists under '{work_type_name}'. "
                "Duplicate Sub Work Type is not allowed."
            )

        existing_item_id = None
        raw_item_id = getattr(row, "ItemID", None)
        try:
            existing_item_id = int(raw_item_id) if raw_item_id not in (None, "") else None
        except (TypeError, ValueError):
            existing_item_id = None

        preferred_chart = None
        try:
            preferred_chart = int(getattr(parent, "ChartGroupID", None) or 0) or None
        except (TypeError, ValueError):
            preferred_chart = None

        item = self._upsert_linked_item(
            sub_work_type=sub_work_type,
            work_name=work_type_name,
            preferred_chart_group_id=preferred_chart,
            existing_item_id=existing_item_id,
        )
        item_id = int(item["item_id"])

        def _write() -> dict:
            fresh = db.session.get(WorkTypeMaster, work_type_id)
            if fresh is None or not fresh.ActiveStatus:
                raise ValueError("Sub work not found.")
            fresh.WorkTypeName = work_type_name
            fresh.SubWorkType = sub_work_type
            fresh.ItemID = item_id
            db.session.flush()
            return self._row_dict(fresh)

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
        linked_item_id = getattr(row, "ItemID", None)

        def _write() -> str:
            row.ActiveStatus = False
            db.session.flush()
            return "Sub work deleted successfully."

        try:
            message = persist(_write)
        except IntegrityError as exc:
            raise_if_integrity_in_use(exc, label)
            raise

        if linked_item_id:
            try:
                from app.services.item_master_service import ItemMasterService

                item_svc = ItemMasterService()
                existing_item = item_svc.get_record(int(linked_item_id))
                existing_item["is_active"] = "0"
                item_svc.update_record(int(linked_item_id), existing_item)
            except Exception:
                pass
        return message
