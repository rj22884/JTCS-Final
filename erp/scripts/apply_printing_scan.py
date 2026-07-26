"""Apply Printing & Scanning migration (WorkMaster + PrintingScanMaster)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from app.extensions import db
from sqlalchemy import text

MIGRATIONS = [
    ROOT / "database" / "024_printing_scan_work_master.sql",
]


def run_migration(path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
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
        for migration in MIGRATIONS:
            if migration.exists():
                run_migration(migration)
                print(f"OK  Applied {migration.name}")
            else:
                print(f"SKIP Missing {migration.name}")
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
