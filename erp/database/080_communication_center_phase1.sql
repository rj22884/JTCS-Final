/*
    Communication Center Phase 1 — extend CrmConversation / CrmMessage,
    add QuickReply / MessageTemplate / CallLog. Idempotent.
*/
USE JTCSS;
GO

/* ---- CrmConversation extensions ---- */
IF COL_LENGTH(N'dbo.CrmConversation', N'ExternalThreadKey') IS NULL
    ALTER TABLE dbo.CrmConversation ADD ExternalThreadKey NVARCHAR(128) NULL;
IF COL_LENGTH(N'dbo.CrmConversation', N'ContactMobile') IS NULL
    ALTER TABLE dbo.CrmConversation ADD ContactMobile NVARCHAR(30) NULL;
IF COL_LENGTH(N'dbo.CrmConversation', N'ContactEmail') IS NULL
    ALTER TABLE dbo.CrmConversation ADD ContactEmail NVARCHAR(255) NULL;
IF COL_LENGTH(N'dbo.CrmConversation', N'IsPinned') IS NULL
    ALTER TABLE dbo.CrmConversation ADD IsPinned BIT NOT NULL CONSTRAINT DF_CrmConversation_IsPinned DEFAULT (0);
IF COL_LENGTH(N'dbo.CrmConversation', N'IsArchived') IS NULL
    ALTER TABLE dbo.CrmConversation ADD IsArchived BIT NOT NULL CONSTRAINT DF_CrmConversation_IsArchived DEFAULT (0);
IF COL_LENGTH(N'dbo.CrmConversation', N'IsStarred') IS NULL
    ALTER TABLE dbo.CrmConversation ADD IsStarred BIT NOT NULL CONSTRAINT DF_CrmConversation_IsStarred DEFAULT (0);
IF COL_LENGTH(N'dbo.CrmConversation', N'LastInboundAt') IS NULL
    ALTER TABLE dbo.CrmConversation ADD LastInboundAt DATETIME2 NULL;
IF COL_LENGTH(N'dbo.CrmConversation', N'LastOutboundAt') IS NULL
    ALTER TABLE dbo.CrmConversation ADD LastOutboundAt DATETIME2 NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_CrmConversation_ExternalThreadKey'
      AND object_id = OBJECT_ID(N'dbo.CrmConversation')
)
    CREATE INDEX IX_CrmConversation_ExternalThreadKey
        ON dbo.CrmConversation (ExternalThreadKey)
        WHERE ExternalThreadKey IS NOT NULL;
GO

/* ---- CrmMessage extensions ---- */
IF COL_LENGTH(N'dbo.CrmMessage', N'ExternalMessageID') IS NULL
    ALTER TABLE dbo.CrmMessage ADD ExternalMessageID NVARCHAR(128) NULL;
IF COL_LENGTH(N'dbo.CrmMessage', N'DeliveryStatus') IS NULL
    ALTER TABLE dbo.CrmMessage ADD DeliveryStatus NVARCHAR(30) NULL;
IF COL_LENGTH(N'dbo.CrmMessage', N'StatusUpdatedAt') IS NULL
    ALTER TABLE dbo.CrmMessage ADD StatusUpdatedAt DATETIME2 NULL;
IF COL_LENGTH(N'dbo.CrmMessage', N'AttachmentMimeType') IS NULL
    ALTER TABLE dbo.CrmMessage ADD AttachmentMimeType NVARCHAR(100) NULL;
IF COL_LENGTH(N'dbo.CrmMessage', N'AttachmentSizeBytes') IS NULL
    ALTER TABLE dbo.CrmMessage ADD AttachmentSizeBytes BIGINT NULL;
IF COL_LENGTH(N'dbo.CrmMessage', N'MediaType') IS NULL
    ALTER TABLE dbo.CrmMessage ADD MediaType NVARCHAR(30) NULL;
IF COL_LENGTH(N'dbo.CrmMessage', N'IsStarred') IS NULL
    ALTER TABLE dbo.CrmMessage ADD IsStarred BIT NOT NULL CONSTRAINT DF_CrmMessage_IsStarred DEFAULT (0);
IF COL_LENGTH(N'dbo.CrmMessage', N'ErrorDetail') IS NULL
    ALTER TABLE dbo.CrmMessage ADD ErrorDetail NVARCHAR(500) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'UX_CrmMessage_ExternalMessageID'
      AND object_id = OBJECT_ID(N'dbo.CrmMessage')
)
    CREATE UNIQUE INDEX UX_CrmMessage_ExternalMessageID
        ON dbo.CrmMessage (ExternalMessageID)
        WHERE ExternalMessageID IS NOT NULL;
GO

/* ---- Quick Replies ---- */
IF OBJECT_ID(N'dbo.CrmQuickReply', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmQuickReply (
        QuickReplyID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        Title NVARCHAR(120) NOT NULL,
        Body NVARCHAR(MAX) NOT NULL,
        Channel NVARCHAR(50) NULL,
        Shortcut NVARCHAR(40) NULL,
        SortOrder INT NOT NULL CONSTRAINT DF_CrmQuickReply_Sort DEFAULT (0),
        IsActive BIT NOT NULL CONSTRAINT DF_CrmQuickReply_IsActive DEFAULT (1),
        CreatedByUserID INT NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmQuickReply_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL
    );
END;
GO

/* ---- Message Templates ---- */
IF OBJECT_ID(N'dbo.CrmMessageTemplate', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmMessageTemplate (
        TemplateID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        Name NVARCHAR(150) NOT NULL,
        Channel NVARCHAR(50) NOT NULL CONSTRAINT DF_CrmMessageTemplate_Channel DEFAULT (N'WhatsApp'),
        Subject NVARCHAR(255) NULL,
        Body NVARCHAR(MAX) NOT NULL,
        ExternalTemplateName NVARCHAR(150) NULL,
        LanguageCode NVARCHAR(20) NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_CrmMessageTemplate_IsActive DEFAULT (1),
        CreatedByUserID INT NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmMessageTemplate_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL
    );
END;
GO

/* ---- Call Logs ---- */
IF OBJECT_ID(N'dbo.CrmCallLog', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmCallLog (
        CallLogID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        CustomerID INT NULL,
        LeadID INT NULL,
        ConversationID INT NULL,
        Direction NVARCHAR(20) NOT NULL CONSTRAINT DF_CrmCallLog_Direction DEFAULT (N'Outgoing'),
        CallStatus NVARCHAR(30) NOT NULL CONSTRAINT DF_CrmCallLog_Status DEFAULT (N'Completed'),
        PhoneNumber NVARCHAR(30) NULL,
        DurationSeconds INT NULL,
        RecordingURL NVARCHAR(500) NULL,
        Notes NVARCHAR(MAX) NULL,
        NextFollowUpAt DATETIME2 NULL,
        CalledAt DATETIME2 NOT NULL CONSTRAINT DF_CrmCallLog_CalledAt DEFAULT (SYSUTCDATETIME()),
        CreatedByUserID INT NULL,
        CreatedByName NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmCallLog_Created DEFAULT (SYSUTCDATETIME()),
        IsActive BIT NOT NULL CONSTRAINT DF_CrmCallLog_IsActive DEFAULT (1)
    );
    CREATE INDEX IX_CrmCallLog_Customer ON dbo.CrmCallLog (CustomerID, CalledAt DESC);
    CREATE INDEX IX_CrmCallLog_Lead ON dbo.CrmCallLog (LeadID, CalledAt DESC);
END;
GO
