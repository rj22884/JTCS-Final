"""Apply 017_bank_master_account_type.sql and smoke-test Bank Master."""
from pathlib import Path

from app import create_app
from app.extensions import db
from app.services.bank_master_service import BankMasterService
from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = ROOT / "database" / "017_bank_master_account_type.sql"


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
        service = BankMasterService()
        rows = service.list_records()
        print(f"OK  Loaded {len(rows)} bank account(s)")
        created = service.create_record(
            {
                "BankName": "Test Bank Master",
                "AccountType": "SB",
                "AccountNumber": "9999999999",
                "ActiveStatus": "1",
            }
        )
        print(f"OK  Created account #{created['account_id']}")
        updated = service.update_record(
            created["account_id"],
            {
                "BankName": "Test Bank Master Updated",
                "AccountType": "CC/OD",
                "AccountNumber": "9999999999",
                "ActiveStatus": "1",
            },
        )
        assert updated["account_type"] == "CC/OD"
        print("OK  Updated account type to CC/OD")
        message = service.delete_record(created["account_id"])
        print(f"OK  Delete: {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
