"""Apply 051_admin_role_settings_menu.sql — Settings under Admin Role (3rd)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app import create_app
from app.extensions import db

MIGRATION = ROOT / "database" / "051_admin_role_settings_menu.sql"


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
        print("OK  Settings moved under Admin Role (DisplayOrder=3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
