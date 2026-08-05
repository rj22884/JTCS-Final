"""Restore Reports → Financial Statements menus after DB restore (idempotent)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.routes.financial_statements import ensure_financial_statements_menus


def main() -> int:
    app = create_app()
    with app.app_context():
        before = db.session.execute(
            text(
                """
                SELECT MenuID, ParentMenuID, MenuName, MenuURL, IsActive
                FROM dbo.MenuMaster
                WHERE MenuName LIKE N'%Financial%'
                   OR MenuURL LIKE N'%financial-statements%'
                ORDER BY MenuID
                """
            )
        ).fetchall()
        print(f"BEFORE: {len(before)} row(s)")
        for row in before:
            print(dict(row._mapping))

        parents = db.session.execute(
            text(
                """
                SELECT TOP 5 MenuID, MenuName, MenuURL, IsActive
                FROM dbo.MenuMaster
                WHERE ParentMenuID IS NULL
                  AND (
                        MenuName LIKE N'%Report%'
                     OR MenuURL LIKE N'/Reports%'
                  )
                ORDER BY MenuID
                """
            )
        ).fetchall()
        print("PARENT CANDIDATES:")
        for row in parents:
            print(dict(row._mapping))

        ensure_financial_statements_menus()
        print("ENSURE OK")

        after = db.session.execute(
            text(
                """
                SELECT m.MenuID, m.ParentMenuID, p.MenuName AS ParentName,
                       m.MenuName, m.MenuURL, m.IsActive, m.DisplayOrder
                FROM dbo.MenuMaster m
                LEFT JOIN dbo.MenuMaster p ON p.MenuID = m.ParentMenuID
                WHERE m.MenuName = N'Financial Statements'
                   OR m.MenuURL LIKE N'%financial-statements%'
                   OR m.ParentMenuID IN (
                        SELECT MenuID FROM dbo.MenuMaster
                        WHERE MenuName = N'Financial Statements'
                           OR MenuURL = N'/Reports_and_analysis/financial-statements'
                   )
                ORDER BY COALESCE(m.ParentMenuID, m.MenuID), m.DisplayOrder, m.MenuID
                """
            )
        ).fetchall()
        print(f"AFTER: {len(after)} row(s)")
        for row in after:
            print(dict(row._mapping))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
