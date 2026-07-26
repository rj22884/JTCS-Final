"""Apply 048_purpose_master_rd_in_bank.sql."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.services.bank_master_service import ACCOUNT_TYPES, BankMasterService
from app.services.purpose_master_service import PurposeMasterService

SQL_FILE = ROOT / "database" / "048_purpose_master_rd_in_bank.sql"


def run_migration() -> None:
    sql = SQL_FILE.read_text(encoding="utf-8")
    for batch in sql.split("GO"):
        batch = batch.strip()
        if not batch or batch.upper().startswith("USE "):
            continue
        if batch.startswith("/*") or batch.startswith("PRINT"):
            continue
        db.session.execute(text(batch))
    db.session.commit()


def main() -> int:
    app = create_app()
    with app.app_context():
        run_migration()
        print("OK  Migration 048 applied")
        assert "RD" in ACCOUNT_TYPES
        print(f"OK  Bank AccountTypes: {ACCOUNT_TYPES}")
        purposes = PurposeMasterService().list_records(active_only=True)
        print(f"OK  Active purposes: {len(purposes)}")
        banks = BankMasterService().list_records()
        print(f"OK  Bank accounts: {len(banks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
