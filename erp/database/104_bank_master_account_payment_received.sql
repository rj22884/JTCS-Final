/*
    Bank Master — Account Payment Received flag.
    Yes accounts appear in Payment Received options / tabs project-wide.
    NOTE: ALTER and UPDATE must be separate batches (SQL Server compile rules).
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.JtcsBankAccountMaster', N'AccountPaymentReceived') IS NULL
BEGIN
    ALTER TABLE dbo.JtcsBankAccountMaster
    ADD AccountPaymentReceived BIT NOT NULL
        CONSTRAINT DF_JtcsBankAccountMaster_AccountPaymentReceived DEFAULT (0);
END;
GO

IF COL_LENGTH(N'dbo.JtcsBankAccountMaster', N'AccountPaymentReceived') IS NOT NULL
   AND COL_LENGTH(N'dbo.JtcsBankAccountMaster', N'QrBillReceived') IS NOT NULL
BEGIN
    -- First-time only: keep existing Payment Received dropdowns working.
    UPDATE dbo.JtcsBankAccountMaster
    SET AccountPaymentReceived = 1
    WHERE AccountPaymentReceived = 0
      AND QrBillReceived = 1;
END;
GO

PRINT '104_bank_master_account_payment_received.sql completed.';
GO
