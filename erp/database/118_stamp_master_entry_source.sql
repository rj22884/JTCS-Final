/*
    StampMaster — entry mode (manual / integration / online) and e-Stamp order reference.
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.StampMaster', N'EntrySource') IS NULL
    ALTER TABLE dbo.StampMaster ADD EntrySource NVARCHAR(20) NULL;
GO

IF COL_LENGTH(N'dbo.StampMaster', N'WebsiteReference') IS NULL
    ALTER TABLE dbo.StampMaster ADD WebsiteReference NVARCHAR(40) NULL;
GO

IF COL_LENGTH(N'dbo.StampMaster', N'WebsiteReference') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1
        FROM sys.indexes
        WHERE name = N'UX_StampMaster_WebsiteReference'
          AND object_id = OBJECT_ID(N'dbo.StampMaster')
   )
    CREATE UNIQUE INDEX UX_StampMaster_WebsiteReference
        ON dbo.StampMaster (WebsiteReference)
        WHERE WebsiteReference IS NOT NULL AND IsActive = 1;
GO

PRINT '118_stamp_master_entry_source.sql completed.';
GO
