USE JTCSS;
GO

IF COL_LENGTH('dbo.FollowupEntryMaster', 'ITRFiledDate') IS NULL
    ALTER TABLE dbo.FollowupEntryMaster ADD ITRFiledDate DATE NULL;
GO

IF COL_LENGTH('dbo.FollowupEntryMaster', 'BillAmount') IS NULL
    ALTER TABLE dbo.FollowupEntryMaster ADD BillAmount DECIMAL(18, 2) NULL;
GO

PRINT '033_followup_billing_fields.sql completed.';
GO
