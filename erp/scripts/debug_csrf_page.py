"""Inspect Integration Settings page CSRF + save response."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app


def main() -> None:
    app = create_app()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["user_name"] = "Admin"
        sess["role"] = "Administrator"

    page = client.get("/admin/integrations")
    html = page.get_data(as_text=True)
    print("page", page.status_code)
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    print("csrf_len", len(m.group(1)) if m else None)
    m2 = re.search(r'data-api-settings="([^"]+)"', html)
    print("api", m2.group(1) if m2 else None)
    m3 = re.search(r"integration_settings\.js\?v=([^\"']+)", html)
    print("js_v", m3.group(1) if m3 else None)

    csrf = m.group(1) if m else ""
    resp = client.post(
        "/admin/integrations/api/settings",
        json={
            "provider": "smtp",
            "values": {
                "host": "smtpout.secureserver.net",
                "port": "465",
                "username": "admin@jtcsxpert.com",
                "use_tls": "False",
                "use_ssl": "True",
                "from_email": "admin@jtcsxpert.com",
            },
        },
        headers={"X-CSRFToken": csrf, "Accept": "application/json"},
    )
    print("post", resp.status_code, resp.headers.get("Content-Type"))
    print(resp.get_data(as_text=True)[:500])


if __name__ == "__main__":
    main()
