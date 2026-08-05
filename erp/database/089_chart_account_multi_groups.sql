/*
    JTCS ERP - Chart of Account: multiple groups per account (max 5, enforced in app).
    Does NOT alter CustomerMaster / WorkMaster.
*/

SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.ChartOfAccountGroupLink', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ChartOfAccountGroupLink (
        AccountID    INT NOT NULL,
        GroupID      INT NOT NULL,
        DisplayOrder TINYINT NOT NULL CONSTRAINT DF_ChartOfAccountGroupLink_Order DEFAULT (1),
        CONSTRAINT PK_ChartOfAccountGroupLink PRIMARY KEY (AccountID, GroupID),
        CONSTRAINT FK_ChartOfAccountGroupLink_Account
            FOREIGN KEY (AccountID) REFERENCES dbo.ChartOfAccountMaster (AccountID) ON DELETE CASCADE,
        CONSTRAINT FK_ChartOfAccountGroupLink_Group
            FOREIGN KEY (GroupID) REFERENCES dbo.ChartOfGroupMaster (GroupID)
    );
    CREATE INDEX IX_ChartOfAccountGroupLink_GroupID ON dbo.ChartOfAccountGroupLink (GroupID);
END
GO

/* Backfill from existing single GroupID */
IF OBJECT_ID(N'dbo.ChartOfAccountGroupLink', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NOT NULL
BEGIN
    INSERT INTO dbo.ChartOfAccountGroupLink (AccountID, GroupID, DisplayOrder)
    SELECT a.AccountID, a.GroupID, 1
    FROM dbo.ChartOfAccountMaster a
    WHERE a.GroupID IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM dbo.ChartOfAccountGroupLink l
          WHERE l.AccountID = a.AccountID AND l.GroupID = a.GroupID
      );
END
GO

PRINT '089_chart_account_multi_groups.sql completed.';
GO
