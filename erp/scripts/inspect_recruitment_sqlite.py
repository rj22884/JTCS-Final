"""Read-only inspection of the existing recruitment SQLite database."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\JTCS Web Page\recruitment\var\recruitment.db")


def main() -> None:
    if not DB_PATH.exists():
        print(f"MISSING: {DB_PATH}")
        return
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    print(f"DB: {DB_PATH}")
    print(f"SIZE: {DB_PATH.stat().st_size}")
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1")]
    print("TABLES:", tables)
    for table in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"\n=== {table} count={count} ===")
        print("COLS:", cols)
    if "job_applications" in tables:
        print("\n--- job_applications rows ---")
        rows = conn.execute(
            """
            SELECT application_id, application_number, application_status,
                   submitted_at, resume_stored_name, application_pdf_stored_name
            FROM job_applications
            ORDER BY application_id
            """
        ).fetchall()
        for row in rows:
            print(dict(row))
        print("\n--- status counts ---")
        for row in conn.execute(
            "SELECT application_status, COUNT(*) AS n FROM job_applications GROUP BY application_status"
        ):
            print(dict(row))
    conn.close()


if __name__ == "__main__":
    main()
