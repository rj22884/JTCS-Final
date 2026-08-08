"""Smoke test for customer portal profile/module loaders."""

from app import create_app
from app.customer_portal.constants import PORTAL_EDITABLE_FIELDS, PORTAL_READONLY_FIELDS
from app.extensions import db
from app.services.customer_portal_service import CustomerPortalService
from sqlalchemy import text


def main() -> None:
    assert "customer_name" in PORTAL_READONLY_FIELDS
    assert "pan_number" in PORTAL_READONLY_FIELDS
    assert "customer_name" not in PORTAL_EDITABLE_FIELDS
    app = create_app()
    with app.app_context():
        svc = CustomerPortalService()
        cid = db.session.execute(
            text(
                """
                SELECT TOP 1 CustomerID
                FROM CustomerMaster
                WHERE CustomerStatus <> N'Inactive'
                ORDER BY CustomerID
                """
            )
        ).scalar()
        print("sample_customer", cid)
        if not cid:
            print("no customer")
            return
        p = svc.get_profile(int(cid))
        print("profile_ok", p.get("ok"), "field_count", len(p.get("profile") or {}))
        print("readonly", (p.get("profile") or {}).get("readonly_fields"))
        for key in ("payments", "itr", "documents", "support", "gst", "tds", "notices", "downloads"):
            m = svc.get_module_data(int(cid), key)
            print(key, "ok=", m.get("ok"), "sections=", len(m.get("sections") or []))
        # Ensure blocked fields are stripped
        cleaned = svc._validate_profile_payload(
            {
                "customer_name": "HACK",
                "pan_number": "AAAAA1234A",
                "occupation": "Consultant",
                "remarks": "portal smoke",
            },
            customer_id=int(cid),
        )
        assert "customer_name" not in cleaned
        assert "pan_number" not in cleaned
        assert cleaned.get("occupation") == "Consultant"
        print("validation_strip_ok")


if __name__ == "__main__":
    main()
