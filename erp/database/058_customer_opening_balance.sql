/*
    Customer Master — Opening Balance fields (Basic Info)
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.CustomerMaster', N'OpeningBalance') IS NULL
    ALTER TABLE dbo.CustomerMaster ADD OpeningBalance DECIMAL(18, 2) NULL;
GO

IF COL_LENGTH(N'dbo.CustomerMaster', N'OpeningBalanceDate') IS NULL
    ALTER TABLE dbo.CustomerMaster ADD OpeningBalanceDate DATE NULL;
GO

IF COL_LENGTH(N'dbo.CustomerMaster', N'OpeningBalanceDrCr') IS NULL
    ALTER TABLE dbo.CustomerMaster ADD OpeningBalanceDrCr NVARCHAR(2) NULL;
GO

PRINT '058_customer_opening_balance.sql completed.';
GO
