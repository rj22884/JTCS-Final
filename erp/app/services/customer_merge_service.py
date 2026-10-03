"""Find duplicate customers and merge their records into one main customer."""

from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.repositories.customer_repository import CustomerRepository
from app.utils.db_session import persist

_MODES = ("name", "phone", "name_phone")
_SKIP_REPOINT = frozenset(
    {
        "CustomerMaster",
        "CustomerIncomeExpenseWorkLink",
        "ChartOfAccountMaster",
        "CustomerPortalLoginLog",
    }
)


def _name_key(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).upper()


def _phone_key(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) >= 10:
        return digits[-10:]
    return ""


def _row_dict(row) -> dict:
    return {
        "customer_id": int(row["CustomerID"]),
        "customer_name": (row.get("CustomerName") or "").strip(),
        "mobile_number": (row.get("MobileNumber") or "").strip(),
        "pan_number": (row.get("PANNumber") or "").strip(),
        "email": (row.get("EmailID") or "").strip(),
        "customer_group": (row.get("CustomerGroup") or "").strip(),
    }


class CustomerMergeService:
    def list_groups(self, mode: str) -> list[dict]:
        mode = (mode or "name_phone").strip().lower()
        if mode not in _MODES:
            raise ValueError("Choose by name, by phone number, or by name + phone number.")
        rows = db.session.execute(
            text(
                """
                SELECT CustomerID, CustomerName, MobileNumber,
                       ISNULL(PANNumber, N'') AS PANNumber,
                       ISNULL(EmailID, N'') AS EmailID,
                       ISNULL(CustomerGroup, N'') AS CustomerGroup
                FROM dbo.CustomerMaster
                WHERE ISNULL(CustomerStatus, N'Active') <> N'Inactive'
                """
            )
        ).mappings().all()
        buckets: dict[str, list[dict]] = {}
        labels: dict[str, str] = {}
        for row in rows:
            item = _row_dict(row)
            name = _name_key(item["customer_name"])
            phone = _phone_key(item["mobile_number"])
            if mode == "name":
                if not name:
                    continue
                key = name
                label = item["customer_name"]
            elif mode == "phone":
                if not phone:
                    continue
                key = phone
                label = item["mobile_number"] or phone
            else:
                if not name or not phone:
                    continue
                key = name + "|" + phone
                label = f"{item['customer_name']} · {item['mobile_number']}"
            buckets.setdefault(key, []).append(item)
            labels[key] = label
        groups = []
        for key, customers in buckets.items():
            if len(customers) < 2:
                continue
            customers.sort(key=lambda item: (item["customer_name"].lower(), item["customer_id"]))
            groups.append(
                {
                    "key": key,
                    "label": labels[key],
                    "count": len(customers),
                    "customers": customers,
                }
            )
        groups.sort(key=lambda group: (-group["count"], group["label"].lower()))
        return groups

    def merge(self, main_customer_id: int, merge_ids: list[int], mode: str) -> dict:
        mode = (mode or "").strip().lower()
        if mode not in _MODES:
            raise ValueError("Choose by name, by phone number, or by name + phone number.")
        main_id = int(main_customer_id)
        sources = []
        for raw in merge_ids or []:
            try:
                cid = int(raw)
            except (TypeError, ValueError):
                continue
            if cid != main_id and cid not in sources:
                sources.append(cid)
        if not sources:
            raise ValueError("Select at least one customer to merge into the main customer.")

        def _write():
            repo = CustomerRepository()
            main = repo.get_by_id(main_id)
            if not main or (getattr(main, "CustomerStatus", None) or "") == "Inactive":
                raise ValueError("Select an active main customer.")
            others = []
            for cid in sources:
                row = repo.get_by_id(cid)
                if not row or (getattr(row, "CustomerStatus", None) or "") == "Inactive":
                    raise ValueError("One of the customers to merge was not found.")
                others.append(row)
            if not self._same_group(main, others, mode):
                raise ValueError("Selected customers are not duplicates for this option.")
            main_name = (getattr(main, "CustomerName", None) or "").strip()
            for row in others:
                source_id = int(row.CustomerID)
                self._repoint(source_id, main_id, main_name)
                self._move_work_links(source_id, main_id)
                self._move_chart(source_id, main_id)
                self._move_portal_log(source_id, main_id)
                repo.purge(source_id)
            return {
                "main_customer_id": main_id,
                "main_customer_name": main_name,
                "merged_count": len(others),
            }

        return persist(_write)

    def _same_group(self, main, others: list, mode: str) -> bool:
        name = _name_key(getattr(main, "CustomerName", None))
        phone = _phone_key(getattr(main, "MobileNumber", None))
        for row in others:
            other_name = _name_key(getattr(row, "CustomerName", None))
            other_phone = _phone_key(getattr(row, "MobileNumber", None))
            if mode == "name" and (not name or other_name != name):
                return False
            if mode == "phone" and (not phone or other_phone != phone):
                return False
            if mode == "name_phone" and (not name or not phone or other_name != name or other_phone != phone):
                return False
        return True

    def _column_exists(self, table: str, column: str) -> bool:
        found = db.session.execute(
            text(
                """
                SELECT COL_LENGTH(:table_name, :column_name)
                """
            ),
            {"table_name": f"dbo.{table}", "column_name": column},
        ).scalar()
        return found is not None

    def _linked_tables(self) -> list[str]:
        rows = db.session.execute(
            text(
                """
                SELECT t.name
                FROM sys.columns c
                INNER JOIN sys.tables t ON t.object_id = c.object_id
                INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
                WHERE s.name = N'dbo' AND c.name = N'CustomerID'
                """
            )
        ).fetchall()
        tables: list[str] = []
        seen: set[str] = set()
        for row in rows:
            table = CustomerRepository._safe_table_name(str(row[0]))
            if not table or table in _SKIP_REPOINT or table in seen:
                continue
            seen.add(table)
            tables.append(table)
        return tables

    def _drop_unique_clashes(self, table: str, source_id: int, main_id: int) -> None:
        """Keep the main customer's row when a unique key would block the move."""
        rows = db.session.execute(
            text(
                """
                SELECT i.index_id, c.name
                FROM sys.tables t
                INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
                INNER JOIN sys.indexes i ON i.object_id = t.object_id AND i.is_unique = 1
                INNER JOIN sys.index_columns ic
                    ON ic.object_id = i.object_id AND ic.index_id = i.index_id
                   AND ic.is_included_column = 0
                INNER JOIN sys.columns c
                    ON c.object_id = ic.object_id AND c.column_id = ic.column_id
                WHERE s.name = N'dbo' AND t.name = :table
                ORDER BY i.index_id, ic.key_ordinal
                """
            ),
            {"table": table},
        ).fetchall()
        grouped: dict[int, list[str]] = {}
        for index_id, column in rows:
            grouped.setdefault(int(index_id), []).append(str(column))
        params = {"main": main_id, "source": source_id}
        for columns in grouped.values():
            if "CustomerID" not in columns:
                continue
            if any(not CustomerRepository._safe_table_name(column) for column in columns):
                continue
            others = [column for column in columns if column != "CustomerID"]
            if not others:
                db.session.execute(
                    text(
                        f"IF EXISTS (SELECT 1 FROM dbo.[{table}] WHERE CustomerID = :main) "
                        f"DELETE FROM dbo.[{table}] WHERE CustomerID = :source"
                    ),
                    params,
                )
                continue
            same = " AND ".join(
                f"((keep.[{column}] = src.[{column}]) OR (keep.[{column}] IS NULL AND src.[{column}] IS NULL))"
                for column in others
            )
            db.session.execute(
                text(
                    f"DELETE src FROM dbo.[{table}] src "
                    f"INNER JOIN dbo.[{table}] keep ON keep.CustomerID = :main AND {same} "
                    f"WHERE src.CustomerID = :source"
                ),
                params,
            )

    def _repoint(self, source_id: int, main_id: int, main_name: str) -> None:
        for table in self._linked_tables():
            self._drop_unique_clashes(table, source_id, main_id)
            has_name = self._column_exists(table, "CustomerName")
            params = {"main": main_id, "source": source_id}
            if has_name:
                size = db.session.execute(
                    text("SELECT COL_LENGTH(:table_name, N'CustomerName')"),
                    {"table_name": f"dbo.{table}"},
                ).scalar()
                chars = max(1, int(size) // 2) if size else 200
                params["name"] = main_name[:chars]
                sql = (
                    f"UPDATE dbo.[{table}] SET CustomerID = :main, CustomerName = :name "
                    "WHERE CustomerID = :source"
                )
            else:
                sql = f"UPDATE dbo.[{table}] SET CustomerID = :main WHERE CustomerID = :source"
            try:
                db.session.execute(text(sql), params)
            except SQLAlchemyError as exc:
                raise ValueError(f"Could not move records in {table}.") from exc

    def _move_work_links(self, source_id: int, main_id: int) -> None:
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.CustomerIncomeExpenseWorkLink', N'U') IS NOT NULL
                BEGIN
                    DELETE src
                    FROM dbo.CustomerIncomeExpenseWorkLink src
                    INNER JOIN dbo.CustomerIncomeExpenseWorkLink keep
                        ON keep.WorkID = src.WorkID
                       AND keep.CustomerID = :main
                    WHERE src.CustomerID = :source;

                    UPDATE dbo.CustomerIncomeExpenseWorkLink
                    SET CustomerID = :main
                    WHERE CustomerID = :source;
                END
                """
            ),
            {"main": main_id, "source": source_id},
        )

    def _move_chart(self, source_id: int, main_id: int) -> None:
        self._try_then(
            """
            IF COL_LENGTH(N'dbo.ChartOfAccountMaster', N'CustomerID') IS NOT NULL
                UPDATE dbo.ChartOfAccountMaster
                SET CustomerID = :main
                WHERE CustomerID = :source
            """,
            """
            IF COL_LENGTH(N'dbo.ChartOfAccountMaster', N'CustomerID') IS NOT NULL
                UPDATE dbo.ChartOfAccountMaster
                SET CustomerID = NULL
                WHERE CustomerID = :source
            """,
            source_id,
            main_id,
        )

    def _move_portal_log(self, source_id: int, main_id: int) -> None:
        self._try_then(
            """
            IF OBJECT_ID(N'dbo.CustomerPortalLoginLog', N'U') IS NOT NULL
                UPDATE dbo.CustomerPortalLoginLog
                SET CustomerID = :main
                WHERE CustomerID = :source
            """,
            """
            IF OBJECT_ID(N'dbo.CustomerPortalLoginLog', N'U') IS NOT NULL
                DELETE FROM dbo.CustomerPortalLoginLog
                WHERE CustomerID = :source
            """,
            source_id,
            main_id,
        )

    def _try_then(self, primary_sql: str, fallback_sql: str, source_id: int, main_id: int) -> None:
        params = {"main": main_id, "source": source_id}
        nested = db.session.begin_nested()
        try:
            db.session.execute(text(primary_sql), params)
            nested.commit()
        except SQLAlchemyError:
            nested.rollback()
            db.session.execute(text(fallback_sql), params)
