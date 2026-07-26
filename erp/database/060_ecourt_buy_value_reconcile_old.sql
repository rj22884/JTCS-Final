/*
    e-Court Activity — reconcile Buy Value for OLD sold receipts
    ----------------------------------------------------------------
    1) JTCSDailyTransaction.PurchaseAmount = SUM(sold receipt buy amounts)
    2) SHCILECourt bank ledger: one Credit (Out) per receipt buy value
       Description: e-Court Purchase — {ReceiptNo}

    No SaleAmount < 500 filter — any buy value.
    Preview first, then run APPLY inside the transaction.
*/
USE JTCSS;
GO

DECLARE @EcourtBankID INT;
DECLARE @BankName NVARCHAR(150);
DECLARE @Masked NVARCHAR(50);

SELECT TOP 1
    @EcourtBankID = JtcsBankAccountID,
    @BankName = BankName,
    @Masked = ISNULL(NULLIF(LTRIM(RTRIM(MaskedAccountNumber)), N''), AccountNumber)
FROM dbo.JtcsBankAccountMaster
WHERE AccountNumber = N'SHCILECourt'
  AND ActiveStatus = 1;

IF @EcourtBankID IS NULL
BEGIN
    RAISERROR(N'SHCILECourt bank account not found in JtcsBankAccountMaster.', 16, 1);
    RETURN;
END

PRINT CONCAT(N'e-Court purchase bank = ', @BankName, N' / ID=', @EcourtBankID);

/* ========== 1) PREVIEW — daily totals ========== */
;WITH BuyByDaily AS (
    SELECT
        s.DailyTransactionID,
        COUNT(*) AS ReceiptCount,
        SUM(ISNULL(s.Amount, 0)) AS BuyTotal
    FROM dbo.ECourtSale s
    WHERE s.DailyTransactionID IS NOT NULL
    GROUP BY s.DailyTransactionID
)
SELECT
    d.TransactionID,
    d.TransactionDate,
    d.ReferenceNo,
    d.SaleAmount,
    d.PurchaseAmount AS Purchase_Before,
    b.BuyTotal AS Purchase_After,
    b.ReceiptCount,
    (
        SELECT COUNT(*)
        FROM dbo.JtcsBankTransaction bt
        WHERE (bt.SourceRecordID = d.TransactionID OR bt.SourceID = d.TransactionID)
          AND bt.JtcsBankAccountID = @EcourtBankID
          AND bt.Description LIKE N'e-Court Purchase%'
    ) AS ExistingPurchaseLedgerRows
FROM dbo.JTCSDailyTransaction d
INNER JOIN BuyByDaily b ON b.DailyTransactionID = d.TransactionID
WHERE d.WorkType = N'SHCIL'
  AND d.SubWorkType = N'e-Court Activity'
ORDER BY d.TransactionID DESC;

/* ========== 2) PREVIEW — per receipt (sample) ========== */
SELECT TOP 100
    s.SaleID,
    s.DailyTransactionID,
    s.StationeryNumber,
    s.ReceiptNo,
    s.Amount AS BuyValue,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM dbo.JtcsBankTransaction bt
            WHERE (bt.SourceRecordID = s.DailyTransactionID OR bt.SourceID = s.DailyTransactionID)
              AND bt.JtcsBankAccountID = @EcourtBankID
              AND bt.Description = N'e-Court Purchase — ' + s.ReceiptNo
        ) THEN N'OK / exists'
        ELSE N'INSERT needed'
    END AS LedgerAction
FROM dbo.ECourtSale s
WHERE s.DailyTransactionID IS NOT NULL
  AND ISNULL(s.Amount, 0) > 0
ORDER BY s.DailyTransactionID DESC, s.ReceiptNo;

/* ========== 3) APPLY ========== */
BEGIN TRAN;

-- A) Daily PurchaseAmount = sum of sold receipt buy values
;WITH BuyByDaily AS (
    SELECT
        s.DailyTransactionID,
        SUM(ISNULL(s.Amount, 0)) AS BuyTotal
    FROM dbo.ECourtSale s
    WHERE s.DailyTransactionID IS NOT NULL
    GROUP BY s.DailyTransactionID
)
UPDATE d
SET d.PurchaseAmount = b.BuyTotal
FROM dbo.JTCSDailyTransaction d
INNER JOIN BuyByDaily b ON b.DailyTransactionID = d.TransactionID
WHERE d.WorkType = N'SHCIL'
  AND d.SubWorkType = N'e-Court Activity';

