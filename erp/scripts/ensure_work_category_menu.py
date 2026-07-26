"""Ensure Masters → Work/Category Master menu row exists."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.routes.masters_work import _ensure_menu


def main() -> int:
    app = create_app()
    with app.app_context():
        _ensure_menu()
        rows = db.session.execute(
            text(
                """
                SELECT MenuName, MenuURL, IsActive, DisplayOrder
                FROM dbo.MenuMaster
                WHERE MenuURL = N'/masters/income-expense'
                   OR MenuName IN (N'Work/Category Master', N'Income/Expense')
                ORDER BY MenuID
                """
            )
        ).mappings().all()
        for row in rows:
            print(dict(row))
    print("OK Work/Category Master menu ensured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
