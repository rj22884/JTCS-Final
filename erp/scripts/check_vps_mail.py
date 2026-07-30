#!/usr/bin/env python3
"""Quick check that mail env is VPS-ready (no secrets printed).

On Ubuntu/Debian VPS use:
  python3 scripts/check_vps_mail.py
or, if a venv exists:
  .venv/bin/python scripts/check_vps_mail.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from app.utils.smtp_health import check_smtp_from_config, mask_email


def main() -> int:
    app = create_app()
    with app.app_context():
        cfg = app.config
        base = (cfg.get("APP_BASE_URL") or "").rstrip("/")
        host = urlparse(base).hostname or ""
        print("MAIL_SERVER     =", cfg.get("MAIL_SERVER"))
        print("MAIL_PORT       =", cfg.get("MAIL_PORT"))
        print("MAIL_USERNAME   =", mask_email(cfg.get("MAIL_USERNAME")))
        print("MAIL_PASSWORD   =", "SET" if cfg.get("MAIL_PASSWORD") else "MISSING")
        print("MAIL_SENDER     =", cfg.get("MAIL_DEFAULT_SENDER"))
        print("APP_BASE_URL    =", base or "(empty)")

        problems = []
        if not cfg.get("MAIL_PASSWORD"):
            problems.append("Set MAIL_PASSWORD in erp/.env to your Titan/GoDaddy mailbox password.")
        if not cfg.get("MAIL_DEFAULT_SENDER"):
            problems.append("Set MAIL_DEFAULT_SENDER in erp/.env.")
        if not host or host in {"localhost", "127.0.0.1"}:
            problems.append(
                "On VPS set APP_BASE_URL to the public URL, e.g. http://203.141.5.68:8000"
            )

        print()
        ok, detail = check_smtp_from_config(cfg)
        print("SMTP check     =", "OK" if ok else "FAIL")
        print("Detail         =", detail)

        if problems:
            print("\nFix these before expecting cloud registration emails:")
            for item in problems:
                print(" -", item)
            return 1 if not ok else 0
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
