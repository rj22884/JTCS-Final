"""Apply 047_others_bank_cash_rd_account.sql and smoke-test modules."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.services.others_bank_cash_service import OthersBankCashService
from app.services.rd_account_service import RdAccountService

SQL_FILE = ROOT / "database" / "047_others_bank_cash_rd_account.sql"


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
        print("OK  Migration 047 applied")

        rd_service = RdAccountService()
        suffix = datetime.utcnow().strftime("%H%M%S")
        created = rd_service.create_record(
            {
                "RdName": "Test RD Account",
                "RdNumber": f"RD-TEST-{suffix}",
                "BankName": "Test Post Office",
                "ActiveStatus": "1",
                "OpeningBalance": "1000",
            },
            created_by="migration-smoke",
        )
        print(f"OK  Created RD #{created['rd_account_id']} bank_account={created['bank_account_id']}")

        obc = OthersBankCashService()
        accounts = obc.list_account_rows()
        print(f"OK  Ledger accounts available: {len(accounts)}")
        assert any(a.get("account_id") == created["bank_account_id"] for a in accounts)

        message = rd_service.delete_record(created["rd_account_id"])
        print(f"OK  RD delete: {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
