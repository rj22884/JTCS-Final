/*
    DSC Followup — permanent application number (separate from Tally bill no.)
*/
IF COL_LENGTH('dbo.FollowupEntryMaster', 'ApplicationNumber') IS NULL
    ALTER TABLE dbo.FollowupEntryMaster ADD ApplicationNumber NVARCHAR(50) NULL;
