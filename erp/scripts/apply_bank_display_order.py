"""Apply 049_bank_account_display_order.sql and verify Bank Master DisplayOrder."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.repositories.transaction_repository import MasterRepository
from app.services.bank_master_service import BankMasterService

SQL_FILE = ROOT / "database" / "049_bank_account_display_order.sql"


def run_migration() -> None:
    sql = SQL_FILE.read_text(encoding="utf-8")
    for batch in sql.split("GO"):
        batch = batch.strip()
        if not batch or batch.upper().startswith("USE "):
            continue
        if batch.startswith("/*"):
            continue
        db.session.execute(text(batch))
    db.session.commit()


def main() -> int:
    app = create_app()
    with app.app_context():
        run_migration()
        service = BankMasterService()
        rows = service.list_records()
        print(f"OK  Loaded {len(rows)} bank account(s)")
        cash = [r for r in rows if r.get("is_cash")]
        for row in cash:
            assert int(row.get("display_order") or 0) == 1, row
            print(f"OK  Cash account #{row['account_id']} DisplayOrder=1")
        modes = MasterRepository().list_stamp_bank_payment_modes()
        if modes:
            first = modes[0]
            print(
                f"OK  Payment modes first: {first.get('display_account_number')} "
                f"(order={first.get('display_order')})"
            )
        print(f"OK  Payment modes count={len(modes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
