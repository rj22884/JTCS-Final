"""Verify Integration Settings module bootstrap."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app import create_app
from app.extensions import db


def main() -> None:
    app = create_app()
    client = app.test_client()
    rules = sorted(r.rule for r in app.url_map.iter_rules() if "integration" in r.rule)
    print("routes", rules)

    page = client.get("/admin/integrations")
    print("page_status", page.status_code, page.headers.get("Location"))

    with app.app_context():
        oid = db.session.execute(
            text("SELECT OBJECT_ID(N'dbo.IntegrationSettings', N'U')")
        ).scalar()
        print("table_ok", bool(oid))
        menu = db.session.execute(
            text(
                """
                SELECT MenuName, MenuURL, RoleName
                FROM dbo.MenuMaster
                WHERE MenuName = N'Integration Settings'
                """
            )
        ).first()
        print("menu", tuple(menu) if menu else None)


if __name__ == "__main__":
    main()
