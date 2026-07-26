/*
    TDS Followup — Form Type + Quarter on FollowupEntryMaster
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.FollowupEntryMaster', N'FormType') IS NULL
BEGIN
    ALTER TABLE dbo.FollowupEntryMaster ADD FormType NVARCHAR(30) NULL;
END;
GO

IF COL_LENGTH(N'dbo.FollowupEntryMaster', N'Quarter') IS NULL
BEGIN
    ALTER TABLE dbo.FollowupEntryMaster ADD Quarter NVARCHAR(10) NULL;
END;
GO

PRINT '047_tds_followup_form_quarter.sql completed.';
GO
