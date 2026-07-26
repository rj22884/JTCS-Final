/*
    JTCS ERP - Multiple payment modes per daily transaction
    - JTCSDailyTransactionPayment detail lines
    - JtcsBankTransaction payment metadata columns
    - JTCSDailyTransaction split count
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.JTCSDailyTransaction') AND name = N'PaymentSplitCount'
)
    ALTER TABLE dbo.JTCSDailyTransaction
        ADD PaymentSplitCount INT NOT NULL
            CONSTRAINT DF_JTCSDailyTransaction_PaymentSplitCount DEFAULT (1);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.JtcsBankTransaction') AND name = N'PaymentModeID'
)
    ALTER TABLE dbo.JtcsBankTransaction ADD PaymentModeID INT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.JtcsBankTransaction') AND name = N'PaymentSequence'
)
    ALTER TABLE dbo.JtcsBankTransaction ADD PaymentSequence INT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.tables WHERE name = N'JTCSDailyTransactionPayment'
)
BEGIN
    CREATE TABLE dbo.JTCSDailyTransactionPayment (
        PaymentLineID       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        TransactionID       INT NOT NULL,
        PaymentSequence     INT NOT NULL CONSTRAINT DF_JTCSDailyTransactionPayment_Seq DEFAULT (1),
        PaymentModeID       INT NULL,
        BankAccountID       INT NOT NULL,
        Amount              DECIMAL(18, 2) NOT NULL,
        BankTransactionID   INT NULL,
        CreatedDate         DATETIME2 NOT NULL CONSTRAINT DF_JTCSDailyTransactionPayment_Created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_JTCSDailyTransactionPayment_Daily
            FOREIGN KEY (TransactionID) REFERENCES dbo.JTCSDailyTransaction (TransactionID),
        CONSTRAINT FK_JTCSDailyTransactionPayment_Bank
            FOREIGN KEY (BankTransactionID) REFERENCES dbo.JtcsBankTransaction (JtcsBankTransactionID),
        CONSTRAINT CK_JTCSDailyTransactionPayment_Amount CHECK (Amount > 0)
    );

    CREATE INDEX IX_JTCSDailyTransactionPayment_Transaction
        ON dbo.JTCSDailyTransactionPayment (TransactionID, PaymentSequence);
END;
GO

SET QUOTED_IDENTIFIER ON;
GO

UPDATE dbo.JtcsBankTransaction
SET PaymentSequence = 1
WHERE PaymentSequence IS NULL
  AND SourceRecordID IS NOT NULL;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_JtcsBankTransaction_SourceKind'
      AND object_id = OBJECT_ID(N'dbo.JtcsBankTransaction')
)
    DROP INDEX UX_JtcsBankTransaction_SourceKind ON dbo.JtcsBankTransaction;
GO

CREATE UNIQUE INDEX UX_JtcsBankTransaction_SourceKind
    ON dbo.JtcsBankTransaction (SourceType, SourceRecordID, LedgerKind, PaymentSequence)
    WHERE SourceRecordID IS NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_JtcsBankTransaction_SourceSequence'
      AND object_id = OBJECT_ID(N'dbo.JtcsBankTransaction')
)
    CREATE INDEX IX_JtcsBankTransaction_SourceSequence
        ON dbo.JtcsBankTransaction (SourceTable, SourceRecordID, PaymentSequence);
GO
