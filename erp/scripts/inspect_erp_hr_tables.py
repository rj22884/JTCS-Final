"""Read-only inspect ERP SQL Server for existing HR/application tables."""
from __future__ import annotations

import sys
from pathlib import Path

ERP_ROOT = Path(r"E:\Git\JTCS Final\erp")
sys.path.insert(0, str(ERP_ROOT))

from app import create_app
from app.extensions import db
from sqlalchemy import text


def main() -> None:
    app = create_app()
    with app.app_context():
        print("RECRUITMENT_DB_PATH:", app.config.get("RECRUITMENT_DB_PATH"))
        print("RECRUITMENT_UPLOAD_DIR:", app.config.get("RECRUITMENT_UPLOAD_DIR"))
        rows = db.session.execute(
            text(
                """
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                  AND (
                    TABLE_NAME LIKE '%Hr%'
                    OR TABLE_NAME LIKE '%Employee%'
                    OR TABLE_NAME LIKE '%Application%'
                    OR TABLE_NAME LIKE '%Candidate%'
                    OR TABLE_NAME LIKE '%Interview%'
                    OR TABLE_NAME LIKE '%Offer%'
                    OR TABLE_NAME LIKE '%Appointment%'
                    OR TABLE_NAME LIKE '%Department%'
                    OR TABLE_NAME LIKE '%Designation%'
                  )
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """
            )
        ).fetchall()
        print("MATCHING TABLES:")
        for row in rows:
            print(f"  {row[0]}.{row[1]}")
        tops = db.session.execute(
            text(
                """
                SELECT MenuID, MenuName, MenuURL, DisplayOrder, IsActive
                FROM dbo.MenuMaster
                WHERE ParentMenuID IS NULL
                ORDER BY DisplayOrder, MenuID
                """
            )
        ).fetchall()
        print("TOP MENUS:")
        for row in tops:
            print(dict(zip(("MenuID", "MenuName", "MenuURL", "DisplayOrder", "IsActive"), row)))


if __name__ == "__main__":
    main()
