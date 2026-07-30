/*
    Hard delete e-Court stationery test data (CK900301625, CK900301678, CKTEMP101)
    Run in SSMS against your ERP database (JTCSS / JTCSS_NEW).
    Previous delete may have failed because DB stores CK9000301625 / CK9000301678 (extra zero).
*/
SET NOCOUNT ON;
PRINT N'Database: ' + DB_NAME();
GO

BEGIN TRANSACTION;

DECLARE @Stationery TABLE (StationeryNumber NVARCHAR(50) PRIMARY KEY);
INSERT INTO @Stationery (StationeryNumber) VALUES
    (N'CK900301625'),
    (N'CK900301678'),
    (N'CKTEMP101'),
    (N'CK9000301625'),
    (N'CK9000301678');

PRINT N'--- Before delete ---';
SELECT StationeryNumber, COUNT(*) AS ReceiptCount
FROM dbo.ECourtReceiptLine
WHERE StationeryNumber IN (SELECT StationeryNumber FROM @Stationery)
GROUP BY StationeryNumber;

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
  AND (
        s.StationeryNumber IN (SELECT StationeryNumber FROM @Stationery)
     OR s.ReceiptNo IN (SELECT ReceiptNo FROM @Receipts)
  );

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

-- 1) Payment lines
DELETE p
FROM dbo.JTCSDailyTransactionPayment p
WHERE p.TransactionID IN (SELECT TransactionID FROM @DailyTxn);

-- 2) Break bank link on daily txn
UPDATE d
SET d.BankTransactionID = NULL
FROM dbo.JTCSDailyTransaction d
WHERE d.TransactionID IN (SELECT TransactionID FROM @DailyTxn);

-- 3) Bank transactions
DELETE b
FROM dbo.JtcsBankTransaction b
WHERE b.JtcsBankTransactionID IN (SELECT JtcsBankTransactionID FROM @BankTxn);

-- 4) Sale records
DELETE s
FROM dbo.ECourtSale s
WHERE s.StationeryNumber IN (SELECT StationeryNumber FROM @Stationery)
   OR s.ReceiptNo IN (SELECT ReceiptNo FROM @Receipts);

-- 5) Daily transactions (accounting)
DELETE d
FROM dbo.JTCSDailyTransaction d
WHERE d.TransactionID IN (SELECT TransactionID FROM @DailyTxn);

-- 6) Imported receipt lines
DELETE l
FROM dbo.ECourtReceiptLine l
WHERE l.StationeryNumber IN (SELECT StationeryNumber FROM @Stationery);

-- 7) Empty import batches
DELETE b
FROM dbo.ECourtReceiptBatch b
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.ECourtReceiptLine l WHERE l.ImportID = b.ImportID
);

PRINT N'--- After delete (should be empty) ---';
SELECT StationeryNumber, COUNT(*) AS Remaining
FROM dbo.ECourtReceiptLine
WHERE StationeryNumber IN (SELECT StationeryNumber FROM @Stationery)
GROUP BY StationeryNumber;

COMMIT TRANSACTION;
PRINT N'Done — hard delete committed.';
GO
