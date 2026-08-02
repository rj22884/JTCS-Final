"""Debug Integration Settings SMTP save JSON response."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from app.modules.settings.services import IntegrationSettingsService


def main() -> None:
    app = create_app()
    with app.app_context():
        svc = IntegrationSettingsService()
        result = svc.save_provider_settings(
            "smtp",
            {
                "host": "smtpout.secureserver.net",
                "port": "465",
                "username": "admin@jtcsxpert.com",
                "smtp_password": "********",
                "use_tls": "False",
                "use_ssl": "True",
                "from_email": "admin@jtcsxpert.com",
            },
        )
        print("service_save_ok", (result.get("field_values") or {}).get("host"))

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["user_name"] = "Admin"
        sess["role"] = "Administrator"

    page = client.get("/admin/integrations")
    print("page", page.status_code)
    html = page.get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    csrf = m.group(1) if m else ""
    print("csrf", bool(csrf))

    resp = client.post(
        "/admin/integrations/api/settings",
        json={
            "provider": "smtp",
            "values": {
                "host": "smtpout.secureserver.net",
                "port": "465",
                "username": "admin@jtcsxpert.com",
                "smtp_password": "********",
                "use_tls": "False",
                "use_ssl": "True",
                "from_email": "admin@jtcsxpert.com",
            },
        },
        headers={"X-CSRFToken": csrf, "Accept": "application/json"},
    )
    print("post_status", resp.status_code)
    print("content_type", resp.headers.get("Content-Type"))
    print("body_head", resp.get_data(as_text=True)[:400])


if __name__ == "__main__":
    main()
