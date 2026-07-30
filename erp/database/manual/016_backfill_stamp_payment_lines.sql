/*
    Backfill JTCSDailyTransactionPayment from linked bank rows
    and sync PaymentSplitCount for stamp entries saved before
    payment detail lines were written correctly.
*/

SET QUOTED_IDENTIFIER ON;
GO

IF EXISTS (
    SELECT 1 FROM sys.tables WHERE name = N'JTCSDailyTransactionPayment'
)
AND EXISTS (
    SELECT 1 FROM sys.tables WHERE name = N'JtcsBankTransaction'
)
BEGIN
    INSERT INTO dbo.JTCSDailyTransactionPayment (
        TransactionID,
        PaymentSequence,
        PaymentModeID,
        BankAccountID,
        Amount,
        BankTransactionID,
        CreatedDate
    )
    SELECT
        d.TransactionID,
        COALESCE(b.PaymentSequence, 1),
        b.PaymentModeID,
        b.JtcsBankAccountID,
        COALESCE(b.Debit, d.SaleAmount),
        b.JtcsBankTransactionID,
        SYSUTCDATETIME()
    FROM dbo.JTCSDailyTransaction d
    INNER JOIN dbo.JtcsBankTransaction b
        ON b.SourceTable = N'JTCSDailyTransaction'
       AND (
            b.SourceRecordID = d.TransactionID
            OR b.SourceID = d.TransactionID
            OR b.JtcsBankTransactionID = d.BankTransactionID
       )
    WHERE COALESCE(b.Debit, 0) > 0
      AND NOT EXISTS (
          SELECT 1
          FROM dbo.JTCSDailyTransactionPayment p
          WHERE p.BankTransactionID = b.JtcsBankTransactionID
      );
END;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.JTCSDailyTransaction')
      AND name = N'PaymentSplitCount'
)
AND EXISTS (
    SELECT 1 FROM sys.tables WHERE name = N'JTCSDailyTransactionPayment'
)
BEGIN
    UPDATE d
    SET PaymentSplitCount = pc.cnt
    FROM dbo.JTCSDailyTransaction d
    INNER JOIN (
        SELECT TransactionID, COUNT(*) AS cnt
        FROM dbo.JTCSDailyTransactionPayment
        GROUP BY TransactionID
    ) pc ON pc.TransactionID = d.TransactionID
    WHERE d.PaymentSplitCount <> pc.cnt;
END;
GO
