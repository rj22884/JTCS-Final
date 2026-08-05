/*
    JTCS ERP - Link Chart of Account Master to CustomerMaster (read-only side).
    Adds optional CustomerID on ChartOfAccountMaster only.
    Does NOT alter dbo.CustomerMaster.
*/

SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
   AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'CustomerID') IS NULL
BEGIN
    ALTER TABLE dbo.ChartOfAccountMaster ADD CustomerID INT NULL;
END
GO

IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
   AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'CustomerID') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = N'FK_ChartOfAccountMaster_Customer'
         AND parent_object_id = OBJECT_ID(N'dbo.ChartOfAccountMaster')
   )
   AND OBJECT_ID(N'dbo.CustomerMaster', N'U') IS NOT NULL
BEGIN
    ALTER TABLE dbo.ChartOfAccountMaster
        ADD CONSTRAINT FK_ChartOfAccountMaster_Customer
        FOREIGN KEY (CustomerID) REFERENCES dbo.CustomerMaster (CustomerID);
END
GO

IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
   AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'CustomerID') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.indexes
       WHERE name = N'UX_ChartOfAccountMaster_CustomerID'
         AND object_id = OBJECT_ID(N'dbo.ChartOfAccountMaster')
   )
BEGIN
    CREATE UNIQUE INDEX UX_ChartOfAccountMaster_CustomerID
        ON dbo.ChartOfAccountMaster (CustomerID)
        WHERE CustomerID IS NOT NULL;
END
GO

PRINT '087_chart_account_customer_link.sql completed.';
GO
