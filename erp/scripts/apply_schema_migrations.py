"""
Apply SCHEMA-ONLY SQL migrations from erp/database/NNN_*.sql

Rules:
  - Never RESTORE / overwrite the database
  - Never run scripts under erp/database/manual/ (one-shot data fixes)
  - Skip known data-mutation script names (belt-and-suspenders)
  - Track applied files in dbo.SchemaMigration (idempotent)
  - Safe to run on every deploy / update_database.bat

Usage (from erp folder):
  .venv\\Scripts\\python.exe scripts\\apply_schema_migrations.py
  python3 scripts/apply_schema_migrations.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pyodbc

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

SQL_DIR = ROOT / "database"
MANUAL_DIR = SQL_DIR / "manual"

# Never auto-apply these (even if someone puts them back under database/).
DATA_MUTATION_SKIP = {
    "006_inspect_user_emails.sql",
    "007_cleanup_legacy_users.sql",
    "016_backfill_stamp_payment_lines.sql",
    "034_delete_ecourt_test_stationery.sql",
    "060_ecourt_buy_value_reconcile_old.sql",
    "061_ecourt_purchaseamount_to_shcilecourt.sql",
}

FORBIDDEN_SQL = re.compile(
    r"\bRESTORE\s+DATABASE\b|\bDROP\s+DATABASE\b|\bTRUNCATE\s+TABLE\b",
    re.IGNORECASE,
)

GO_SPLIT = re.compile(r"^\s*GO\s*(?:--.*)?$", re.IGNORECASE | re.MULTILINE)


def _odbc_connect_string() -> str:
    server = os.getenv("DB_SERVER", r"JTCS\JTCS")
    database = os.getenv("DB_NAME", "JTCSS")
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    trusted = os.getenv("DB_TRUSTED_CONNECTION", "1") == "1"
    user = os.getenv("DB_USER", "")
    password = os.getenv("DB_PASSWORD", "")
    # Prefer Driver 18 if listed that way on VPS.
    extra = ""
    if "18" in driver:
        extra = "TrustServerCertificate=yes;"
    if trusted:
        return (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
            f"Trusted_Connection=yes;{extra}"
        )
    return (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
        f"UID={user};PWD={password};{extra}"
    )


def _split_batches(sql_text: str) -> list[str]:
    parts = GO_SPLIT.split(sql_text)
    batches: list[str] = []
    for part in parts:
        cleaned = part.strip()
        if cleaned:
            batches.append(cleaned)
    return batches


def _ensure_tracking(cursor) -> None:
    cursor.execute(
        """
        IF OBJECT_ID(N'dbo.SchemaMigration', N'U') IS NULL
        BEGIN
            CREATE TABLE dbo.SchemaMigration (
                MigrationID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                ScriptName NVARCHAR(260) NOT NULL UNIQUE,
                AppliedAt DATETIME2 NOT NULL
                    CONSTRAINT DF_SchemaMigration_AppliedAt DEFAULT (SYSUTCDATETIME())
            );
        END
        """
    )


def _already_applied(cursor, name: str) -> bool:
    cursor.execute(
        "SELECT COUNT(1) FROM dbo.SchemaMigration WHERE ScriptName = ?",
        name,
    )
    row = cursor.fetchone()
    return bool(row and int(row[0]) >= 1)


def _list_schema_scripts() -> list[Path]:
    if not SQL_DIR.is_dir():
        return []
    scripts = sorted(SQL_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    return [p for p in scripts if p.is_file()]


def apply_migrations() -> int:
    server = os.getenv("DB_SERVER", r"JTCS\JTCS")
    database = os.getenv("DB_NAME", "JTCSS")
    print("========================================")
    print("  JTCS ERP — SCHEMA-ONLY migrations")
    print("========================================")
    print(f"  Server   : {server}")
    print(f"  Database : {database}")
    print("  Policy   : existing DATA is never overwritten")
    print("             only new tables / columns / indexes")
    print("========================================")
    print()

    try:
        conn = pyodbc.connect(_odbc_connect_string(), autocommit=True, timeout=30)
    except Exception as exc:
        print(f"[ERROR] SQL connect fail: {exc}")
        return 1

    applied = 0
    skipped = 0
    blocked = 0

    try:
        cursor = conn.cursor()
        _ensure_tracking(cursor)

        scripts = _list_schema_scripts()
        if not scripts:
            print("[OK] No numbered SQL scripts found.")
            return 0

        for path in scripts:
            name = path.name
            if name in DATA_MUTATION_SKIP:
                print(f"[SKIP data-script] {name}")
                blocked += 1
                continue

            text = path.read_text(encoding="utf-8-sig")
            if FORBIDDEN_SQL.search(text):
                print(f"[BLOCK dangerous SQL] {name} — contains RESTORE/DROP DATABASE/TRUNCATE")
                blocked += 1
                continue

            if _already_applied(cursor, name):
                skipped += 1
                continue

            print(f"[APPLY] {name}")
            try:
                for batch in _split_batches(text):
                    cursor.execute(batch)
                    while cursor.nextset():
                        pass
                cursor.execute(
                    "INSERT INTO dbo.SchemaMigration (ScriptName) VALUES (?)",
                    name,
                )
                applied += 1
            except Exception as exc:
                print(f"[ERROR] Failed on {name}: {exc}")
                print("  Database left as-is (no restore / no data wipe).")
                return 1

        print()
        print(f"[OK] Applied={applied}  AlreadyDone={skipped}  Blocked={blocked}")
        if MANUAL_DIR.is_dir():
            manuals = sorted(MANUAL_DIR.glob("*.sql"))
            if manuals:
                print(
                    f"  Note: {len(manuals)} one-shot script(s) in database/manual/ "
                    "(run by hand only — never auto)."
                )
        print("========================================")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(apply_migrations())
