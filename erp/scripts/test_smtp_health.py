"""Verify GoDaddy Titan SMTP connectivity using .env settings."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from app.utils.smtp_health import check_smtp_from_config, mask_email


def main() -> int:
    app = create_app()
    with app.app_context():
        username = app.config.get("MAIL_USERNAME", "")
        print(f"Checking SMTP for {mask_email(username)} via {app.config.get('MAIL_SERVER')}:{app.config.get('MAIL_PORT')}")
        ok, detail = check_smtp_from_config(app.config)
        if ok:
            print(f"OK  {detail}")
            return 0
        print(f"FAIL {detail}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
