"""
Migrate JTCS ERP to new database JTCSS on SQL Server instance JTCS\\JTCS.

- Creates JTCSS if missing
- Builds schema from legacy structure clone + numbered SQL scripts
- Imports MASTER data only from JTCS (read-only on source)
- Leaves all transaction tables empty
- Generates migration report

Usage (from erp folder):
    .venv\\Scripts\\python.exe scripts\\migrate_to_jtcss.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import build_sqlalchemy_uri

SOURCE_DB = "JTCS"
TARGET_DB = "JTCSS"
SERVER = r"JTCS\JTCS"

LEGACY_STRUCTURE_TABLES = [
    "Users",
    "CustomerMaster",
    "JtcsBankAccountMaster",
    "JtcsBankTransaction",
    "WorkTypeMaster",
    "TransactionTypeMaster",
]

MASTER_IMPORT_TABLES = [
    "JtcsBankAccountMaster",
    "CustomerMaster",
    "WorkTypeMaster",
    "TransactionTypeMaster",
    "Users",
    "CompanyProfile",
    "PaymentModeMaster",
    "MenuMaster",
]

TRANSACTION_EMPTY_TABLES = [
    "JtcsBankTransaction",
    "JTCSDailyTransaction",
    "JTCSDailyTransactionPayment",
    "StampMaster",
    "StampOcrImage",
    "AuthToken",
    "PasswordResetOTP",
]

SQL_SCRIPTS_IN_ORDER = [
    "000_create_jtcss_database.sql",
    "015_bootstrap_jtcss_legacy_structure.sql",
    "001_create_menu_master.sql",
    "002_create_jtcs_daily_transaction.sql",
    "004_auth_production.sql",
    "008_create_password_reset_otp.sql",
    "009_add_verification_tracking.sql",
    "010_create_stamp_master.sql",
    "012_stamp_ocr_image.sql",
    "014_multiple_payment_modes.sql",
    "003_seed_module_menus.sql",
    "005_remove_court_fee_stamp.sql",
    "011_stamp_activity_menu.sql",
    "013_stamp_reports_menu.sql",
]


def _master_engine(database: str) -> Engine:
    import os
    from urllib.parse import quote_plus

    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    odbc = (
        f"DRIVER={{{driver}}};"
        f"SERVER={SERVER};"
        f"DATABASE={database};"
        "Trusted_Connection=yes;"
    )
    uri = f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc)}"
    return create_engine(uri, isolation_level="AUTOCOMMIT")


def _run_sql_file(engine: Engine, path: Path, database: str | None = None) -> None:
    sql = path.read_text(encoding="utf-8")
    if database:
        sql = f"USE [{database}];\n{sql}"
    batches = [b.strip() for b in sql.split("\nGO") if b.strip()]
    with engine.connect() as conn:
        for batch in batches:
            conn.exec_driver_sql(batch)


def _table_exists(engine: Engine, table: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=:t"
            ),
            {"t": table},
        ).first()
    return row is not None


def _row_count(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT COUNT(*) FROM dbo.[{table}]")).scalar() or 0)


def _list_tables(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_TYPE='BASE TABLE' AND TABLE_SCHEMA='dbo' "
                "ORDER BY TABLE_NAME"
            )
        ).all()
    return [r[0] for r in rows]


def _import_master_table(target: Engine, source: Engine, table: str) -> dict:
    result = {"table": table, "imported": 0, "skipped": False, "error": None}
    if not _table_exists(source, table):
        result["skipped"] = True
        result["error"] = "Not found in source JTCS"
        return result
    if not _table_exists(target, table):
        result["skipped"] = True
        result["error"] = "Not found in target JTCSS"
        return result

    source_count = _row_count(source, table)
    if source_count == 0:
        result["skipped"] = True
        result["error"] = "Source empty"
        return result

    with target.connect() as conn:
        conn.exec_driver_sql(f"DELETE FROM dbo.[{table}]")
        conn.commit()

    with source.connect() as src_conn, target.connect() as tgt_conn:
        cols = src_conn.execute(
            text(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=:t "
                "ORDER BY ORDINAL_POSITION"
            ),
            {"t": table},
        ).all()
        col_list = ", ".join(f"[{c[0]}]" for c in cols)
        has_identity = src_conn.execute(
            text(
                "SELECT COUNT(*) FROM sys.identity_columns "
                "WHERE OBJECT_ID = OBJECT_ID(:full)"
            ),
            {"full": f"dbo.{table}"},
        ).scalar()

        insert_sql = (
            f"INSERT INTO [{TARGET_DB}].dbo.[{table}] ({col_list}) "
            f"SELECT {col_list} FROM [{SOURCE_DB}].dbo.[{table}]"
        )
        if has_identity:
            tgt_conn.exec_driver_sql(f"SET IDENTITY_INSERT dbo.[{table}] ON")
        tgt_conn.exec_driver_sql(insert_sql)
        if has_identity:
            tgt_conn.exec_driver_sql(f"SET IDENTITY_INSERT dbo.[{table}] OFF")
        tgt_conn.commit()

    result["imported"] = _row_count(target, table)
    return result


def main() -> int:
    report: dict = {
        "started": datetime.now().isoformat(),
        "source_database": SOURCE_DB,
        "target_database": TARGET_DB,
        "server": SERVER,
        "connection_string": build_sqlalchemy_uri(),
        "tables_created": [],
        "master_imports": [],
        "skipped_tables": [],
        "empty_transaction_tables": [],
        "warnings": [],
        "errors": [],
    }

    master_engine = _master_engine("master")
    source_engine = _master_engine(SOURCE_DB)
    target_engine = _master_engine(TARGET_DB)

    db_dir = ROOT / "database"

    print("=== STEP 1: Create JTCSS database ===")
    try:
        _run_sql_file(master_engine, db_dir / "000_create_jtcss_database.sql")
    except Exception as exc:
        report["errors"].append(f"Create database: {exc}")
        print(f"ERROR: {exc}")
        return 1

    print("=== STEP 2: Bootstrap legacy table structures ===")
    try:
        _run_sql_file(target_engine, db_dir / "015_bootstrap_jtcss_legacy_structure.sql", TARGET_DB)
    except Exception as exc:
        report["errors"].append(f"Legacy bootstrap: {exc}")
        print(f"ERROR: {exc}")
        return 1

    print("=== STEP 3: Apply ERP SQL scripts ===")
    for script in SQL_SCRIPTS_IN_ORDER[2:]:
        path = db_dir / script
        if not path.exists():
            report["warnings"].append(f"Missing script: {script}")
            continue
        print(f"  Running {script}...")
        try:
            _run_sql_file(target_engine, path, TARGET_DB)
        except Exception as exc:
            report["errors"].append(f"{script}: {exc}")
            print(f"  WARN/ERROR {script}: {exc}")

    report["tables_created"] = _list_tables(target_engine)
    print(f"  Tables in JTCSS: {len(report['tables_created'])}")

    print("=== STEP 4: Import master data from JTCS (read-only source) ===")
    for table in MASTER_IMPORT_TABLES:
        print(f"  Importing {table}...")
        try:
            info = _import_master_table(target_engine, source_engine, table)
            report["master_imports"].append(info)
            if info.get("error") and not info.get("imported"):
                report["skipped_tables"].append(table)
                print(f"    Skipped: {info['error']}")
            else:
                print(f"    Imported {info['imported']} rows")
        except Exception as exc:
            report["errors"].append(f"Import {table}: {exc}")
            print(f"    ERROR: {exc}")

    print("=== STEP 5: Verify transaction tables empty ===")
    for table in TRANSACTION_EMPTY_TABLES:
        if _table_exists(target_engine, table):
            count = _row_count(target_engine, table)
            report["empty_transaction_tables"].append({"table": table, "rows": count})
            if count > 0:
                report["warnings"].append(f"{table} has {count} rows (expected 0)")

    with target_engine.connect() as conn:
        db_name = conn.execute(text("SELECT DB_NAME()")).scalar()
    report["verified_db_name"] = db_name
    report["finished"] = datetime.now().isoformat()

    report_path = db_dir / "MIGRATION_JTCSS_REPORT.md"
    _write_report(report_path, report)
    print(f"\nReport written: {report_path}")
    print(f"SELECT DB_NAME() => {db_name}")
    print(f"Tables: {len(report['tables_created'])}")
    print(f"Master imports: {len(report['master_imports'])}")
    print(f"Errors: {len(report['errors'])}")
    return 0 if not report["errors"] else 1


def _write_report(path: Path, report: dict) -> None:
    lines = [
        "# JTCSS Migration Report",
        "",
        f"- **Started:** {report['started']}",
        f"- **Finished:** {report.get('finished', '—')}",
        f"- **Server:** `{report['server']}`",
        f"- **Source database:** `{report['source_database']}` (unchanged, read-only)",
        f"- **Target database:** `{report['target_database']}`",
        f"- **Verified DB_NAME():** `{report.get('verified_db_name', '—')}`",
        "",
        "## Connection String",
        "",
        f"`{report['connection_string']}`",
        "",
        f"## Total Tables Created ({len(report['tables_created'])})",
        "",
    ]
    for t in report["tables_created"]:
        lines.append(f"- `{t}`")

    lines.extend(["", "## Master Data Import", ""])
    lines.append("| Table | Rows Imported | Status |")
    lines.append("|-------|---------------|--------|")
    for item in report["master_imports"]:
        status = item.get("error") or "OK"
        lines.append(f"| {item['table']} | {item.get('imported', 0)} | {status} |")

    lines.extend(["", "## Transaction Tables (must be empty)", ""])
    for item in report["empty_transaction_tables"]:
        lines.append(f"- `{item['table']}`: **{item['rows']}** rows")

    if report["skipped_tables"]:
        lines.extend(["", "## Skipped Master Tables", ""])
        for t in report["skipped_tables"]:
            lines.append(f"- `{t}`")

    if report["warnings"]:
        lines.extend(["", "## Warnings", ""])
        for w in report["warnings"]:
            lines.append(f"- {w}")

    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for e in report["errors"]:
            lines.append(f"- {e}")

    lines.extend(
        [
            "",
            "## Accounting Rule (permanent)",
            "",
            "- Business work → `JTCSDailyTransaction`",
            "- Money movement → `JtcsBankTransaction`",
            "- All modules post through these two tables only",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
