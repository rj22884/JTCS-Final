/*
    Dashboard What's New — auto menu sync + published feature notes
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.WhatsNew', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.WhatsNew (
        EntryID INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_WhatsNew PRIMARY KEY,
        FeatureKey NVARCHAR(120) NOT NULL,
        Title NVARCHAR(200) NOT NULL,
        Detail NVARCHAR(500) NULL,
        UrlPath NVARCHAR(250) NULL,
        Badge NVARCHAR(20) NULL,
        EntryDate DATE NOT NULL,
        Source NVARCHAR(40) NOT NULL
            CONSTRAINT DF_WhatsNew_Source DEFAULT (N'manual'),
        IsActive BIT NOT NULL
            CONSTRAINT DF_WhatsNew_IsActive DEFAULT (1),
        CreatedDate DATETIME2 NOT NULL
            CONSTRAINT DF_WhatsNew_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL
    );
    CREATE UNIQUE INDEX UX_WhatsNew_FeatureKey ON dbo.WhatsNew (FeatureKey);
    CREATE INDEX IX_WhatsNew_Active_Date
        ON dbo.WhatsNew (IsActive, EntryDate DESC, EntryID DESC);
END;
GO

PRINT '063_whats_new.sql completed.';
GO
