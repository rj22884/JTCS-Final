/*
    Ration Card Master match key is FPS ID + RC Number.
    DATA safe / idempotent.
*/
USE JTCSS;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_PdsRationCardMaster_RcNumber'
      AND object_id = OBJECT_ID(N'dbo.PdsRationCardMaster')
)
    DROP INDEX UX_PdsRationCardMaster_RcNumber ON dbo.PdsRationCardMaster;
GO

IF OBJECT_ID(N'dbo.PdsRationCardMaster', N'U') IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_PdsRationCardMaster_FpsRc'
      AND object_id = OBJECT_ID(N'dbo.PdsRationCardMaster')
)
    CREATE UNIQUE INDEX UX_PdsRationCardMaster_FpsRc
        ON dbo.PdsRationCardMaster (FpsRowID, RcNumber)
        WHERE RcNumber <> N'';
GO
