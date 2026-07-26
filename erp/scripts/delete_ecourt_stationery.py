"""Hard-delete e-Court stationery groups and related accounting rows."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

TARGET_STATIONERY = [
    "CK900301625",
    "CK900301678",
    "CKTEMP101",
    # Actual values stored in DB (UI may show shortened label)
    "CK9000301625",
    "CK9000301678",
]


def main() -> int:
    import pyodbc

    server = os.getenv("DB_SERVER", r"JTCS\JTCS")
    database = os.getenv("DB_NAME", "JTCSS")
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};Trusted_Connection=yes;"
    )
    conn.autocommit = False
    cur = conn.cursor()

    placeholders = ",".join("?" for _ in TARGET_STATIONERY)
    print(f"Database: {database}")

    cur.execute(
        f"SELECT StationeryNumber, COUNT(*) FROM dbo.ECourtReceiptLine "
        f"WHERE StationeryNumber IN ({placeholders}) GROUP BY StationeryNumber",
        TARGET_STATIONERY,
    )
    before_lines = cur.fetchall()
    print("Before ECourtReceiptLine:", before_lines or "none")

    cur.execute(
        f"SELECT StationeryNumber, COUNT(*) FROM dbo.ECourtSale "
        f"WHERE StationeryNumber IN ({placeholders}) GROUP BY StationeryNumber",
        TARGET_STATIONERY,
    )
    before_sales = cur.fetchall()
    print("Before ECourtSale:", before_sales or "none")

    sql = f"""
DECLARE @Stationery TABLE (StationeryNumber NVARCHAR(50) PRIMARY KEY);
INSERT INTO @Stationery (StationeryNumber) VALUES
    (N'CK900301625'), (N'CK900301678'), (N'CKTEMP101'),
    (N'CK9000301625'), (N'CK9000301678');

DECLARE @Receipts TABLE (ReceiptNo NVARCHAR(50) PRIMARY KEY);
INSERT INTO @Receipts (ReceiptNo)
SELECT DISTINCT l.ReceiptNo
FROM dbo.ECourtReceiptLine l
WHERE l.StationeryNumber IN (SELECT StationeryNumber FROM @Stationery);

DECLARE @DailyTxn TABLE (TransactionID INT PRIMARY KEY);
INSERT INTO @DailyTxn (TransactionID)
SELECT DISTINCT s.DailyTransactionID
FROM dbo.ECourtSale s
WHERE s.DailyTransactionID IS NOT NULL
  AND (s.StationeryNumber IN (SELECT StationeryNumber FROM @Stationery)
       OR s.ReceiptNo IN (SELECT ReceiptNo FROM @Receipts));

DECLARE @BankTxn TABLE (JtcsBankTransactionID INT PRIMARY KEY);
INSERT INTO @BankTxn (JtcsBankTransactionID)
SELECT DISTINCT p.BankTransactionID
FROM dbo.JTCSDailyTransactionPayment p
WHERE p.TransactionID IN (SELECT TransactionID FROM @DailyTxn)
  AND p.BankTransactionID IS NOT NULL;

INSERT INTO @BankTxn (JtcsBankTransactionID)
SELECT DISTINCT b.JtcsBankTransactionID
FROM dbo.JtcsBankTransaction b
WHERE b.SourceRecordID IN (SELECT TransactionID FROM @DailyTxn)
  AND b.SourceType = N'SHCIL'
  AND b.JtcsBankTransactionID NOT IN (SELECT JtcsBankTransactionID FROM @BankTxn);

DELETE p FROM dbo.JTCSDailyTransactionPayment p
WHERE p.TransactionID IN (SELECT TransactionID FROM @DailyTxn);

UPDATE d SET d.BankTransactionID = NULL
FROM dbo.JTCSDailyTransaction d
WHERE d.TransactionID IN (SELECT TransactionID FROM @DailyTxn);

DELETE b FROM dbo.JtcsBankTransaction b
WHERE b.JtcsBankTransactionID IN (SELECT JtcsBankTransactionID FROM @BankTxn);

DELETE s FROM dbo.ECourtSale s
WHERE s.StationeryNumber IN (SELECT StationeryNumber FROM @Stationery)
   OR s.ReceiptNo IN (SELECT ReceiptNo FROM @Receipts);

DELETE d FROM dbo.JTCSDailyTransaction d
WHERE d.TransactionID IN (SELECT TransactionID FROM @DailyTxn);

DELETE l FROM dbo.ECourtReceiptLine l
WHERE l.StationeryNumber IN (SELECT StationeryNumber FROM @Stationery);

DELETE b FROM dbo.ECourtReceiptBatch b
WHERE NOT EXISTS (SELECT 1 FROM dbo.ECourtReceiptLine l WHERE l.ImportID = b.ImportID);
"""
    cur.execute(sql)
    conn.commit()

    cur.execute(
        f"SELECT StationeryNumber, COUNT(*) FROM dbo.ECourtReceiptLine "
        f"WHERE StationeryNumber IN ({placeholders}) GROUP BY StationeryNumber",
        TARGET_STATIONERY,
    )
    after_lines = cur.fetchall()
    print("After ECourtReceiptLine:", after_lines or "none (deleted)")

    cur.execute(
        f"SELECT StationeryNumber, COUNT(*) FROM dbo.ECourtSale "
        f"WHERE StationeryNumber IN ({placeholders}) GROUP BY StationeryNumber",
        TARGET_STATIONERY,
    )
    after_sales = cur.fetchall()
    print("After ECourtSale:", after_sales or "none (deleted)")

    conn.close()
    print("OK — hard delete committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