PRINT CONCAT(N'Daily PurchaseAmount rows updated = ', @@ROWCOUNT);

-- B) Remove old aggregate / wrong purchase ledger rows for these dailies
--    (keeps only exact per-receipt rows: e-Court Purchase — {ReceiptNo})
DELETE bt
FROM dbo.JtcsBankTransaction bt
INNER JOIN dbo.JTCSDailyTransaction d
    ON (bt.SourceRecordID = d.TransactionID OR bt.SourceID = d.TransactionID)
WHERE d.WorkType = N'SHCIL'
  AND d.SubWorkType = N'e-Court Activity'
  AND bt.JtcsBankAccountID = @EcourtBankID
  AND bt.Description LIKE N'e-Court Purchase%'
  AND NOT EXISTS (
        SELECT 1
        FROM dbo.ECourtSale s
        WHERE s.DailyTransactionID = d.TransactionID
          AND bt.Description = N'e-Court Purchase — ' + s.ReceiptNo
  );

PRINT CONCAT(N'Old/mismatched SHCILECourt purchase rows deleted = ', @@ROWCOUNT);

-- C) Insert missing per-receipt buy-value Credit (Out) on SHCILECourt
INSERT INTO dbo.JtcsBankTransaction (
    JtcsBankAccountID,
    BankName,
    MaskedAccountNumber,
    TransactionDate,
    Description,
    Debit,
    Credit,
    ClosingBalance,
    ImportedBy,
    ImportedDate,
    Remarks,
    IsLocked,
    SourceTable,
    SourceRecordID,
    SourceType,
    SourceID,
    LedgerKind,
    PaymentModeID,
    PaymentSequence
)
SELECT
    @EcourtBankID,
    @BankName,
    @Masked,
    d.TransactionDate,
    N'e-Court Purchase — ' + s.ReceiptNo,
    NULL,
    s.Amount,                              -- Credit (Out) = buy value
    0,
    ISNULL(d.CreatedBy, N'system-fix'),
    SYSUTCDATETIME(),
    s.StationeryNumber,
    0,
    N'JTCSDailyTransaction',
    d.TransactionID,
    N'SHCIL',
    d.TransactionID,
    N'PAYMENT',
    d.PaymentModeID,
    ISNULL(d.PaymentSplitCount, 0)
        + ROW_NUMBER() OVER (
            PARTITION BY d.TransactionID
            ORDER BY s.ReceiptNo
          )
FROM dbo.ECourtSale s
INNER JOIN dbo.JTCSDailyTransaction d
    ON d.TransactionID = s.DailyTransactionID
WHERE d.WorkType = N'SHCIL'
  AND d.SubWorkType = N'e-Court Activity'
  AND ISNULL(s.Amount, 0) > 0
  AND NOT EXISTS (
        SELECT 1
        FROM dbo.JtcsBankTransaction bt
        WHERE (bt.SourceRecordID = d.TransactionID OR bt.SourceID = d.TransactionID)
          AND bt.JtcsBankAccountID = @EcourtBankID
          AND bt.Description = N'e-Court Purchase — ' + s.ReceiptNo
  );

PRINT CONCAT(N'Per-receipt SHCILECourt purchase rows inserted = ', @@ROWCOUNT);

/* ========== 4) VERIFY (CK9000300001 example) ========== */
SELECT
    d.TransactionID,
    d.ReferenceNo,
    d.SaleAmount,
    d.PurchaseAmount,
    s.ReceiptNo,
    s.Amount AS BuyValue,
    bt.JtcsBankTransactionID,
    bt.Credit AS LedgerCredit,
    bt.Description
FROM dbo.JTCSDailyTransaction d
INNER JOIN dbo.ECourtSale s ON s.DailyTransactionID = d.TransactionID
LEFT JOIN dbo.JtcsBankTransaction bt
    ON (bt.SourceRecordID = d.TransactionID OR bt.SourceID = d.TransactionID)
   AND bt.JtcsBankAccountID = @EcourtBankID
   AND bt.Description = N'e-Court Purchase — ' + s.ReceiptNo
WHERE d.WorkType = N'SHCIL'
  AND d.SubWorkType = N'e-Court Activity'
  AND (
        d.ReferenceNo = N'CK9000300001'
        OR s.StationeryNumber = N'CK9000300001'
        OR s.ReceiptNo = N'UKCT1609595F2642L'
      )
ORDER BY s.ReceiptNo;

COMMIT TRAN;
-- galat lage to: ROLLBACK TRAN;
GO
