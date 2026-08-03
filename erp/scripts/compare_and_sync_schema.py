"""
Compare SQL Server schema (tables/columns) and optionally sync MISSING columns to target DB.

Rules:
  - SCHEMA ONLY — never DROP, never TRUNCATE, never copy row data
  - Missing columns are added as NULL (safe)
  - Missing tables are reported (apply numbered migrations); not auto-created
  - Safe to run repeatedly

Usage (from erp/):
  # Dump local DB structure
  .venv\\Scripts\\python.exe scripts\\compare_and_sync_schema.py --dump schema_local.json

  # On VPS: compare dump vs this DB and add missing columns
  .venv/bin/python scripts/compare_and_sync_schema.py --sync-from /tmp/schema_local.json

  # Report only (no ALTER)
  .venv/bin/python scripts/compare_and_sync_schema.py --sync-from schema_local.json --report-only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")


def _connect_string() -> str:
    server = os.getenv("DB_SERVER", r"JTCS\JTCS")
    database = os.getenv("DB_NAME", "JTCSS")
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    trusted = os.getenv("DB_TRUSTED_CONNECTION", "1") == "1"
    user = os.getenv("DB_USER", "")
    password = os.getenv("DB_PASSWORD", "")
    trust = "TrustServerCertificate=yes;"
    if os.getenv("DB_TRUST_SERVER_CERTIFICATE", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        trust = ""
    if trusted:
        return (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
            f"Trusted_Connection=yes;{trust}"
        )
    return (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
        f"UID={user};PWD={password};{trust}"
    )


def _db_label() -> str:
    return f"{os.getenv('DB_SERVER', '?')}\\{os.getenv('DB_NAME', '?')}"


def dump_schema(conn) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            t.TABLE_SCHEMA,
            t.TABLE_NAME,
            c.COLUMN_NAME,
            c.ORDINAL_POSITION,
            c.DATA_TYPE,
            c.CHARACTER_MAXIMUM_LENGTH,
            c.NUMERIC_PRECISION,
            c.NUMERIC_SCALE,
            c.IS_NULLABLE,
            c.COLUMN_DEFAULT
        FROM INFORMATION_SCHEMA.TABLES t
        INNER JOIN INFORMATION_SCHEMA.COLUMNS c
            ON c.TABLE_SCHEMA = t.TABLE_SCHEMA
           AND c.TABLE_NAME = t.TABLE_NAME
        WHERE t.TABLE_TYPE = 'BASE TABLE'
          AND t.TABLE_SCHEMA = 'dbo'
        ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION
        """
    )
    tables: dict[str, dict] = {}
    for row in cur.fetchall():
        schema, table, col, ord_pos, dtype, char_len, num_prec, num_scale, nullable, default = row
        key = f"{schema}.{table}"
        tables.setdefault(
            key,
            {"schema": schema, "table": table, "columns": {}},
        )
        tables[key]["columns"][col] = {
            "name": col,
            "ordinal": int(ord_pos or 0),
            "data_type": (dtype or "").lower(),
            "char_len": int(char_len) if char_len is not None else None,
            "num_prec": int(num_prec) if num_prec is not None else None,
            "num_scale": int(num_scale) if num_scale is not None else None,
            "nullable": (nullable or "YES").upper() == "YES",
            "default": default,
        }
    return {
        "database": os.getenv("DB_NAME", ""),
        "server": os.getenv("DB_SERVER", ""),
        "tables": tables,
    }


def sql_type(col: dict) -> str:
    dtype = col["data_type"]
    if dtype in {"nvarchar", "varchar", "nchar", "char", "varbinary", "binary"}:
        n = col.get("char_len")
        if n is None:
            return dtype.upper()
        if n == -1:
            return f"{dtype.upper()}(MAX)"
        return f"{dtype.upper()}({n})"
    if dtype in {"decimal", "numeric"}:
        p = col.get("num_prec") or 18
        s = col.get("num_scale") or 0
        return f"{dtype.upper()}({p},{s})"
    if dtype == "float":
        p = col.get("num_prec")
        return f"FLOAT({p})" if p else "FLOAT"
    return dtype.upper()


def compare(source: dict, target: dict) -> tuple[list[str], list[tuple[str, dict]], list[str]]:
    """Return (missing_tables, missing_columns[(table, colmeta)], type_mismatches)."""
    src_tables = source.get("tables") or {}
    tgt_tables = target.get("tables") or {}
    missing_tables: list[str] = []
    missing_cols: list[tuple[str, dict]] = []
    mismatches: list[str] = []

    for tkey, tmeta in sorted(src_tables.items()):
        if tkey not in tgt_tables:
            missing_tables.append(tkey)
            continue
        src_cols = tmeta.get("columns") or {}
        tgt_cols = tgt_tables[tkey].get("columns") or {}
        for cname, cmeta in src_cols.items():
            if cname not in tgt_cols:
                missing_cols.append((tkey, cmeta))
                continue
            # Soft type check (report only)
            st = sql_type(cmeta)
            tt = sql_type(tgt_cols[cname])
            if st.replace(" ", "").lower() != tt.replace(" ", "").lower():
                mismatches.append(f"{tkey}.{cname}: local={st} vps={tt}")
    return missing_tables, missing_cols, mismatches


