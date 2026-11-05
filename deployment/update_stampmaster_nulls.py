"""Preview and optionally fill NULL fields in JTCSS.dbo.StampMaster.

The live application's .env supplies the database connection. This script only
updates MobileNumber or EntrySource, and only rows where the chosen column is
NULL. It always previews the target rows and requires an explicit YES.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

APP_ROOT = Path(os.environ.get("VPS_APP_DIR", "/root/JTCS-final"))
ERP_ROOT = APP_ROOT / "erp"
sys.path.insert(0, str(ERP_ROOT))

from sqlalchemy import text

from app import create_app
from app.extensions import db


UPDATES = {
    "1": ("MobileNumber", "9837012345"),
    "2": ("EntrySource", "manual"),
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in UPDATES:
        print("Usage: update_stampmaster_nulls.py 1|2", file=sys.stderr)
        return 2

    column, value = UPDATES[sys.argv[1]]
    app = create_app()
    with app.app_context():
        try:
            with db.engine.connect() as conn:
                database = conn.execute(text("SELECT DB_NAME()")).scalar_one()
                if database != "JTCSS":
                    print(f"[STOP] Connected database is {database!r}; expected 'JTCSS'.")
                    return 3

                rows = conn.execute(
                    text(
                        "SELECT StampID, CertificateNumber, CertificateIssuedDate, "
                        "FirstPartyName, SecondPartyName, MobileNumber, EntrySource "
                        "FROM dbo.StampMaster "
                        f"WHERE [{column}] IS NULL ORDER BY StampID"
                    )
                ).mappings().all()
        except Exception as exc:
            print(
                f"[FAIL] Could not preview live database rows ({type(exc).__name__}). "
                "Check the VPS application's DB connection settings.",
                file=sys.stderr,
            )
            return 4

        print(f"Database: {database}")
        print(f"Selected: {column} NULL -> {value}")
        print(f"Matching rows: {len(rows)}")
        for row in rows:
            print(" | ".join(str(row[key]) if row[key] is not None else "—" for key in (
                "StampID", "CertificateNumber", "CertificateIssuedDate",
                "FirstPartyName", "SecondPartyName", "MobileNumber", "EntrySource",
            )))

        if not rows:
            print("Nothing to update.")
            return 0

        confirm = input("Review complete? Type YES to update these NULL values: ").strip()
        if confirm != "YES":
            print("Cancelled. Nothing was changed.")
            return 0

        try:
            with db.engine.begin() as conn:
                result = conn.execute(
                    text(f"UPDATE dbo.StampMaster SET [{column}] = :value WHERE [{column}] IS NULL"),
                    {"value": value},
                )
                print(f"Updated rows: {result.rowcount}")
        except Exception as exc:
            print(
                f"[FAIL] Update failed and transaction was rolled back ({type(exc).__name__}).",
                file=sys.stderr,
            )
            return 5

    print("Update complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
