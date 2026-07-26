/*
    ITR Followup: Return Filing Status + Filing Date (KDK sync columns)
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.FollowupEntryMaster', N'ReturnFilingStatus') IS NULL
BEGIN
    ALTER TABLE dbo.FollowupEntryMaster
    ADD ReturnFilingStatus NVARCHAR(150) NULL;
END;
GO

IF COL_LENGTH(N'dbo.FollowupEntryMaster', N'FilingDate') IS NULL
BEGIN
    ALTER TABLE dbo.FollowupEntryMaster
    ADD FilingDate DATE NULL;
END;
GO

PRINT '050_followup_itr_filing_status.sql completed.';
GO