def add_missing_columns(conn, missing_cols: list[tuple[str, dict]]) -> tuple[int, list[str]]:
    cur = conn.cursor()
    applied = 0
    errors: list[str] = []
    for tkey, cmeta in missing_cols:
        schema, table = tkey.split(".", 1)
        col = cmeta["name"]
        # Always add as NULL for safety (even if source was NOT NULL)
        typ = sql_type(cmeta)
        sql = (
            f"IF COL_LENGTH(N'{schema}.{table}', N'{col}') IS NULL "
            f"ALTER TABLE [{schema}].[{table}] ADD [{col}] {typ} NULL;"
        )
        try:
            cur.execute(sql)
            applied += 1
            print(f"[ADD] {tkey}.{col} {typ} NULL")
        except Exception as exc:  # noqa: BLE001
            msg = f"{tkey}.{col}: {exc}"
            errors.append(msg)
            print(f"[ERROR] {msg}")
    return applied, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare/sync SQL schema (structure only)")
    parser.add_argument("--dump", metavar="FILE", help="Dump current DB schema JSON")
    parser.add_argument("--sync-from", metavar="FILE", help="Compare JSON dump to current DB")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="With --sync-from: only report, do not ALTER",
    )
    args = parser.parse_args()

    if not args.dump and not args.sync_from:
        parser.print_help()
        return 2

    print("========================================")
    print("  JTCS ERP — Schema compare / sync")
    print("========================================")
    print(f"  Connected : {_db_label()}")
    print("  Policy    : DATA never overwritten")
    print("========================================")

    try:
        conn = pyodbc.connect(_connect_string(), autocommit=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] SQL connect: {exc}")
        return 1

    try:
        if args.dump:
            data = dump_schema(conn)
            out = Path(args.dump)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(f"[OK] Dumped {len(data['tables'])} tables → {out}")
            return 0

        src_path = Path(args.sync_from)
        if not src_path.is_file():
            print(f"[FAIL] Dump file not found: {src_path}")
            return 1
        source = json.loads(src_path.read_text(encoding="utf-8"))
        target = dump_schema(conn)
        missing_tables, missing_cols, mismatches = compare(source, target)

        print()
        print(f"Source dump : {source.get('server')}\\{source.get('database')} ({src_path.name})")
        print(f"Target DB   : {_db_label()}")
        print(f"Missing tables  : {len(missing_tables)}")
        print(f"Missing columns : {len(missing_cols)}")
        print(f"Type mismatches : {len(mismatches)} (report only)")
        print()

        if missing_tables:
            print("--- Missing tables on VPS (run migrations / deploy) ---")
            for t in missing_tables[:80]:
                print(f"  [TABLE] {t}")
            if len(missing_tables) > 80:
                print(f"  ... and {len(missing_tables) - 80} more")
            print()

        if missing_cols:
            print("--- Missing columns on VPS ---")
            for tkey, cmeta in missing_cols[:100]:
                print(f"  [COL] {tkey}.{cmeta['name']} {sql_type(cmeta)}")
            if len(missing_cols) > 100:
                print(f"  ... and {len(missing_cols) - 100} more")
            print()

        if mismatches:
            print("--- Type mismatches (not auto-changed) ---")
            for line in mismatches[:40]:
                print(f"  [TYPE] {line}")
            if len(mismatches) > 40:
                print(f"  ... and {len(mismatches) - 40} more")
            print()

        if args.report_only:
            print("[OK] Report only — no changes applied")
            return 0 if not missing_tables and not missing_cols else 1

        applied = 0
        errors: list[str] = []
        if missing_cols:
            print("Applying missing columns (NULL-safe ALTER)…")
            applied, errors = add_missing_columns(conn, missing_cols)

        print()
        print(
            f"[OK] ColumnsAdded={applied}  MissingTablesLeft={len(missing_tables)}  "
            f"Errors={len(errors)}"
        )
        if missing_tables:
            print(
                "[WARN] Missing tables were NOT auto-created. "
                "Run schema migrations on VPS (option 9 / apply_schema_migrations)."
            )
        if errors:
            print("[FAIL] Some column adds failed")
            return 1
        if missing_tables:
            return 2
        print("[PASS] Schema structure aligned (columns)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
