/*
    JTCS ERP - Link Chart of Account Master to WorkMaster (Income/Expense).
    Adds optional WorkID on ChartOfAccountMaster only.
    Does NOT alter dbo.WorkMaster.
*/

SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
   AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'WorkID') IS NULL
BEGIN
    ALTER TABLE dbo.ChartOfAccountMaster ADD WorkID INT NULL;
END
GO

IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
   AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'WorkID') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = N'FK_ChartOfAccountMaster_Work'
         AND parent_object_id = OBJECT_ID(N'dbo.ChartOfAccountMaster')
   )
   AND OBJECT_ID(N'dbo.WorkMaster', N'U') IS NOT NULL
BEGIN
    ALTER TABLE dbo.ChartOfAccountMaster
        ADD CONSTRAINT FK_ChartOfAccountMaster_Work
        FOREIGN KEY (WorkID) REFERENCES dbo.WorkMaster (WorkID);
END
GO

IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
   AND COL_LENGTH(N'dbo.ChartOfAccountMaster', N'WorkID') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.indexes
       WHERE name = N'UX_ChartOfAccountMaster_WorkID'
         AND object_id = OBJECT_ID(N'dbo.ChartOfAccountMaster')
   )
BEGIN
    CREATE UNIQUE INDEX UX_ChartOfAccountMaster_WorkID
        ON dbo.ChartOfAccountMaster (WorkID)
        WHERE WorkID IS NOT NULL;
END
GO

PRINT '088_chart_account_work_link.sql completed.';
GO
