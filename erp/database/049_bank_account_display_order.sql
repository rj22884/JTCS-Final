/*
    Bank Master: DisplayOrder for payment dropdown ordering.
    Cash is always DisplayOrder = 1.
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.JtcsBankAccountMaster', N'DisplayOrder') IS NULL
BEGIN
    ALTER TABLE dbo.JtcsBankAccountMaster
    ADD DisplayOrder INT NOT NULL
        CONSTRAINT DF_JtcsBankAccountMaster_DisplayOrder DEFAULT (100);
END;
GO

UPDATE dbo.JtcsBankAccountMaster
SET DisplayOrder = 1
WHERE LOWER(LTRIM(RTRIM(ISNULL(BankName, N'')))) = N'cash'
   OR LOWER(LTRIM(RTRIM(ISNULL(AccountNumber, N'')))) = N'cash';
GO

UPDATE dbo.JtcsBankAccountMaster
SET DisplayOrder = 100
WHERE DisplayOrder IS NULL
   OR (
        LOWER(LTRIM(RTRIM(ISNULL(BankName, N'')))) <> N'cash'
        AND LOWER(LTRIM(RTRIM(ISNULL(AccountNumber, N'')))) <> N'cash'
        AND DisplayOrder = 1
      );
GO

PRINT '049_bank_account_display_order.sql completed.';
GO
