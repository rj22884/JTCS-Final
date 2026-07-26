/*
    e-Court OLD sold records → SHCILECourt purchase in JtcsBankTransaction
    ---------------------------------------------------------------------
    For each sold daily:
      WorkType      = SHCIL
      SubWorkType   = e-Court Activity
      PurchaseAmount > 0
      Description like 'e-Court Receipt Sale%'
    Insert missing Credit (Out) on HDFC / SHCILECourt
    Description = e-Court Purchase, Credit = PurchaseAmount

    SSMS: pehle PREVIEW, phir APPLY. Galat ho to ROLLBACK.
*/
USE JTCSS;
GO

DECLARE @EcourtBankID INT;
DECLARE @BankName NVARCHAR(150);
DECLARE @Masked NVARCHAR(50);
DECLARE @PaymentModeID INT;

SELECT TOP 1
    @EcourtBankID = JtcsBankAccountID,
    @BankName = BankName,
    @Masked = ISNULL(NULLIF(LTRIM(RTRIM(MaskedAccountNumber)), N''), AccountNumber)
FROM dbo.JtcsBankAccountMaster
WHERE AccountNumber = N'SHCILECourt'
  AND ActiveStatus = 1;

IF @EcourtBankID IS NULL
BEGIN
    RAISERROR(N'SHCILECourt (HDFC) account not found in JtcsBankAccountMaster.', 16, 1);
    RETURN;
END

SELECT TOP 1 @PaymentModeID = pm.PaymentModeID
FROM dbo.PaymentModeMaster pm
WHERE pm.BankAccountID = @EcourtBankID
  AND pm.IsActive = 1
ORDER BY pm.PaymentModeID;

PRINT CONCAT(N'Bank = ', @BankName, N' / ID=', @EcourtBankID, N' / PaymentModeID=', ISNULL(@PaymentModeID, 0));

/* ========== 1) PREVIEW ========== */
SELECT
    d.TransactionID,
    d.TransactionDate,
    d.ReferenceNo,
    d.Description,
    d.SaleAmount,
    d.PurchaseAmount,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM dbo.JtcsBankTransaction b
            WHERE (b.SourceRecordID = d.TransactionID OR b.SourceID = d.TransactionID)
              AND b.JtcsBankAccountID = @EcourtBankID
              AND ISNULL(b.Credit, 0) > 0
        ) THEN N'OK / already exists'
        ELSE N'INSERT needed'
    END AS LedgerAction
FROM dbo.JTCSDailyTransaction d
WHERE d.WorkType = N'SHCIL'
  AND d.SubWorkType = N'e-Court Activity'
  AND ISNULL(d.PurchaseAmount, 0) > 0
  AND (
        d.Description LIKE N'e-Court Receipt Sale%'
        OR d.Description LIKE N'%receipt(s)%'
      )
ORDER BY d.TransactionID DESC;

/* ========== 2) APPLY ========== */
BEGIN TRAN;

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
    N'e-Court Purchase',
    NULL,
    d.PurchaseAmount,
    0,
    N'System',
    GETUTCDATE(),
    d.ReferenceNo,
    0,
    N'JTCSDailyTransaction',
    d.TransactionID,
    N'SHCIL',
    d.TransactionID,
    N'PAYMENT',
    @PaymentModeID,
    ISNULL(d.PaymentSplitCount, 1) + 1
FROM dbo.JTCSDailyTransaction d
WHERE d.WorkType = N'SHCIL'
  AND d.SubWorkType = N'e-Court Activity'
  AND ISNULL(d.PurchaseAmount, 0) > 0
  AND (
        d.Description LIKE N'e-Court Receipt Sale%'
        OR d.Description LIKE N'%receipt(s)%'
      )
  AND NOT EXISTS (
      SELECT 1
      FROM dbo.JtcsBankTransaction b
      WHERE (b.SourceRecordID = d.TransactionID OR b.SourceID = d.TransactionID)
        AND b.JtcsBankAccountID = @EcourtBankID
        AND ISNULL(b.Credit, 0) > 0
  );

SELECT @@ROWCOUNT AS RowsInserted;

/* verify */
SELECT
    b.JtcsBankTransactionID,
    d.TransactionID,
    d.TransactionDate,
    d.ReferenceNo,
    d.PurchaseAmount,
    b.BankName,
    b.MaskedAccountNumber,
    b.Description,
    b.Credit
FROM dbo.JTCSDailyTransaction d
INNER JOIN dbo.JtcsBankTransaction b
    ON (b.SourceRecordID = d.TransactionID OR b.SourceID = d.TransactionID)
WHERE d.WorkType = N'SHCIL'
  AND d.SubWorkType = N'e-Court Activity'
  AND b.JtcsBankAccountID = @EcourtBankID
  AND b.Description = N'e-Court Purchase'
  AND ISNULL(b.Credit, 0) > 0
ORDER BY d.TransactionID DESC;

COMMIT;
-- ROLLBACK;
