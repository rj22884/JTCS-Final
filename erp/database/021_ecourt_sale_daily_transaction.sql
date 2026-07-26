/*
    e-Court Activity — link sales to JTCSDailyTransaction
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.ECourtSale', N'DailyTransactionID') IS NULL
    ALTER TABLE dbo.ECourtSale ADD DailyTransactionID INT NULL;
GO

IF COL_LENGTH(N'dbo.ECourtSale', N'DailyTransactionID') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ECourtSale_DailyTransaction')
    CREATE INDEX IX_ECourtSale_DailyTransaction ON dbo.ECourtSale (DailyTransactionID);
GO

PRINT '021_ecourt_sale_daily_transaction.sql completed.';
GO
