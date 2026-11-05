/*
    Keep previous CSV import batches and store Added / Updated / Deleted markers.
    DATA safe / idempotent.
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.RationCardUploadBatch', N'ImportMode') IS NULL
    ALTER TABLE dbo.RationCardUploadBatch ADD ImportMode NVARCHAR(20) NULL;
GO

IF COL_LENGTH(N'dbo.RationCardMember', N'ChangeStatus') IS NULL
    ALTER TABLE dbo.RationCardMember ADD ChangeStatus NVARCHAR(20) NULL;
GO

IF COL_LENGTH(N'dbo.RationCardMember', N'ChangeDetail') IS NULL
    ALTER TABLE dbo.RationCardMember ADD ChangeDetail NVARCHAR(800) NULL;
GO
