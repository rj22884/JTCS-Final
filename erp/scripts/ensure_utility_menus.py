from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.routes.utility import ensure_utility_menus
from app.utils.runtime_env import is_vps_runtime, sync_menu_label


def main() -> int:
    app = create_app()
    with app.app_context():
        ensure_utility_menus()
        rows = db.session.execute(
            text(
                """
                SELECT m.MenuName, m.MenuURL, p.MenuName AS ParentName
                FROM dbo.MenuMaster m
                LEFT JOIN dbo.MenuMaster p ON p.MenuID = m.ParentMenuID
                WHERE m.MenuURL LIKE N'/admin/utility%'
                   OR m.MenuName = N'Utility'
                ORDER BY m.DisplayOrder, m.MenuID
                """
            )
        ).fetchall()
        print(f"is_vps={is_vps_runtime()} label={sync_menu_label()}")
        for row in rows:
            print(dict(row._mapping))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
