"""Insert Admin Role Property menus into the live ERP database."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from app.extensions import db
from app.routes.property_listings import ensure_property_menu
from sqlalchemy import text


def main() -> None:
    app = create_app()
    with app.app_context():
        ensure_property_menu()
        rows = db.session.execute(
            text(
                """
                SELECT MenuName, MenuURL, IsActive, DisplayOrder
                FROM dbo.MenuMaster
                WHERE MenuName IN (N'Property Management', N'Property Admin Login')
                   OR MenuURL LIKE N'/admin/property%'
                ORDER BY DisplayOrder
                """
            )
        ).fetchall()
        for row in rows:
            print(dict(row._mapping))
        print("PROPERTY_DB_PATH:", app.config.get("PROPERTY_DB_PATH"))


if __name__ == "__main__":
    main()
