"""Read-only review of JtcsBankTransaction ID 3003 before any delete."""

from __future__ import annotations

from app import create_app
from app.extensions import db
from sqlalchemy import text


def main() -> None:
    app = create_app()
    with app.app_context():
        print("=== RECORD 3003 ===")
        row = db.session.execute(
            text(
                """
                SELECT *
                FROM dbo.JtcsBankTransaction
                WHERE JtcsBankTransactionID = 3003
                """
            )
        ).mappings().first()
        print(dict(row) if row else "NOT FOUND")

        print("\n=== FK CONSTRAINTS REFERENCING JtcsBankTransaction ===")
        fks = db.session.execute(
            text(
                """
                SELECT
                    fk.name AS fk_name,
                    OBJECT_SCHEMA_NAME(fk.parent_object_id) AS schema_name,
                    OBJECT_NAME(fk.parent_object_id) AS parent_table,
                    COL_NAME(fc.parent_object_id, fc.parent_column_id) AS parent_column,
                    OBJECT_NAME(fk.referenced_object_id) AS referenced_table,
                    COL_NAME(fc.referenced_object_id, fc.referenced_column_id) AS referenced_column,
                    fk.delete_referential_action_desc
                FROM sys.foreign_keys fk
                INNER JOIN sys.foreign_key_columns fc
                    ON fc.constraint_object_id = fk.object_id
                WHERE OBJECT_NAME(fk.referenced_object_id) = N'JtcsBankTransaction'
                ORDER BY parent_table, parent_column
                """
            )
        ).mappings().all()
        if not fks:
            print("None (no FK constraints reference JtcsBankTransaction)")
        for fk in fks:
            print(dict(fk))

        print("\n=== SOFT REFERENCES (application-level) ===")
        checks = [
            (
                "JTCSDailyTransaction.BankTransactionID=3003",
                """
                SELECT TransactionID, TransactionDate, Description, TotalAmount,
                       BankTransactionID, Status, WorkType, SubWorkType
                FROM dbo.JTCSDailyTransaction
                WHERE BankTransactionID = 3003
                """,
            ),
            (
                "JTCSDailyTransaction.TransactionID=1610",
                """
                SELECT TransactionID, TransactionDate, Description, TotalAmount,
                       BankTransactionID, Status, WorkType, SubWorkType, CustomerID
                FROM dbo.JTCSDailyTransaction
                WHERE TransactionID = 1610
                """,
            ),
            (
                "JTCSDailyTransactionPayment.BankTransactionID=3003",
                """
                SELECT PaymentLineID, TransactionID, BankAccountID, Amount, BankTransactionID
                FROM dbo.JTCSDailyTransactionPayment
                WHERE BankTransactionID = 3003
                """,
            ),
            (
                "OthersBankCashTransaction In/Out = 3003",
                """
                SELECT EntryID, VoucherNo, WorkDate, Amount,
                       InBankTransactionID, OutBankTransactionID
                FROM dbo.OthersBankCashTransaction
                WHERE InBankTransactionID = 3003 OR OutBankTransactionID = 3003
                """,
            ),
        ]
        for title, sql in checks:
            print(f"\n-- {title}")
            try:
                rows = db.session.execute(text(sql)).mappings().all()
                if not rows:
                    print("0 rows")
                for r in rows:
                    print(dict(r))
            except Exception as exc:  # noqa: BLE001
                print(f"SKIP/ERROR: {exc}")

        # Any other columns named like %BankTransaction% containing 3003
        print("\n=== SCAN TABLES WITH BankTransactionID-LIKE COLUMNS ===")
        cols = db.session.execute(
            text(
                """
                SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE COLUMN_NAME LIKE N'%BankTransaction%'
                ORDER BY TABLE_NAME, COLUMN_NAME
                """
            )
        ).mappings().all()
        for col in cols:
            schema = col["TABLE_SCHEMA"]
            table = col["TABLE_NAME"]
            column = col["COLUMN_NAME"]
            sql = f"""
                SELECT COUNT(*) AS cnt
                FROM [{schema}].[{table}]
                WHERE [{column}] = 3003
            """
            try:
                cnt = db.session.execute(text(sql)).scalar()
                print(f"{schema}.{table}.{column} => {cnt}")
            except Exception as exc:  # noqa: BLE001
                print(f"{schema}.{table}.{column} => ERROR {exc}")

        print("\n=== IsLocked / soft-delete column on JtcsBankTransaction ===")
        meta = db.session.execute(
            text(
                """
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = N'JtcsBankTransaction'
                  AND COLUMN_NAME IN (N'IsLocked', N'IsActive', N'IsDeleted', N'DeletedDate')
                ORDER BY COLUMN_NAME
                """
            )
        ).mappings().all()
        for m in meta:
            print(dict(m))
        if not meta:
            print("No IsActive/IsDeleted soft-delete columns found")


if __name__ == "__main__":
    main()
