/*
    Other Bank/Cash Transactions — ledger keys for Chart of Group ledgers
    (bank accounts + Chart of Account under Assets / Liabilities).
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.OthersBankCashTransaction', N'U') IS NOT NULL
BEGIN
    IF COL_LENGTH(N'dbo.OthersBankCashTransaction', N'CreditLedgerKey') IS NULL
        ALTER TABLE dbo.OthersBankCashTransaction ADD CreditLedgerKey NVARCHAR(40) NULL;

    IF COL_LENGTH(N'dbo.OthersBankCashTransaction', N'DebitLedgerKey') IS NULL
        ALTER TABLE dbo.OthersBankCashTransaction ADD DebitLedgerKey NVARCHAR(40) NULL;
END;
GO

IF OBJECT_ID(N'dbo.OthersBankCashTransaction', N'U') IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE name = N'CK_OthersBankCashTxn_Accounts'
          AND parent_object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
    )
        ALTER TABLE dbo.OthersBankCashTransaction DROP CONSTRAINT CK_OthersBankCashTxn_Accounts;

    IF EXISTS (
        SELECT 1 FROM sys.foreign_keys
        WHERE name = N'FK_OthersBankCashTxn_Credit'
          AND parent_object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
    )
        ALTER TABLE dbo.OthersBankCashTransaction DROP CONSTRAINT FK_OthersBankCashTxn_Credit;

    IF EXISTS (
        SELECT 1 FROM sys.foreign_keys
        WHERE name = N'FK_OthersBankCashTxn_Debit'
          AND parent_object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
    )
        ALTER TABLE dbo.OthersBankCashTransaction DROP CONSTRAINT FK_OthersBankCashTxn_Debit;
END;
GO

IF OBJECT_ID(N'dbo.OthersBankCashTransaction', N'U') IS NOT NULL
   AND COL_LENGTH(N'dbo.OthersBankCashTransaction', N'CreditBankAccountID') IS NOT NULL
BEGIN
    ALTER TABLE dbo.OthersBankCashTransaction ALTER COLUMN CreditBankAccountID INT NULL;
    ALTER TABLE dbo.OthersBankCashTransaction ALTER COLUMN DebitBankAccountID INT NULL;
END;
GO

IF OBJECT_ID(N'dbo.OthersBankCashTransaction', N'U') IS NOT NULL
BEGIN
    UPDATE dbo.OthersBankCashTransaction
    SET CreditLedgerKey = CONCAT(N'bank-', CreditBankAccountID)
    WHERE CreditLedgerKey IS NULL AND CreditBankAccountID IS NOT NULL;

    UPDATE dbo.OthersBankCashTransaction
    SET DebitLedgerKey = CONCAT(N'bank-', DebitBankAccountID)
    WHERE DebitLedgerKey IS NULL AND DebitBankAccountID IS NOT NULL;
END;
GO

IF OBJECT_ID(N'dbo.OthersBankCashTransaction', N'U') IS NOT NULL
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM sys.foreign_keys
        WHERE name = N'FK_OthersBankCashTxn_Credit'
          AND parent_object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
    )
        ALTER TABLE dbo.OthersBankCashTransaction
            ADD CONSTRAINT FK_OthersBankCashTxn_Credit
            FOREIGN KEY (CreditBankAccountID)
            REFERENCES dbo.JtcsBankAccountMaster (JtcsBankAccountID);

    IF NOT EXISTS (
        SELECT 1 FROM sys.foreign_keys
        WHERE name = N'FK_OthersBankCashTxn_Debit'
          AND parent_object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
    )
        ALTER TABLE dbo.OthersBankCashTransaction
            ADD CONSTRAINT FK_OthersBankCashTxn_Debit
            FOREIGN KEY (DebitBankAccountID)
            REFERENCES dbo.JtcsBankAccountMaster (JtcsBankAccountID);

    IF NOT EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE name = N'CK_OthersBankCashTxn_LedgerKeys'
          AND parent_object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
    )
        ALTER TABLE dbo.OthersBankCashTransaction
            ADD CONSTRAINT CK_OthersBankCashTxn_LedgerKeys
            CHECK (
                CreditLedgerKey IS NOT NULL
                AND DebitLedgerKey IS NOT NULL
                AND CreditLedgerKey <> DebitLedgerKey
            );
END;
GO
