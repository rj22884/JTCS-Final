/*
    DSC Followup — Location and IntroducedBy (mandatory on entry form).
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.FollowupEntryMaster', N'Location') IS NULL
    ALTER TABLE dbo.FollowupEntryMaster ADD Location NVARCHAR(200) NULL;
GO

IF COL_LENGTH(N'dbo.FollowupEntryMaster', N'IntroducedBy') IS NULL
    ALTER TABLE dbo.FollowupEntryMaster ADD IntroducedBy NVARCHAR(200) NULL;
GO

PRINT '044_followup_dsc_location_introduced.sql completed.';
GO
