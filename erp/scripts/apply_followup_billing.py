"""Apply followup billing / ITR filed date migration."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from app.extensions import db
from sqlalchemy import text

MIGRATION = ROOT / "database" / "033_followup_billing_fields.sql"


def _prepare_batch(batch: str) -> str | None:
    batch = batch.strip()
    if not batch or batch.upper().startswith("USE "):
        return None
    if batch.upper().startswith("PRINT"):
        return None
    while batch.startswith("/*"):
        end = batch.find("*/")
        if end == -1:
            return None
        batch = batch[end + 2 :].strip()
    return batch or None


def main() -> int:
    sql = MIGRATION.read_text(encoding="utf-8")
    app = create_app()
    with app.app_context():
        for batch in sql.split("GO"):
            prepared = _prepare_batch(batch)
            if not prepared:
                continue
            db.session.execute(text(prepared))
        db.session.commit()
    print(f"OK Applied {MIGRATION.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
