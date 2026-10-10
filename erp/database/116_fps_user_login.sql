/*
    FPS_USER login: link a staff Users row to one PdsFpsMaster shop.
    DATA safe / idempotent. Does not duplicate FPS Master.
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.Users', N'U') IS NOT NULL
AND COL_LENGTH(N'dbo.Users', N'FpsRowID') IS NULL
    ALTER TABLE dbo.Users ADD FpsRowID INT NULL;
GO

IF OBJECT_ID(N'dbo.Users', N'U') IS NOT NULL
AND OBJECT_ID(N'dbo.PdsFpsMaster', N'U') IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = N'FK_Users_FpsRowID'
      AND parent_object_id = OBJECT_ID(N'dbo.Users')
)
    ALTER TABLE dbo.Users
        ADD CONSTRAINT FK_Users_FpsRowID
        FOREIGN KEY (FpsRowID) REFERENCES dbo.PdsFpsMaster (FpsRowID);
GO

IF OBJECT_ID(N'dbo.Users', N'U') IS NOT NULL
AND COL_LENGTH(N'dbo.Users', N'FpsRowID') IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_Users_FpsRowID'
      AND object_id = OBJECT_ID(N'dbo.Users')
)
    CREATE UNIQUE INDEX UX_Users_FpsRowID
        ON dbo.Users (FpsRowID)
        WHERE FpsRowID IS NOT NULL;
GO

PRINT '116_fps_user_login completed.';
GO
