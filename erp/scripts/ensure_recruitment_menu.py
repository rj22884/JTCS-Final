"""Insert Admin Role recruitment menus into the live ERP database."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from app.extensions import db
from app.routes.recruitment_applications import ensure_recruitment_menu
from sqlalchemy import text


def main() -> None:
    app = create_app()
    with app.app_context():
        ensure_recruitment_menu()
        rows = db.session.execute(
            text(
                """
                SELECT MenuName, MenuURL, IsActive, DisplayOrder
                FROM dbo.MenuMaster
                WHERE MenuName IN (N'Sales Executive Applications', N'Recruitment Admin Login')
                   OR MenuURL LIKE N'/admin/recruitment%'
                ORDER BY DisplayOrder
                """
            )
        ).fetchall()
        for row in rows:
            print(dict(row._mapping))


if __name__ == "__main__":
    main()
