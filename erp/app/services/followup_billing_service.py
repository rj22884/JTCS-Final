from __future__ import annotations

from datetime import date

from sqlalchemy import text

from app.extensions import db


class FollowupBillingService:
    @staticmethod
    def next_bill_no(module_code: str, work_date: date | None = None) -> str:
        work_date = work_date or date.today()
        prefix = (module_code or "ITR").strip().upper()
        date_part = work_date.strftime("%d%m%Y")
        pattern = f"{prefix}-{date_part}-%"
        row = db.session.execute(
            text(
                """
                SELECT MAX(BillNo) AS MaxBill
                FROM FollowupEntryMaster
                WHERE ModuleCode = :module
                  AND BillNo LIKE :pattern
                """
            ),
            {"module": prefix, "pattern": pattern},
        ).mappings().first()
        current = (row or {}).get("MaxBill") or ""
        seq = 1
        if current and current.rsplit("-", 1)[-1].isdigit():
            seq = int(current.rsplit("-", 1)[-1]) + 1
        return f"{prefix}-{date_part}-{seq:03d}"
