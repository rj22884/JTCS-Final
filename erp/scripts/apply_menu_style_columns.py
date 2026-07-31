"""One-shot: apply 068_menu_master_style_columns.sql only."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SQL_FILE = ROOT / "database" / "068_menu_master_style_columns.sql"
GO_SPLIT = re.compile(r"^\s*GO\s*(?:--.*)?$", re.IGNORECASE | re.MULTILINE)


def connect_string() -> str:
    server = os.getenv("DB_SERVER", r"JTCS\JTCS")
    database = os.getenv("DB_NAME", "JTCSS")
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    trusted = os.getenv("DB_TRUSTED_CONNECTION", "1") == "1"
    trust = "TrustServerCertificate=yes;"
    if os.getenv("DB_TRUST_SERVER_CERTIFICATE", "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        trust = ""
    if trusted:
        return (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
            f"Trusted_Connection=yes;{trust}"
        )
    user = os.getenv("DB_USER", "")
    password = os.getenv("DB_PASSWORD", "")
    return (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
        f"UID={user};PWD={password};{trust}"
    )


def main() -> int:
    sql_text = SQL_FILE.read_text(encoding="utf-8")
    batches = [part.strip() for part in GO_SPLIT.split(sql_text) if part.strip()]
    cn = pyodbc.connect(connect_string(), autocommit=True)
    cur = cn.cursor()
    for batch in batches:
        cur.execute(batch)
    cur.execute(
        """
        SELECT
            COL_LENGTH(N'dbo.MenuMaster', N'FontColor'),
            COL_LENGTH(N'dbo.MenuMaster', N'FontName'),
            COL_LENGTH(N'dbo.MenuMaster', N'BackgroundColor')
        """
    )
    print("Applied", SQL_FILE.name, "OK — column lengths:", cur.fetchone())
    cn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
