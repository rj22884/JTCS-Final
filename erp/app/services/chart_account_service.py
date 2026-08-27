from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.repositories.chart_account_repository import ChartAccountRepository
from app.repositories.chart_group_repository import ChartGroupRepository
from app.utils.db_session import persist
from app.utils.opening_balance import default_dr_cr_for_under_type, parse_opening_balance_fields
from app.utils.master_delete_guard import (
    assert_master_unused,
    raise_if_integrity_in_use,
)

MAX_GROUPS = 5


class ChartAccountService:
    def __init__(
        self,
        repository: ChartAccountRepository | None = None,
        group_repository: ChartGroupRepository | None = None,
    ):
        self.repo = repository or ChartAccountRepository()
        self.group_repo = group_repository or ChartGroupRepository()

    @staticmethod
    def _parse_id_list(raw) -> list[int]:
        if raw is None:
            return []
        if isinstance(raw, str):
            parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
            values = parts
        elif isinstance(raw, (list, tuple, set)):
            values = list(raw)
        else:
            values = [raw]
        ids: list[int] = []
        seen: set[int] = set()
        for value in values:
            try:
                gid = int(value)
            except (TypeError, ValueError):
                continue
            if gid <= 0 or gid in seen:
                continue
            seen.add(gid)
            ids.append(gid)
        return ids

    @staticmethod
    def _ids_from_csv(raw) -> list[int]:
        if not raw:
            return []
        return ChartAccountService._parse_id_list(str(raw))

    def _groups_payload(self, group_ids: list[int], *, names: str = "", unders: str = "") -> dict:
        primary = group_ids[0] if group_ids else None
        under_list = [u.strip() for u in (unders or "").split(",") if u.strip()]
        primary_under = under_list[0] if under_list else ""
        if not names and group_ids:
            name_parts = []
            under_parts = []
            for gid in group_ids:
                g = self.group_repo.get_by_id(gid)
                if g:
                    name_parts.append(g.GroupName or "")
                    under_parts.append(g.UnderType or "")
            names = ", ".join(p for p in name_parts if p)
            unders = ", ".join(p for p in under_parts if p)
            primary_under = under_parts[0] if under_parts else ""
        return {
            "group_id": primary,
            "group_ids": group_ids,
            "group_name": names or "",
            "under_type": primary_under,
            "under_types": unders or primary_under,
        }

    def _groups_from_row_dict(self, row: dict) -> dict:
        ids = self._ids_from_csv(row.get("GroupIDs"))
        if not ids and row.get("GroupID") is not None:
            ids = [int(row["GroupID"])]
        return self._groups_payload(
            ids,
            names=(row.get("GroupNames") or row.get("GroupName") or "") or "",
            unders=(row.get("UnderTypes") or row.get("UnderType") or "") or "",
        )

    def _groups_for_account(self, account_id: int | None, fallback_group_id: int | None = None) -> dict:
        if account_id:
            links = self.repo.list_group_links(account_id)
            if links:
                ids = [int(l["GroupID"]) for l in links]
                names = ", ".join((l.get("GroupName") or "") for l in links)
                unders = ", ".join((l.get("UnderType") or "") for l in links)
                return self._groups_payload(ids, names=names, unders=unders)
        if fallback_group_id:
            return self._groups_payload([int(fallback_group_id)])
        return self._groups_payload([])

    def _ob_payload(self, payload: dict, *, under_type: str | None = None) -> dict:
        fields = parse_opening_balance_fields(payload)
        if not fields.get("OpeningBalanceDrCr"):
            fields["OpeningBalanceDrCr"] = default_dr_cr_for_under_type(under_type)
        return fields

    @staticmethod
    def _ob_serialize(row_or_dict) -> dict:
        if isinstance(row_or_dict, dict):
            ob = row_or_dict.get("OpeningBalance")
            ob_date = row_or_dict.get("OpeningBalanceDate")
            ob_dr_cr = row_or_dict.get("OpeningBalanceDrCr")
            under = row_or_dict.get("UnderType") or row_or_dict.get("under_type") or ""
        else:
            ob = getattr(row_or_dict, "OpeningBalance", None)
            ob_date = getattr(row_or_dict, "OpeningBalanceDate", None)
            ob_dr_cr = getattr(row_or_dict, "OpeningBalanceDrCr", None)
            under = ""
        return {
            "opening_balance": str(ob) if ob is not None else "",
            "opening_balance_date": ob_date.isoformat() if ob_date else "",
            "opening_balance_dr_cr": ob_dr_cr
            or default_dr_cr_for_under_type(under)
            or "Dr",
        }

    def _serialize_manual(self, row) -> dict:
        groups = self._groups_for_account(row.AccountID, row.GroupID)
        return {
            "row_key": f"a-{row.AccountID}",
            "source": "manual",
            "account_id": row.AccountID,
            "customer_id": None,
            "work_id": None,
            "ledger_kind": "",
            "account_name": row.AccountName or "",
            **groups,
            **self._ob_serialize(row),
            "is_active": bool(row.IsActive),
            "name_editable": True,
            "created_date": row.CreatedDate.isoformat() if row.CreatedDate else "",
            "updated_date": row.UpdatedDate.isoformat() if row.UpdatedDate else "",
        }

    def _serialize_customer(self, row: dict) -> dict:
        account_id = row.get("AccountID")
        created = row.get("AccountCreatedDate")
        updated = row.get("AccountUpdatedDate")
        is_active = row.get("AccountIsActive")
        groups = self._groups_from_row_dict(row)
        return {
            "row_key": f"c-{row.get('CustomerID')}",
            "source": "customer",
            "account_id": int(account_id) if account_id is not None else None,
            "customer_id": int(row["CustomerID"]),
            "work_id": None,
            "ledger_kind": "",
            "account_name": (row.get("CustomerName") or "").strip(),
            **groups,
            **self._ob_serialize(row),
            "is_active": True if is_active is None else bool(is_active),
            "name_editable": False,
            "created_date": created.isoformat() if created else "",
            "updated_date": updated.isoformat() if updated else "",
        }

    def _serialize_work(self, row: dict) -> dict:
        account_id = row.get("AccountID")
        created = row.get("AccountCreatedDate")
        updated = row.get("AccountUpdatedDate")
        is_active = row.get("AccountIsActive")
        groups = self._groups_from_row_dict(row)
        return {
            "row_key": f"w-{row.get('WorkID')}",
            "source": "work",
            "account_id": int(account_id) if account_id is not None else None,
            "customer_id": None,
            "work_id": int(row["WorkID"]),
            "ledger_kind": (row.get("LedgerKind") or "").strip(),
            "account_name": (row.get("WorkName") or "").strip(),
            **groups,
            **self._ob_serialize(row),
            "is_active": True if is_active is None else bool(is_active),
            "name_editable": False,
            "created_date": created.isoformat() if created else "",
            "updated_date": updated.isoformat() if updated else "",
        }

    def list_records(self, *, search: str | None = None, active_only: bool = False) -> list[dict]:
        customers = [
            self._serialize_customer(row)
            for row in self.repo.list_customer_ledger_rows(search=search)
        ]
        works = [
            self._serialize_work(row)
            for row in self.repo.list_work_ledger_rows(search=search)
        ]
        manuals = [
            self._serialize_manual(row)
            for row in self.repo.list_manual_accounts(search=search, active_only=active_only)
        ]
        if active_only:
            customers = [r for r in customers if r["is_active"]]
            works = [r for r in works if r["is_active"]]
        combined = customers + works + manuals
        combined.sort(key=lambda r: (r.get("account_name") or "").lower())
        return combined

    def _linked_record_from_row(self, row) -> dict:
        groups = self._groups_for_account(row.AccountID, row.GroupID)
        if row.CustomerID:
            name = self.repo.get_customer_name(row.CustomerID) or row.AccountName
            return {
                "row_key": f"c-{row.CustomerID}",
                "source": "customer",
                "account_id": row.AccountID,
                "customer_id": row.CustomerID,
                "work_id": None,
                "ledger_kind": "",
                "account_name": name,
                **groups,
                "is_active": bool(row.IsActive),
                "name_editable": False,
                "created_date": row.CreatedDate.isoformat() if row.CreatedDate else "",
                "updated_date": row.UpdatedDate.isoformat() if row.UpdatedDate else "",
            }
        if row.WorkID:
            info = self.repo.get_work_info(row.WorkID) or {}
            return {
                "row_key": f"w-{row.WorkID}",
                "source": "work",
                "account_id": row.AccountID,
                "customer_id": None,
                "work_id": row.WorkID,
                "ledger_kind": info.get("ledger_kind") or "",
                "account_name": info.get("work_name") or row.AccountName or "",
                **groups,
                "is_active": bool(row.IsActive),
                "name_editable": False,
                "created_date": row.CreatedDate.isoformat() if row.CreatedDate else "",
                "updated_date": row.UpdatedDate.isoformat() if row.UpdatedDate else "",
            }
        return self._serialize_manual(row)

    def get_record(self, account_id: int) -> dict:
        row = self.repo.get_by_id(account_id)
        if row is None:
            raise ValueError("Account not found.")
        return self._linked_record_from_row(row)

    def get_customer_record(self, customer_id: int) -> dict:
        name = self.repo.get_customer_name(customer_id)
        if not name:
            raise ValueError("Customer not found or inactive.")
        existing = self.repo.get_by_customer_id(customer_id)
        if existing is None:
            return {
                "row_key": f"c-{customer_id}",
                "source": "customer",
                "account_id": None,
                "customer_id": customer_id,
                "work_id": None,
                "ledger_kind": "",
                "account_name": name,
                **self._groups_payload([]),
                "is_active": True,
                "name_editable": False,
                "created_date": "",
                "updated_date": "",
            }
        return self.get_record(existing.AccountID)

    def get_work_record(self, work_id: int) -> dict:
        info = self.repo.get_work_info(work_id)
        if not info or not info.get("work_name"):
            raise ValueError("Income/Expense work type not found or inactive.")
        existing = self.repo.get_by_work_id(work_id)
        if existing is None:
            return {
                "row_key": f"w-{work_id}",
                "source": "work",
                "account_id": None,
                "customer_id": None,
                "work_id": work_id,
                "ledger_kind": info.get("ledger_kind") or "",
                "account_name": info["work_name"],
                **self._groups_payload([]),
                "is_active": True,
                "name_editable": False,
                "created_date": "",
                "updated_date": "",
            }
        return self.get_record(existing.AccountID)

    def _parse_groups(self, payload: dict) -> list[int]:
        raw = payload.get("group_ids")
        if raw is None:
            raw = payload.get("GroupIDs")
        ids = self._parse_id_list(raw)
        if not ids:
            # Backward compat: single group_id
            single = payload.get("group_id") if "group_id" in payload else payload.get("GroupID")
            ids = self._parse_id_list([single] if single not in (None, "") else [])
        if not ids:
            raise ValueError("Select at least one group.")
        if len(ids) > MAX_GROUPS:
            raise ValueError(f"Maximum {MAX_GROUPS} groups allowed (Sale / Purchase / Income / Expense / Contra).")
        for gid in ids:
            group = self.group_repo.get_by_id(gid)
            if group is None or not group.IsActive:
                raise ValueError("One or more selected groups are invalid or inactive.")
        return ids

    def _unique_account_name(
        self,
        preferred: str,
        *,
        exclude_account_id: int | None = None,
        owner_customer_id: int | None = None,
        owner_work_id: int | None = None,
        fallback_suffix: str = "",
    ) -> str:
        name = preferred[:200]
        clash = self.repo.find_by_name(name, exclude_id=exclude_account_id)
        if clash is None:
            return name
        if owner_customer_id and clash.CustomerID == owner_customer_id:
            return name
        if owner_work_id and clash.WorkID == owner_work_id:
            return name
        alt = f"{preferred} {fallback_suffix}".strip()[:200]
        if not alt or alt == name:
            alt = f"{preferred} #{owner_work_id or owner_customer_id or ''}"[:200]
        clash2 = self.repo.find_by_name(alt, exclude_id=exclude_account_id)
        if clash2 is None:
            return alt
        raise ValueError(
            f"Account Name '{preferred}' already exists. Rename the other chart account first."
        )

    def _apply_groups(self, account_id: int, group_ids: list[int]) -> None:
        self.repo.replace_group_links(account_id, group_ids)
        # Keep legacy GroupID column in sync with first selected group.
        row = self.repo.get_by_id(account_id)
        if row is not None:
            self.repo.update(row, {"GroupID": group_ids[0]})

    def assign_customer_group(self, customer_id: int, payload: dict) -> dict:
        name = self.repo.get_customer_name(customer_id)
        if not name:
            raise ValueError("Customer not found or inactive.")
        group_ids = self._parse_groups(payload)
        primary = self.group_repo.get_by_id(group_ids[0])
        ob_fields = self._ob_payload(
            payload, under_type=primary.UnderType if primary else None
        )
        existing = self.repo.get_by_customer_id(customer_id)
        account_name = self._unique_account_name(
            name,
            exclude_account_id=existing.AccountID if existing else None,
            owner_customer_id=customer_id,
            fallback_suffix="(Customer)",
        )

        def _write() -> dict:
            if existing is None:
                row = self.repo.create(
                    {
                        "AccountName": account_name,
                        "GroupID": group_ids[0],
                        "CustomerID": customer_id,
                        "WorkID": None,
                        **ob_fields,
                        "IsActive": True,
                        "CreatedDate": datetime.utcnow(),
                        "UpdatedDate": None,
                    }
                )
            else:
                row = self.repo.update(
                    existing,
                    {
                        "AccountName": account_name,
                        "GroupID": group_ids[0],
                        **ob_fields,
                        "IsActive": True,
                        "UpdatedDate": datetime.utcnow(),
                    },
                )
            self._apply_groups(row.AccountID, group_ids)
            return self.get_record(row.AccountID)

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise ValueError("Unable to assign group — account name or customer link conflict.") from exc

    def assign_work_group(self, work_id: int, payload: dict) -> dict:
        info = self.repo.get_work_info(work_id)
        if not info or not info.get("work_name"):
            raise ValueError("Income/Expense work type not found or inactive.")
        group_ids = self._parse_groups(payload)
        primary = self.group_repo.get_by_id(group_ids[0])
        ob_fields = self._ob_payload(
            payload, under_type=primary.UnderType if primary else None
        )
        existing = self.repo.get_by_work_id(work_id)
        kind = info.get("ledger_kind") or "IE"
        account_name = self._unique_account_name(
            info["work_name"],
            exclude_account_id=existing.AccountID if existing else None,
            owner_work_id=work_id,
            fallback_suffix=f"({kind})",
        )

        def _write() -> dict:
            if existing is None:
                row = self.repo.create(
                    {
                        "AccountName": account_name,
                        "GroupID": group_ids[0],
                        "CustomerID": None,
                        "WorkID": work_id,
                        **ob_fields,
                        "IsActive": True,
                        "CreatedDate": datetime.utcnow(),
                        "UpdatedDate": None,
                    }
                )
            else:
                row = self.repo.update(
                    existing,
                    {
                        "AccountName": account_name,
                        "GroupID": group_ids[0],
                        **ob_fields,
                        "IsActive": True,
                        "UpdatedDate": datetime.utcnow(),
                    },
                )
            self._apply_groups(row.AccountID, group_ids)
            return self.get_record(row.AccountID)

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise ValueError("Unable to assign group — account name or work link conflict.") from exc

    def _parse_manual(self, payload: dict, *, existing=None) -> tuple[dict, list[int]]:
        name = (payload.get("account_name") or payload.get("AccountName") or "").strip()
        group_ids = self._parse_groups(payload)
        primary = self.group_repo.get_by_id(group_ids[0])
        ob_fields = self._ob_payload(
            payload, under_type=primary.UnderType if primary else None
        )

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
            raise ValueError("Account Name is required.")
        if len(name) > 200:
            raise ValueError("Account Name must be at most 200 characters.")

        return (
            {
                "AccountName": name,
                "GroupID": group_ids[0],
                "CustomerID": None,
                "WorkID": None,
                **ob_fields,
                "IsActive": is_active,
            },
            group_ids,
        )

    def create_record(self, payload: dict) -> dict:
        if payload.get("customer_id") or payload.get("CustomerID"):
            try:
                customer_id = int(payload.get("customer_id") or payload.get("CustomerID"))
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid customer.") from exc
            return self.assign_customer_group(customer_id, payload)

        if payload.get("work_id") or payload.get("WorkID"):
            try:
                work_id = int(payload.get("work_id") or payload.get("WorkID"))
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid work type.") from exc
            return self.assign_work_group(work_id, payload)

        data, group_ids = self._parse_manual(payload)
        if self.repo.find_by_name(data["AccountName"]):
            raise ValueError(f"Account Name '{data['AccountName']}' already exists.")

        def _write() -> dict:
            row = self.repo.create(
                {
                    **data,
                    "CreatedDate": datetime.utcnow(),
                    "UpdatedDate": None,
                }
            )
            self._apply_groups(row.AccountID, group_ids)
            return self._serialize_manual(row)

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise ValueError(f"Account Name '{data['AccountName']}' already exists.") from exc

    def update_record(self, account_id: int, payload: dict) -> dict:
        row = self.repo.get_by_id(account_id)
        if row is None:
            raise ValueError("Account not found.")
        if row.CustomerID:
            return self.assign_customer_group(row.CustomerID, payload)
        if row.WorkID:
            return self.assign_work_group(row.WorkID, payload)

        data, group_ids = self._parse_manual(payload, existing=row)
        if self.repo.find_by_name(data["AccountName"], exclude_id=account_id):
            raise ValueError(f"Account Name '{data['AccountName']}' already exists.")

        def _write() -> dict:
            updated = self.repo.update(
                row,
                {
                    **data,
                    "UpdatedDate": datetime.utcnow(),
                },
            )
            self._apply_groups(updated.AccountID, group_ids)
            return self._serialize_manual(updated)

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise ValueError(f"Account Name '{data['AccountName']}' already exists.") from exc

    def delete_record(self, account_id: int) -> str:
        row = self.repo.get_by_id(account_id)
        if row is None:
            raise ValueError("Account not found.")
        name = row.AccountName or "Account"
        linked = bool(row.CustomerID or row.WorkID)
        assert_master_unused(
            table="ChartOfAccountMaster",
            pk_column="AccountID",
            pk_value=account_id,
            display_name=name,
            skip_tables={"ChartOfAccountGroupLink"},
            extra_checks=[
                {
                    "table": "OthersBankCashTransaction",
                    "where": "CreditLedgerKey = :key OR DebitLedgerKey = :key",
                    "params": {"key": f"coa-{int(account_id)}"},
                    "label": "Bank / Cash Transaction",
                },
            ],
        )

        def _write() -> str:
            self.repo.delete(row)
            if linked:
                return f"Group assignment cleared for '{name}'."
            return f"Account '{name}' deleted."

        try:
            return persist(_write)
        except IntegrityError as exc:
            raise_if_integrity_in_use(exc, name)
            raise

    def clear_customer_group(self, customer_id: int) -> str:
        row = self.repo.get_by_customer_id(customer_id)
        if row is None:
            raise ValueError("No group assigned for this customer.")
        return self.delete_record(row.AccountID)

    def clear_work_group(self, work_id: int) -> str:
        row = self.repo.get_by_work_id(work_id)
        if row is None:
            raise ValueError("No group assigned for this Income/Expense work type.")
        return self.delete_record(row.AccountID)
