"""Apply Others > Expense menu migration."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from app.extensions import db
from sqlalchemy import text

MIGRATION = ROOT / "database" / "025_others_expense_menu.sql"


def main() -> int:
    sql = MIGRATION.read_text(encoding="utf-8")
    app = create_app()
    with app.app_context():
        for batch in sql.split("GO"):
            batch = batch.strip()
            if not batch or batch.upper().startswith("USE "):
                continue
            if batch.startswith("/*") or batch.startswith("PRINT"):
                continue
            db.session.execute(text(batch))
        db.session.commit()
    print(f"OK Applied {MIGRATION.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
