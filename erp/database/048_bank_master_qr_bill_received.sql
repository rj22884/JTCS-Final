/*
    Bank Master — QR/Bill Received flag for Payment Received / Make Payment lists
    NOTE: ALTER and UPDATE must be separate batches (SQL Server compile rules).
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.JtcsBankAccountMaster', N'QrBillReceived') IS NULL
BEGIN
    ALTER TABLE dbo.JtcsBankAccountMaster
    ADD QrBillReceived BIT NOT NULL
        CONSTRAINT DF_JtcsBankAccountMaster_QrBillReceived DEFAULT (0);
END;
GO

IF COL_LENGTH(N'dbo.JtcsBankAccountMaster', N'QrBillReceived') IS NOT NULL
BEGIN
    UPDATE dbo.JtcsBankAccountMaster
    SET QrBillReceived = 1
    WHERE ActiveStatus = 1
      AND QrBillReceived = 0;
END;
GO

PRINT '048_bank_master_qr_bill_received.sql completed.';
GO
