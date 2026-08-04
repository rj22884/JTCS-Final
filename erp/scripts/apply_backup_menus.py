"""Ensure Admin Role backup menus and smoke-test BackupService list APIs."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from app.models.menu_master import MenuMaster
from app.routes.backup import ensure_backup_menus
from app.services.backup_service import BackupService


def main() -> int:
    app = create_app()
    with app.app_context():
        ensure_backup_menus()
        rows = (
            MenuMaster.query.filter(
                MenuMaster.MenuName.in_(["Admin Role", "Backup Full", "Data Backup", "Restore Backup"])
            )
            .order_by(MenuMaster.MenuID)
            .all()
        )
        for m in rows:
            print(f"MENU {m.MenuID} {m.MenuName!r} url={m.MenuURL!r} parent={m.ParentMenuID}")

        service = BackupService()
        print("CONN", service.connection_info())
        print("DB backups", len(service.list_database_backups()))
        print("Full backups", len(service.list_full_backups()))

        info = service.create_database_backup(created_by="smoke-test")
        print("CREATED", info["file_name"], info["size_label"], Path(info["path"]).exists())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
