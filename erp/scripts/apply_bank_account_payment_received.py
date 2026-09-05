"""Apply 104_bank_master_account_payment_received.sql and verify the flag."""
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

SQL_FILE = ROOT / "database" / "104_bank_master_account_payment_received.sql"


def run_migration() -> None:
    sql = SQL_FILE.read_text(encoding="utf-8")
    for batch in sql.split("GO"):
        batch = batch.strip()
        if not batch or batch.upper().startswith("USE "):
            continue
        if batch.startswith("/*") or batch.upper().startswith("PRINT"):
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
        flagged = [r for r in rows if r.get("account_payment_received")]
        print(f"OK  Account Payment Received = Yes: {len(flagged)}")
        modes = MasterRepository().list_stamp_bank_payment_modes()
        print(f"OK  Payment Received options: {len(modes)}")
        for row in modes:
            assert row.get("account_payment_received") is True, row
        all_modes = MasterRepository().list_stamp_bank_payment_modes(
            account_payment_received_only=False
        )
        print(f"OK  Unfiltered payment options: {len(all_modes)}")
        assert len(all_modes) >= len(modes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
