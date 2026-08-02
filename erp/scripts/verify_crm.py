"""Quick CRM schema / menu verification."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app import create_app
from app.extensions import db


def main() -> None:
    app = create_app()
    with app.app_context():
        tables = [
            "CrmLead",
            "CrmConversation",
            "CrmMessage",
            "CrmTask",
            "CrmFollowUp",
            "CrmTimelineEvent",
            "Notification",
            "AuditLog",
            "CrmDocument",
            "CrmWorkflowDefinition",
        ]
        for name in tables:
            obj_id = db.session.execute(
                text("SELECT OBJECT_ID(:n, N'U')"),
                {"n": f"dbo.{name}"},
            ).scalar()
            print(f"{name}: {'OK' if obj_id else 'MISSING'}")

        menus = db.session.execute(
            text(
                """
                SELECT COUNT(1) FROM dbo.MenuMaster
                WHERE MenuName = N'CRM'
                   OR ParentMenuID IN (
                        SELECT MenuID FROM dbo.MenuMaster WHERE MenuName = N'CRM'
                   )
                """
            )
        ).scalar()
        leads = db.session.execute(text("SELECT COUNT(1) FROM dbo.CrmLead")).scalar()
        print(f"crm menus: {menus}")
        print(f"leads: {leads}")


if __name__ == "__main__":
    main()
