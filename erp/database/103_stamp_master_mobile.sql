/*
    StampMaster — persist the mobile used at save/edit (walk-in, not CustomerMaster).
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.StampMaster', N'MobileNumber') IS NULL
    ALTER TABLE dbo.StampMaster ADD MobileNumber NVARCHAR(15) NULL;
GO

PRINT '103_stamp_master_mobile.sql completed.';
GO
