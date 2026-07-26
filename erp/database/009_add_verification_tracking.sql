/*
    JTCS ERP - Email verification audit columns on Users
*/
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.Users') AND name = N'VerificationDate')
    ALTER TABLE dbo.Users ADD VerificationDate DATETIME2 NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.Users') AND name = N'VerificationIP')
    ALTER TABLE dbo.Users ADD VerificationIP NVARCHAR(45) NULL;
GO

PRINT '009_add_verification_tracking.sql completed.';
GO
